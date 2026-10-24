#!/usr/bin/env python3
"""Verify each embedded world observation against a fresh official UN Comtrade raw response.

This is a comparison, not a silent update. Raw revisions are retained with SHA256.
UN Comtrade public preview permits limited records. Request partnerCode=0 to avoid
truncating world aggregates among partner observations.
"""
import argparse
from datetime import datetime,timezone
import hashlib,json
from pathlib import Path
import re
import time
from urllib.parse import urlencode
from urllib.request import Request,urlopen

HERE=Path(__file__).resolve().parent
BASE='https://comtradeapi.un.org/public/v1/preview/C/M/HS'

def preview_world_url(period,hs,flow):
    if not re.fullmatch(r'20\d{2}(0[1-9]|1[0-2])',period):raise ValueError('invalid period')
    if not re.fullmatch(r'\d{4}',hs) or flow not in ('M','X'):raise ValueError('invalid HS or flow')
    return BASE+'?'+urlencode({'period':period,'reporterCode':842,'partnerCode':0,'cmdCode':hs,'flowCode':flow,'maxRecords':500})

def audit_response(expected,raw):
    issues=[]
    if raw.get('error') not in ('',None):issues.append('api_error')
    result=[r for r in raw.get('data',[]) if str(r.get('period'))==expected['period']
            and str(r.get('cmdCode'))==expected['hs']
            and str(r.get('flowCode'))==expected['flow']
            and str(r.get('partnerCode'))=='0'
            and str(r.get('reporterCode'))=='842']
    if len(result)==0:issues.append('world_row_missing')
    if len(result)>1:issues.append('duplicate_world_rows')
    actual=None
    if len(result)==1:
        r=result[0]
        val=r.get('primaryValue')
        weight=r.get('netWgt')
        actual={'value_usd':int(val) if val is not None else None,
                'net_weight_kg':int(weight) if weight is not None and float(weight)>0 else None,
                'qty_estimated':r.get('isQtyEstimated')}
        if actual['value_usd']!=expected['value_usd']:issues.append('trade_value_changed')
        if actual['net_weight_kg']!=expected['net_weight_kg']:issues.append('net_weight_changed')
        if actual['qty_estimated']!=expected['qty_estimated']:issues.append('qty_estimation_flag_changed')
    return {'key':f"{expected['period']}:{expected['hs']}:{expected['flow']}",
            'match':not issues,'problems':issues,'expected':expected,'actual':actual}

def audit_snapshot(snapshot,raw_dir):
    results=[];raw_dir=Path(raw_dir)
    for expected in snapshot['world']:
        fname=f"{expected['period']}_{expected['hs']}_{expected['flow']}.json"
        p=raw_dir/fname
        if not p.exists():
            results.append({'key':fname,'match':False,'problems':['raw_response_missing']})
            continue
        blob=p.read_bytes()
        r=audit_response(expected,json.loads(blob))
        r['raw_sha256']=hashlib.sha256(blob).hexdigest();r['raw_path']=fname
        results.append(r)
    return {'status':'verified' if all(r['match'] for r in results) else 'unverified',
            'matches':sum(r['match'] for r in results),'expected':len(results),
            'results':results}

def retrieve(snapshot,raw_dir,delay=1.2):
    """Sequential and polite (at least one second between remote requests)."""
    raw_dir=Path(raw_dir);raw_dir.mkdir(parents=True,exist_ok=True)
    found=[]
    for idx,x in enumerate(snapshot['world']):
        dest=raw_dir/f"{x['period']}_{x['hs']}_{x['flow']}.json"
        if dest.exists():continue
        if idx:time.sleep(max(1.05,delay))
        url=preview_world_url(x['period'],x['hs'],x['flow'])
        with urlopen(Request(url,headers={'User-Agent':'Lithographie research, observed data audit'}),timeout=45) as response:
            blob=response.read(4_000_001)
        if len(blob)>4_000_000:raise ValueError('response size exceeds limit')
        raw=json.loads(blob)
        # Always retain valid JSON for revision inspection, even if numbers differ.
        temp=dest.with_suffix('.partial')
        temp.write_bytes(blob);temp.replace(dest)
        found.append({'url':url,'file':str(dest),'match':audit_response(x,raw)['match']})
    return found

def main():
    a=argparse.ArgumentParser(description=__doc__)
    a.add_argument('--snapshot',type=Path,default=HERE/'monthly-snapshot.json')
    a.add_argument('--raw-dir',type=Path,default=HERE/'raw-comtrade')
    a.add_argument('--fetch',action='store_true',help='fetch missing raw observations (requires internet)')
    a.add_argument('--out',type=Path,default=HERE/'comtrade-audit.json')
    args=a.parse_args()
    snapshot=json.loads(args.snapshot.read_text())
    if args.fetch: retrieve(snapshot,args.raw_dir)
    result=audit_snapshot(snapshot,args.raw_dir)
    result['generated_utc']=datetime.now(timezone.utc).isoformat()
    args.out.write_text(json.dumps(result,indent=2))
    print(json.dumps({'status':result['status'],'matches':result['matches'],'expected':result['expected'],'output':str(args.out)}))
    if result['status']!='verified':raise SystemExit(2)
if __name__=='__main__':main()
