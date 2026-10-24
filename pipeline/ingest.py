"""Immutable source archive, typed parsing ledger and bounded HTTP acquisition.

A 'raw' blob is exactly the input received (including browser-produced extracts).
It does not follow that all raw objects are original publisher responses.
"""
from datetime import datetime,timezone
import hashlib,json,os,re,sqlite3,tempfile,zipfile
from pathlib import Path
from urllib.parse import urlsplit
from urllib.request import Request,build_opener,HTTPRedirectHandler
from .registry import SourceSpec,source_url
from .adapters import parse_comtrade_world,parse_html_country_codes,parse_gleif_entity,parse_census_browser_extract

PARSER_VERSION='3'
SCHEMA='''
PRAGMA foreign_keys=ON;
CREATE TABLE IF NOT EXISTS sources(source_id TEXT PRIMARY KEY,adapter TEXT NOT NULL,acquisition_method TEXT NOT NULL,
  observation_type TEXT NOT NULL,provenance TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS source_objects(sha256 TEXT PRIMARY KEY,bytes INTEGER NOT NULL,archived_utc TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS acquisitions(id INTEGER PRIMARY KEY,source_id TEXT NOT NULL REFERENCES sources(source_id),sha256 TEXT NOT NULL REFERENCES source_objects(sha256),
  source_url TEXT NOT NULL,method TEXT NOT NULL,acquired_utc TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS ingestion_runs(id INTEGER PRIMARY KEY,source_id TEXT NOT NULL REFERENCES sources(source_id),
  sha256 TEXT NOT NULL REFERENCES source_objects(sha256),parser_version TEXT NOT NULL,status TEXT NOT NULL,
  reason TEXT,records INTEGER NOT NULL DEFAULT 0,scope_json TEXT NOT NULL,run_utc TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS ix_runs_source ON ingestion_runs(source_id,sha256,parser_version,status);
CREATE TABLE IF NOT EXISTS records(source_id TEXT NOT NULL REFERENCES sources(source_id),sha256 TEXT NOT NULL REFERENCES source_objects(sha256),
  parser_version TEXT NOT NULL,record_type TEXT NOT NULL,record_key TEXT NOT NULL,
  data_json TEXT NOT NULL,provenance TEXT NOT NULL,PRIMARY KEY(source_id,sha256,parser_version,record_type,record_key));
CREATE INDEX IF NOT EXISTS ix_records_kind ON records(record_type,source_id);
'''

def utc():return datetime.now(timezone.utc).isoformat()
def digest(data):return hashlib.sha256(data).hexdigest()

class EvidenceVault:
    def __init__(self,root):
        self.root=Path(root);self.root.mkdir(parents=True,exist_ok=True)
        self.conn=sqlite3.connect(self.root/'evidence.sqlite')
        self.conn.execute('PRAGMA foreign_keys=ON');self.conn.executescript(SCHEMA)
    def close(self):self.conn.close()
    def raw_path(self,sha256):
        if not re.fullmatch('[a-f0-9]{64}',sha256):raise ValueError('invalid digest')
        return self.root/'raw'/'sha256'/sha256[:2]/sha256
    def store_raw(self,raw):
        if not isinstance(raw,bytes):raise TypeError('source bytes required')
        sha=digest(raw);path=self.raw_path(sha);path.parent.mkdir(parents=True,exist_ok=True)
        if path.exists():
            if digest(path.read_bytes())!=sha:raise ValueError('stored raw object checksum mismatch')
        else:
            with tempfile.NamedTemporaryFile(dir=path.parent,delete=False) as tmp:
                tmp.write(raw);tmp.flush();os.fsync(tmp.fileno());name=tmp.name
            try:
                # Race-safe create. Another process cannot mutate an existing object.
                try:os.link(name,path)
                except FileExistsError:
                    if digest(path.read_bytes())!=sha:raise ValueError('colliding raw object')
            finally:os.unlink(name)
        with self.conn:
            self.conn.execute('INSERT OR IGNORE INTO source_objects VALUES(?,?,?)',(sha,len(raw),utc()))
        return sha
    def records(self,source_id=None):
        query='SELECT source_id,sha256,record_type,record_key,data_json,provenance FROM records'
        args=()
        if source_id:query+=' WHERE source_id=?';args=(source_id,)
        return [{'source_id':a,'sha256':b,'observation_type':c,'key':d,'data':json.loads(e),'provenance':f} for a,b,c,d,e,f in self.conn.execute(query+' ORDER BY record_key,sha256',args)]
    def current_records(self,source_id=None):
        """Explicit latest accepted revision PER scope. Never sum all versions by default."""
        query="""WITH ranked AS (
          SELECT source_id,sha256,parser_version,scope_json,
          ROW_NUMBER() OVER(PARTITION BY source_id,scope_json ORDER BY id DESC) AS version_rank
          FROM ingestion_runs WHERE status='accepted'
        )
        SELECT o.source_id,o.sha256,o.record_type,o.record_key,o.data_json,o.provenance
          FROM records o JOIN ranked r ON o.source_id=r.source_id
          AND o.sha256=r.sha256 AND o.parser_version=r.parser_version
          WHERE r.version_rank=1"""
        args=()
        if source_id:query+=' AND o.source_id=?';args=(source_id,)
        return [{'source_id':a,'sha256':b,'observation_type':c,'key':d,'data':json.loads(e),'provenance':f}
            for a,b,c,d,e,f in self.conn.execute(query+' ORDER BY o.record_key,o.sha256',args)]
    def failures(self):
        return [dict(zip(('source_id','sha256','reason'),r)) for r in self.conn.execute("SELECT source_id,sha256,reason FROM ingestion_runs WHERE status='quarantined' ORDER BY id")]
    def revisions(self,source_id):
        return [dict(zip(('sha256','status','records','run_utc'),r)) for r in self.conn.execute('SELECT sha256,status,records,run_utc FROM ingestion_runs WHERE source_id=? ORDER BY id',(source_id,))]
    def status(self):
        archives=0
        try:archives=self.conn.execute('SELECT COUNT(*) FROM port_hs6_archives').fetchone()[0]
        except sqlite3.OperationalError:pass
        return {'distinct_raw_objects':self.conn.execute('SELECT count(*) FROM source_objects').fetchone()[0],
                'accepted_runs':self.conn.execute("SELECT count(*) FROM ingestion_runs WHERE status='accepted'").fetchone()[0],
                'quarantined_runs':self.conn.execute("SELECT count(*) FROM ingestion_runs WHERE status='quarantined'").fetchone()[0],
                'typed_rows':self.conn.execute('SELECT count(*) FROM records').fetchone()[0],
                'browser_verified_extract_rows':self.conn.execute("SELECT count(*) FROM records WHERE provenance='browser_full_scan_unbundled_zip'").fetchone()[0],
                'raw_census_archives_imported':archives}

def validate_url(spec,location,scope):
    expected=source_url(spec,**scope) if spec.adapter!='census_extract' else spec.url
    parsed=urlsplit(location)
    if parsed.scheme!='https' or not parsed.netloc or parsed.username or parsed.password or parsed.fragment:
        raise ValueError('source URL must be HTTPS without credentials or fragments')
    if location!=expected:raise ValueError('source URL not in registry scope; refusing alternate endpoint')

def ingest_bytes(vault,spec,raw,location,scope,origin="local_copy"):
    if origin not in ('local_copy','browser_capture','https_fetch','replay'):
        raise ValueError('unrecognized acquisition origin')
    scope=dict(scope)
    if spec.adapter=='census_extract':scope.setdefault('period',spec.period)
    validate_url(spec,location,scope)
    if len(raw)>spec.max_bytes:raise ValueError('response exceeds configured byte limit')
    sha=vault.store_raw(raw)
    with vault.conn:
        vault.conn.execute('INSERT OR IGNORE INTO sources VALUES(?,?,?,?,?)',(spec.source_id,spec.adapter,spec.method,spec.observation_type,spec.provenance))
        current=vault.conn.execute('SELECT id FROM ingestion_runs WHERE source_id=? AND sha256=? AND parser_version=? AND status=? AND scope_json=?',
          (spec.source_id,sha,PARSER_VERSION,'accepted',json.dumps(scope,sort_keys=True))).fetchone()
        vault.conn.execute('INSERT INTO acquisitions(source_id,sha256,source_url,method,acquired_utc) VALUES(?,?,?,?,?)',
                           (spec.source_id,sha,location,origin,utc()))
        if current:return {'status':'unchanged','sha256':sha,'records':vault.conn.execute('SELECT COUNT(*) FROM records WHERE source_id=? AND sha256=?',(spec.source_id,sha)).fetchone()[0]}
    try:
        if spec.adapter=='census_extract':rows=parse_census_browser_extract(raw,scope)
        elif spec.adapter=='comtrade_world':rows=parse_comtrade_world(raw,scope)
        elif spec.adapter=='census_country_html':rows=parse_html_country_codes(raw,scope)
        elif spec.adapter=='gleif_record':rows=parse_gleif_entity(raw,scope)
        elif spec.adapter=='census_zip':
            from engine.census_port_hs6 import initialize,import_archive
            # A supplied file bearing an official filename is NOT proof of
            # publisher provenance. For independently audited periods pin the
            # original ZIP SHA; for future periods require HTTPS acquisition.
            audit_path=Path(__file__).resolve().parents[1]/'research/data/browser_scanned_totals.json'
            audit=json.loads(audit_path.read_text())
            pin=next((x for x in audit['archives'] if x['period']==scope['period']),None)
            if pin and pin['source_sha256']!=sha:
                raise ValueError('Census ZIP checksum differs from independent archive scan; source revision needs review')
            if not pin and origin!='https_fetch':
                raise ValueError('unverified local Census ZIP; fetch publisher file via HTTPS')
            with zipfile.ZipFile(vault.raw_path(sha)) as candidate:
                if sum(m.file_size for m in candidate.infolist())>600_000_000:
                    raise ValueError('uncompressed Census ZIP exceeds safety limit')
            initialize(vault.conn)
            # Accept the archive and its ingestion ledger in one transaction.
            with vault.conn:
                result=import_archive(vault.conn,vault.raw_path(sha),scope['period'],'M',manage_transaction=False)
                if result['status']=='unchanged':
                    raise ValueError('existing Census archive needs isolated replay under the new parser version')
                vault.conn.execute('''INSERT INTO ingestion_runs(source_id,sha256,parser_version,status,records,scope_json,run_utc)
                    VALUES(?,?,?,?,?,?,?)''',(spec.source_id,sha,PARSER_VERSION,'accepted',
                    result['rows_stored'],json.dumps(scope,sort_keys=True),utc()))
            return {'status':'accepted','sha256':sha,'records':result['rows_stored']}
        else:raise ValueError('unsupported adapter')
        keys=set()
        for row in rows:
            if row['type']!=spec.observation_type:raise ValueError('adapter output type mismatch')
            if (row['type'],row['key']) in keys:raise ValueError('duplicate record identity in source')
            keys.add((row['type'],row['key']))
        actual_provenance=(spec.provenance if spec.method=='browser_extract' else
                 spec.provenance if origin=='https_fetch' else
                 'sha256_pinned_to_independent_scan' if spec.adapter=='census_zip' else
                 'local_payload_unverified_origin')
        with vault.conn:
            vault.conn.executemany('INSERT INTO records VALUES(?,?,?,?,?,?,?)',
                [(spec.source_id,sha,PARSER_VERSION,r['type'],r['key'],json.dumps(r['data'],sort_keys=True),actual_provenance) for r in rows])
            vault.conn.execute('INSERT INTO ingestion_runs(source_id,sha256,parser_version,status,records,scope_json,run_utc) VALUES(?,?,?,?,?,?,?)',
                (spec.source_id,sha,PARSER_VERSION,'accepted',len(rows),json.dumps(scope,sort_keys=True),utc()))
        return {'status':'accepted','sha256':sha,'records':len(rows)}
    except (ValueError,TypeError,KeyError,sqlite3.DatabaseError,zipfile.BadZipFile) as e:
        # Quarantine is not a successful import. Raw input is still preserved.
        with vault.conn:
            vault.conn.execute('INSERT INTO ingestion_runs(source_id,sha256,parser_version,status,reason,scope_json,run_utc) VALUES(?,?,?,?,?,?,?)',
                (spec.source_id,sha,PARSER_VERSION,'quarantined',str(e),json.dumps(scope,sort_keys=True),utc()))
        return {'status':'quarantined','sha256':sha,'records':0,'reason':str(e)}

def _census_row_fingerprint(conn,period):
    """Compare every stored aggregate value, not just equal month totals."""
    h=hashlib.sha256()
    sql="""SELECT hs6,country_code,port_code,value_usd,air_value_usd,
        air_weight_kg,vessel_value_usd,vessel_weight_kg,container_value_usd,
        container_weight_kg FROM port_hs6 WHERE period=? AND flow='M'
        ORDER BY hs6,country_code,port_code"""
    for row in conn.execute(sql,(period,)):
        h.update(json.dumps(row,separators=(',',':')).encode()+b'\n')
    return h.hexdigest()

def replay(vault,spec,sha,scope):
    """Reparse full Census ZIPs in an isolated database; never overwrite accepted rows."""
    if spec.adapter!='census_zip':
        return ingest_bytes(vault,spec,vault.raw_path(sha).read_bytes(),source_url(spec,**scope),scope,origin='replay')
    from engine.census_port_hs6 import initialize,import_archive
    if not vault.conn.execute("SELECT 1 FROM ingestion_runs WHERE source_id=? AND sha256=? AND status='accepted'",
                 (spec.source_id,sha)).fetchone():
        raise ValueError('cannot replay an unaccepted source ZIP')
    period=scope.get('period','')
    if not vault.conn.execute("SELECT 1 FROM port_hs6_archives WHERE period=? AND flow='M' AND sha256=?",
                              (period,sha)).fetchone():
        raise ValueError('original archive and replay scope differ')
    if vault.conn.execute("SELECT 1 FROM ingestion_runs WHERE source_id=? AND sha256=? AND parser_version=? AND status='verified_replay'",
                          (spec.source_id,sha,PARSER_VERSION)).fetchone():
        return {'status':'unchanged','sha256':sha,'not_promoted':True}
    original=vault.conn.execute("""SELECT parser_version FROM ingestion_runs WHERE source_id=? AND sha256=?
                       AND status='accepted' ORDER BY id DESC LIMIT 1""",(spec.source_id,sha)).fetchone()[0]
    if original==PARSER_VERSION:
        return {'status':'unchanged','sha256':sha,'reason':'accepted under current parser'}
    replay_dir=vault.root/'replays';replay_dir.mkdir(exist_ok=True)
    stage=replay_dir/f'{sha}-parser-{PARSER_VERSION}.sqlite'
    if stage.exists():raise ValueError('existing staged replay requires review')
    with tempfile.NamedTemporaryFile(dir=replay_dir,suffix='.sqlite',delete=False) as tmp:
        temp_path=Path(tmp.name)
    try:
        conn=sqlite3.connect(temp_path)
        try:
            initialize(conn)
            outcome=import_archive(conn,vault.raw_path(sha),period,'M')
            old_hash=_census_row_fingerprint(vault.conn,period)
            new_hash=_census_row_fingerprint(conn,period)
        finally:conn.close()
        temp_path.replace(stage)
        status='verified_replay' if old_hash==new_hash else 'source_conflict'
        with vault.conn:
            vault.conn.execute("""INSERT INTO ingestion_runs(source_id,sha256,parser_version,status,reason,records,scope_json,run_utc)
              VALUES(?,?,?,?,?,?,?,?)""",(spec.source_id,sha,PARSER_VERSION,status,
              'isolated replay; no automatic promotion',outcome['rows_stored'],json.dumps(scope,sort_keys=True),utc()))
        return {'status':status,'sha256':sha,'staging_database':str(stage),'not_promoted':True,
                'original_record_fingerprint':old_hash,'replay_record_fingerprint':new_hash,
                'records':outcome['rows_stored']}
    except Exception:
        temp_path.unlink(missing_ok=True)
        raise

class _SameHostRedirect(HTTPRedirectHandler):
    def redirect_request(self,req,fp,code,msg,headers,newurl):
        if urlsplit(newurl).netloc.lower()!=urlsplit(req.full_url).netloc.lower() or urlsplit(newurl).scheme!='https':
            raise ValueError('redirect would leave approved HTTPS host')
        return super().redirect_request(req,fp,code,msg,headers,newurl)

def fetch(vault,spec,scope,timeout=40):
    if spec.method=='browser_extract':raise ValueError('browser extract is not fetchable as its original ZIP')
    url=source_url(spec,**scope);validate_url(spec,url,scope)
    req=Request(url,headers={'User-Agent':'Lithographie trade research; source audit','Accept':'application/json,text/html,application/zip,*/*'})
    with build_opener(_SameHostRedirect()).open(req,timeout=timeout) as stream:
        body=stream.read(spec.max_bytes+1)
        if len(body)>spec.max_bytes:raise ValueError('source exceeded size limit')
    return ingest_bytes(vault,spec,body,url,scope,origin="https_fetch")

def compare_revisions(vault,source_id,old_sha,new_sha):
    """Inspect source revisions, never silently accept a revised value as history."""
    for sha in (old_sha,new_sha):
        if not vault.conn.execute("SELECT 1 FROM ingestion_runs WHERE source_id=? AND sha256=? AND status='accepted'",(source_id,sha)).fetchone():
            raise ValueError('both revisions must be accepted and stored')
    scopes=[{r[0] for r in vault.conn.execute("SELECT scope_json FROM ingestion_runs WHERE source_id=? AND sha256=? AND status='accepted'",(source_id,sha))} for sha in (old_sha,new_sha)]
    if len(scopes[0])!=1 or scopes[0]!=scopes[1]:raise ValueError('cannot diff different data scopes')
    def collect(sha):
        return {r['key']:r['data'] for r in vault.records(source_id) if r['sha256']==sha}
    a,b=collect(old_sha),collect(new_sha)
    return {'source_id':source_id,'old_sha256':old_sha,'new_sha256':new_sha,
        'added_keys':sorted(b.keys()-a.keys()),'removed_keys':sorted(a.keys()-b.keys()),
        'changed_keys':sorted(k for k in a.keys()&b.keys() if a[k]!=b[k]),
        'unchanged_count':sum(a[k]==b[k] for k in a.keys()&b.keys()),
        'status':'comparison_only; no revisions removed or overwritten'}

def compare_equivalent(records):
    types={r['observation_type'] for r in records}
    if len(types)!=1 or types!={'customs_port_aggregate'}:
        return {'status':'not_comparable','reason':'different units, geography, classification or observation types'}
    return {'status':'requires_scope_validation','reason':'check period, HS version, geography, measure and source coverage before comparison'}
