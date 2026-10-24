"""Lithographie acquisition CLI: explicit source contracts, no implicit joins."""
import argparse,csv,json,sys
from pathlib import Path
from .ingest import EvidenceVault,ingest_bytes,fetch,replay
from .registry import SOURCES,CENSUS_EXTRACT_2024,CENSUS_EXTRACT_2025,CENSUS_COUNTRY_BROWSER_FRAGMENT,COMTRADE_WORLD_BROWSER,source_url

ROOT=Path(__file__).resolve().parents[1]
def spec_from_args(args):
    if args.source=='census_browser_hs6_extract':
        return {'202401':CENSUS_EXTRACT_2024,'202501':CENSUS_EXTRACT_2025}.get(args.period) or (_ for _ in ()).throw(ValueError('browser extract requires period 202401 or 202501'))
    if args.source not in SOURCES:raise ValueError(f'unknown registered source {args.source}')
    return SOURCES[args.source]
def get_scope(args,spec):
    if spec.adapter=='census_extract':return {}
    if spec.adapter in ('comtrade_world','census_zip'):return {x:getattr(args,x) for x in (('period','hs','flow') if spec.adapter=='comtrade_world' else ('period',))}
    if spec.adapter=='gleif_record':return {'lei':args.lei}
    return {}
def make_parser():
    p=argparse.ArgumentParser(description='Source registry and immutable evidence warehouse')
    p.add_argument('--vault',type=Path,default=ROOT/'var'/'evidence-vault')
    sub=p.add_subparsers(dest='command',required=True)
    sub.add_parser('bootstrap',help='validate and ingest two existing browser-scanned Census HS6 extracts')
    sub.add_parser('status')
    sub.add_parser('sources')
    for command in ('ingest-file','fetch','replay'):
        a=sub.add_parser(command)
        a.add_argument('--source',required=True)
        a.add_argument('--period',default='')
        a.add_argument('--hs',default='')
        a.add_argument('--flow',default='M')
        a.add_argument('--lei',default='')
        if command=='ingest-file':a.add_argument('--file',type=Path,required=True)
        if command=='replay':a.add_argument('--sha256',required=True)
    compare=sub.add_parser('compare',help='matched-month evidence comparison with ggplot2 CSV output')
    compare.add_argument('--hs',required=True)
    compare.add_argument('--base',required=True)
    compare.add_argument('--comparison',required=True)
    compare.add_argument('--csv',type=Path)
    export=sub.add_parser('export')
    export.add_argument('--source',required=True)
    export.add_argument('--out',required=True,type=Path)
    return p

def main(argv=None):
    args=make_parser().parse_args(argv)
    vault=EvidenceVault(args.vault)
    try:
        if args.command=='bootstrap':
            result=[]
            for spec in (CENSUS_EXTRACT_2024,CENSUS_EXTRACT_2025):
                path=ROOT/'research/data'/f'census_760110_{spec.period}_verified.json'
                r=ingest_bytes(vault,spec,path.read_bytes(),spec.url,{})
                if r['status']=='quarantined':raise ValueError(r['reason'])
                result.append({'source':spec.source_id,'period':spec.period,**r})
            captures=(
                (CENSUS_COUNTRY_BROWSER_FRAGMENT,ROOT/'research/data/browser_census_schedule_c_excerpt.html',{}),
                (COMTRADE_WORLD_BROWSER,ROOT/'research/data/browser_comtrade_202501_hs7601.json',
                 {'period':'202501','hs':'7601','flow':'M'}),
            )
            for spec,path,scope in captures:
                r=ingest_bytes(vault,spec,path.read_bytes(),source_url(spec,**scope),scope)
                if r['status']=='quarantined':raise ValueError(r['reason'])
                result.append({'source':spec.source_id,**r})
            output={'ingested':result,'vault_status':vault.status(),
                    'coverage_label':'browser_scanned_extract and small browser API/HTML captures; full source bytes not stored'}
        elif args.command=='status':
            output={**vault.status(),'sources':{sid:len(vault.records(sid)) for sid in sorted({r[0] for r in vault.conn.execute('SELECT source_id FROM sources')})}}
        elif args.command=='sources':
            from .registry import ALL_SOURCES
            output=[{'source_id':s.source_id,'adapter':s.adapter,'method':s.method,'provenance':s.provenance,'url':s.url} for s in ALL_SOURCES]
        elif args.command=='compare':
            from .reconcile import compare_monthly_hs6,chart_csv
            report=compare_monthly_hs6(vault,args.hs,args.base,args.comparison)
            if report['status']=='derived' and args.csv:
                args.csv.parent.mkdir(parents=True,exist_ok=True)
                args.csv.write_text(chart_csv(report),encoding='utf-8')
            output={k:v for k,v in report.items() if k!='rows'}
            output['matched_pairs']=len(report['rows'])
            if args.csv and report['status']=='derived':output['ggplot2_csv']=str(args.csv)
            elif args.csv:output['ggplot2_csv']=None
        elif args.command=='export':
            if not any(r[0]==args.source for r in vault.conn.execute('SELECT source_id FROM sources')):raise ValueError('source not ingested')
            records=vault.current_records(args.source)
            args.out.parent.mkdir(parents=True,exist_ok=True)
            with args.out.open('w',newline='',encoding='utf-8') as stream:
                w=csv.writer(stream)
                w.writerow(['source_id','source_sha256','observation_type','record_key','provenance','payload_json'])
                for r in records:w.writerow([r['source_id'],r['sha256'],r['observation_type'],r['key'],r['provenance'],json.dumps(r['data'],sort_keys=True)])
            output={'exported':len(records),'path':str(args.out),'note':'typed observations with source digests; not merged sources'}
        else:
            spec=spec_from_args(args);scope=get_scope(args,spec)
            if args.command=='fetch':result=fetch(vault,spec,scope)
            elif args.command=='replay':result=replay(vault,spec,args.sha256,scope)
            else:result=ingest_bytes(vault,spec,args.file.read_bytes(),source_url(spec,**scope),scope)
            output={**result,'source':spec.source_id,'provenance':spec.provenance}
        print(json.dumps(output,indent=2))
        return 2 if isinstance(output,dict) and output.get('status') in ('quarantined','unavailable','source_conflict') else 0
    except (ValueError,OSError) as e:
        print(f'error: {e}',file=sys.stderr)
        return 2
    finally:vault.close()

if __name__=='__main__':raise SystemExit(main())
