#!/usr/bin/env python3
"""US Census Port HS6 monthly records: reproducible, typed evidence, no shipment inference.

The official ZIPs contain fixed-width ASCII records (230 chars), not CSV. Neither
port-country-HS6 aggregate nor USACE tonnage identifies a company or a vessel.
"""
import argparse
from contextlib import nullcontext
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import sqlite3
from urllib.request import Request, urlopen
import zipfile

PORTAL='https://www.census.gov/foreign-trade/data/'
LAYOUT={
 'M':'https://www.census.gov/foreign-trade/reference/products/layouts/dporths6i.html',
 'X':'https://www.census.gov/foreign-trade/reference/products/layouts/dporths6e.html',
}
NUM_FIELDS=('value_usd','air_value_usd','air_weight_kg','vessel_value_usd',
            'vessel_weight_kg','container_value_usd','container_weight_kg',
            'ytd_value_usd','ytd_air_value_usd','ytd_air_weight_kg',
            'ytd_vessel_value_usd','ytd_vessel_weight_kg',
            'ytd_container_value_usd','ytd_container_weight_kg')

def source_url(period,flow):
    if not re.fullmatch(r'20\d{2}(0[1-9]|1[0-2])',period):
        raise ValueError('period must be YYYYMM (2000-2099)')
    if flow not in ('M','X'):raise ValueError('flow must be M or X')
    folder='im_hs6_m' if flow=='M' else 'ex_hs6_m'
    prefix='PORTHS6MM' if flow=='M' else 'PORTHS6XM'
    return f'https://www.census.gov/trade/downloads/{period[:4]}/Port/{folder}/{prefix}{period[2:]}.ZIP'

def parse_record(raw, period):
    """Parse one official record; reject mismatched periods and malformed quantities."""
    if isinstance(raw,bytes):raw=raw.decode('ascii','strict')
    raw=raw.rstrip('\r\n')
    if len(raw)!=230:raise ValueError(f'expected 230 chars, got {len(raw)}')
    keys=('hs6','country_code','port_code','year','month')
    lengths=(6,4,4,4,2)
    pos=0; row={}
    for key,length in zip(keys,lengths):
        part=raw[pos:pos+length];pos+=length
        if not part.isascii() or not part.isdigit():raise ValueError(f'invalid {key}: {part!r}')
        row[key]=part
    if row.pop('year')+row.pop('month')!=period:raise ValueError('record period does not match source archive')
    for key in NUM_FIELDS:
        part=raw[pos:pos+15];pos+=15
        if not part.isascii() or not part.isdigit():raise ValueError(f'invalid {key}: {part!r}')
        row[key]=int(part)
    assert pos==230
    if row['air_value_usd']+row['vessel_value_usd']>row['value_usd']:
        raise ValueError('air plus vessel exceeds total value')
    if row['container_value_usd']>row['vessel_value_usd']:
        raise ValueError('containerized vessel value exceeds vessel value')
    if row['container_weight_kg']>row['vessel_weight_kg']:
        raise ValueError('containerized vessel weight exceeds vessel weight')
    return row

SCHEMA='''
CREATE TABLE IF NOT EXISTS port_hs6_archives(
  period TEXT NOT NULL, flow TEXT NOT NULL CHECK(flow IN ('M','X')),
  sha256 TEXT NOT NULL, source_url TEXT NOT NULL, layout_url TEXT NOT NULL,
  archive_bytes INTEGER NOT NULL, physical_rows INTEGER NOT NULL,
  stored_rows INTEGER NOT NULL, selection TEXT NOT NULL,
  imported_utc TEXT NOT NULL, PRIMARY KEY(period,flow));
CREATE TABLE IF NOT EXISTS port_hs6(
  period TEXT NOT NULL,flow TEXT NOT NULL,hs6 TEXT NOT NULL,country_code TEXT NOT NULL,
  port_code TEXT NOT NULL,value_usd INTEGER NOT NULL,air_value_usd INTEGER NOT NULL,
  air_weight_kg INTEGER NOT NULL,vessel_value_usd INTEGER NOT NULL,
  vessel_weight_kg INTEGER NOT NULL,container_value_usd INTEGER NOT NULL,
  container_weight_kg INTEGER NOT NULL,
  PRIMARY KEY(period,flow,hs6,country_code,port_code),
  FOREIGN KEY(period,flow) REFERENCES port_hs6_archives(period,flow),
  CHECK(length(hs6)=6), CHECK(length(country_code)=4), CHECK(length(port_code)=4),
  CHECK(value_usd>=0),CHECK(container_value_usd<=vessel_value_usd),
  CHECK(container_weight_kg<=vessel_weight_kg));
CREATE INDEX IF NOT EXISTS ix_port_hs6_period ON port_hs6(flow,hs6,period,port_code,country_code);
'''

def initialize(conn):
    conn.execute('PRAGMA foreign_keys=ON')
    conn.executescript(SCHEMA)

def iter_fixed_records(stream):
    """Support LF, CRLF and contiguous 230-byte official fixed-length files."""
    first=stream.peek(232)
    if first[230:231] in (b'\n',b'\r') or first[231:232]==b'\n':
        yield from stream
        return
    while True:
        record=stream.read(230)
        if not record:break
        if len(record)!=230:raise ValueError('truncated final fixed-width record')
        yield record

def import_archive(conn,path,period,flow,hs_prefixes=(), *, manage_transaction=True):
    """Atomic import: reject malformed data, never silently overwrite revisions."""
    url=source_url(period,flow)
    prefixes=tuple(hs_prefixes)
    if any(not re.fullmatch(r'\d{2,6}',p) for p in prefixes):
        raise ValueError('HS prefixes must contain 2-6 digits')
    selection='complete_file' if not prefixes else 'filtered:' + ','.join(sorted(prefixes))
    path=Path(path)
    h=hashlib.sha256();size=0
    with path.open('rb') as stream:
        for chunk in iter(lambda:stream.read(1024*1024),b''):
            h.update(chunk);size+=len(chunk)
    sha=h.hexdigest()
    existing=conn.execute('SELECT sha256,selection FROM port_hs6_archives WHERE period=? AND flow=?',(period,flow)).fetchone()
    if existing:
        if existing==(sha,selection):
            return {'period':period,'flow':flow,'status':'unchanged','sha256':sha,'rows_stored':conn.execute('SELECT count(*) FROM port_hs6 WHERE period=? AND flow=?',(period,flow)).fetchone()[0]}
        raise ValueError('source revision or selection changed; preserve evidence and import to a fresh database')
    member_prefix=f'DPORTHS6{"I" if flow=="M" else "E"}'
    # Current monthly Census ZIPs add "R" in their TXT member name;
    # the published layout lists the older spelling without "R".
    accepted={f'{member_prefix}{period[2:]}.TXT',
              f'{member_prefix}R{period[2:]}.TXT'}
    with zipfile.ZipFile(path) as archive:
        matches=[x for x in archive.namelist() if Path(x).name.upper() in accepted]
        if len(matches)!=1:
            raise ValueError(f'expected one official {member_prefix} [R] {period[2:]} TXT member, found {len(matches)}')
        info=archive.getinfo(matches[0])
        if info.file_size>2_000_000_000:raise ValueError('uncompressed archive exceeds size limit')
        with conn if manage_transaction else nullcontext():
            conn.execute('INSERT INTO port_hs6_archives VALUES(?,?,?,?,?,?,?,?,?,?)',
                         (period,flow,sha,url,LAYOUT[flow],size,0,0,selection,datetime.now(timezone.utc).isoformat()))
            total=stored=0
            with archive.open(matches[0]) as stream:
                batch=[]
                for line in iter_fixed_records(stream):
                    if not line.strip():continue
                    total+=1
                    try:row=parse_record(line,period)
                    except (ValueError,UnicodeError) as exc:
                        raise ValueError(f'{path.name}:{total}: {exc}') from exc
                    if prefixes and not row['hs6'].startswith(prefixes):continue
                    batch.append((period,flow,row['hs6'],row['country_code'],row['port_code'],
                                  *(row[k] for k in NUM_FIELDS[:7])))
                    if len(batch)>=2000:
                        conn.executemany('INSERT INTO port_hs6 VALUES(?,?,?,?,?,?,?,?,?,?,?,?)',batch)
                        stored+=len(batch);batch=[]
                if batch:
                    conn.executemany('INSERT INTO port_hs6 VALUES(?,?,?,?,?,?,?,?,?,?,?,?)',batch)
                    stored+=len(batch)
            if not total:raise ValueError('archive contains no records')
            conn.execute('UPDATE port_hs6_archives SET physical_rows=?,stored_rows=? WHERE period=? AND flow=?',
                         (total,stored,period,flow))
    return {'period':period,'flow':flow,'status':'complete_file' if not prefixes else 'filtered',
            'physical_rows':total,'rows_stored':stored,'sha256':sha,'source_url':url}

def quarter_routes(conn,year,hs_prefix,flow,limit=20):
    """Aggregate evidence without mixing months, shipping modes or data sources."""
    if not re.fullmatch(r'20\d{2}',year) or not re.fullmatch(r'\d{2,6}',hs_prefix) or flow not in ('M','X'):
        raise ValueError('invalid year / HS prefix / flow')
    ps=tuple(year+f'{m:02d}' for m in (1,2,3))
    info=conn.execute('SELECT period,selection FROM port_hs6_archives WHERE flow=? AND period IN (?,?,?)',(flow,*ps)).fetchall()
    coverage_complete=len(info)==3 and all(x[1]=='complete_file' for x in info)
    where="period IN (?,?,?) AND flow=? AND substr(hs6,1,?)=?"
    args=(*ps,flow,len(hs_prefix),hs_prefix)
    totals=conn.execute('SELECT COALESCE(SUM(value_usd),0),count(*) FROM port_hs6 WHERE '+where,args).fetchone()
    rows=conn.execute('''SELECT port_code,country_code,SUM(value_usd) value_usd,
      SUM(air_value_usd) air_value_usd,SUM(vessel_value_usd) vessel_value_usd,
      SUM(container_value_usd) container_value_usd,COUNT(*) hs6_month_rows
      FROM port_hs6 WHERE '''+where+''' GROUP BY port_code,country_code
      ORDER BY value_usd DESC,port_code,country_code LIMIT ?''',(*args,limit)).fetchall() if coverage_complete else []
    return {'year':year,'hs_prefix':hs_prefix,'flow':flow,'months':len(info),
            'month_ids':sorted(p for p,_ in info),'coverage_complete':coverage_complete,
            'total_usd':totals[0] if coverage_complete else None,'observed_usd':totals[0],
            'rows':totals[1], 'routes':[dict(zip(('port_code','country_code','value_usd','air_value_usd','vessel_value_usd','container_value_usd','hs6_month_rows'),r)) for r in rows],
            'claim':'aggregate HS6 by partner-country and customs port; not shipment or vessel evidence'}

def evidence_status(conn):
    n=conn.execute('SELECT count(*) FROM port_hs6').fetchone()[0]
    sources=conn.execute('SELECT period,flow,sha256,physical_rows,stored_rows,selection,source_url FROM port_hs6_archives ORDER BY period,flow').fetchall()
    return {'port_hs6_records':n,'archive_count':len(sources),'archives':[dict(zip(('period','flow','sha256','physical_rows','stored_rows','selection','source_url'),r)) for r in sources],
            'verified_bills_of_lading':0,'company_shipment_edges':0,'verified_vessel_links':0}

def fetch(period,flow,dest):
    """Fetch only a known official census URL; no third party mirror or API key."""
    u=source_url(period,flow); dest=Path(dest);dest.parent.mkdir(parents=True,exist_ok=True)
    req=Request(u,headers={'User-Agent':'Lithographie research (official US Census monthly archive)'})
    with urlopen(req,timeout=80) as stream, dest.open('wb') as out:
        while True:
            chunk=stream.read(1024*1024)
            if not chunk:break
            out.write(chunk)
            if out.tell()>100_000_000:raise ValueError('archive exceeds 100 MB')
    if not zipfile.is_zipfile(dest):
        dest.unlink(missing_ok=True)
        raise ValueError('download was not a valid ZIP')
    return dest

def main():
    cli=argparse.ArgumentParser(description=__doc__)
    cli.add_argument('--db',type=Path,default=Path(__file__).parent/'lithographie.sqlite')
    sub=cli.add_subparsers(dest='action',required=True)
    get=sub.add_parser('fetch');get.add_argument('--period',required=True);get.add_argument('--flow',required=True,choices=('M','X'))
    get.add_argument('--output',type=Path)
    load=sub.add_parser('import');load.add_argument('zip',type=Path);load.add_argument('--period',required=True);load.add_argument('--flow',required=True,choices=('M','X'))
    load.add_argument('--hs-prefix',action='append',default=[])
    qry=sub.add_parser('compare');qry.add_argument('--year',required=True);qry.add_argument('--hs',required=True);qry.add_argument('--flow',choices=('M','X'),required=True)
    sub.add_parser('coverage')
    a=cli.parse_args()
    if a.action=='fetch':
        name=f'PORTHS6{"MM" if a.flow=="M" else "XM"}{a.period[2:]}.ZIP'
        print(fetch(a.period,a.flow,a.output or Path(__file__).parent/'downloads'/name));return
    conn=sqlite3.connect(a.db)
    try:
        initialize(conn)
        result=(import_archive(conn,a.zip,a.period,a.flow,a.hs_prefix) if a.action=='import' else
                quarter_routes(conn,a.year,a.hs,a.flow) if a.action=='compare' else evidence_status(conn))
        print(json.dumps(result,indent=2))
    finally:conn.close()

if __name__=='__main__':main()
