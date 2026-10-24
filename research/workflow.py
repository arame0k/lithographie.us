"""Strict observed-aggregate comparison contract for Lithographie's first research workflow.

A complete HS6 extraction is not the whole Census monthly archive. It is evidence
of every matching record from an explicitly scanned, unfiltered archive. Never
present an incomplete spot check as an exhaustive group of flows.
"""
import csv
import io
import json
import re
from pathlib import Path

SCHEMA_VERSION='lithographie.census-port-hs6.extract.v1'
REQUIRED_ROW={'country_code','port_code','value_usd','air_value_usd','vessel_value_usd','container_value_usd'}

def validate_extract(raw):
    r=dict(raw)
    for key in ('period','flow','hs6','source_url','source_sha256','archive_full_scan','matching_rows_complete','archive_physical_rows','matching_row_count','total_usd','rows'):
        if key not in r:raise ValueError(f'missing {key}')
    if not re.fullmatch(r'20\d{2}(0[1-9]|1[0-2])',r['period']):raise ValueError('invalid period')
    if r['flow']!='M' or not re.fullmatch(r'\d{6}',r['hs6']):raise ValueError('invalid flow or HS6')
    if not r['source_url'].startswith('https://www.census.gov/'):raise ValueError('source must be official Census URL')
    if not re.fullmatch('[0-9a-f]{64}',r['source_sha256'] or ''):raise ValueError('missing archive sha256')
    for flag in ('archive_full_scan','matching_rows_complete'):
        if not isinstance(r[flag],bool):raise ValueError('invalid coverage flag')
    if type(r['archive_physical_rows']) is not int or r['archive_physical_rows']<1:raise ValueError('invalid scanned archive count')
    if type(r['matching_row_count']) is not int or r['matching_row_count']!=len(r['rows']):raise ValueError('row count mismatch')
    if type(r['total_usd']) is not int or r['total_usd']<0:raise ValueError('invalid total')
    values=set();total=0;ports=[]
    for item in r['rows']:
        if not REQUIRED_ROW.issubset(item):raise ValueError('missing row field')
        for code in ('country_code','port_code'):
            if not isinstance(item[code],str) or not re.fullmatch(r'\d{4}',item[code]):raise ValueError('code must remain four characters')
        identity=(item['country_code'],item['port_code'])
        if identity in values:raise ValueError('duplicate port-country combination')
        values.add(identity)
        for field in ('value_usd','air_value_usd','vessel_value_usd','container_value_usd'):
            if type(item[field]) is not int or item[field]<0:raise ValueError('invalid nonnegative integral USD value')
        if item['container_value_usd']>item['vessel_value_usd']:raise ValueError('container value exceeds vessel value')
        if item['vessel_value_usd']+item['air_value_usd']>item['value_usd']:raise ValueError('air + vessel exceeds monthly total')
        total+=item['value_usd'];ports.append(item)
    if total!=r['total_usd']:raise ValueError(f'source total mismatch: {total} vs {r["total_usd"]}')
    if len(ports)>r['archive_physical_rows']:raise ValueError('matching rows exceed archive length')
    return r

def load_extracts(directory):
    ret=[]
    for path in sorted(Path(directory).glob('*.json')):
        data=json.loads(path.read_text())
        # Explicitly exclude older five-row spotcheck; it uses a separate shape.
        if data.get('schema_version')==SCHEMA_VERSION:
            ret.append(validate_extract(data))
    return ret

def build_comparison(extracts,hs6,base,comparison):
    if not re.fullmatch(r'\d{6}',hs6):raise ValueError('HS must be six digits')
    if not re.fullmatch(r'20\d{2}(0[1-9]|1[0-2])',base) or not re.fullmatch(r'20\d{2}(0[1-9]|1[0-2])',comparison):raise ValueError('bad period')
    if base[4:]!=comparison[4:]:raise ValueError('not matched calendar months')
    selected={}
    for raw in extracts:
        r=validate_extract(raw)
        if r['hs6']==hs6 and r['period'] in (base,comparison):
            if r['period'] in selected:raise ValueError('duplicate period evidence')
            selected[r['period']]=r
    contract={'hs6':hs6,'flow':'M','base':base,'comparison':comparison,
              'unit':'nominal USD','unit_scope':'monthly general imports; customs port of unlading and country of origin',
              'excludes':['shipment','carrier','company','vessel identity','causal explanation']}
    if (base not in selected or comparison not in selected or
        any(not selected[period]['archive_full_scan'] or not selected[period]['matching_rows_complete']
            for period in (base,comparison))):
        return {**contract,'status':'unavailable','reason':'Both periods require a complete scan of the official ZIP and all matching HS6 rows.','port_rows':[],'sources':list(selected.values())}
    a,b=selected[base],selected[comparison]
    port_ids={(r['port_code'],r['country_code']) for s in (a,b) for r in s['rows']}
    keyed={period:{(x['port_code'],x['country_code']):x for x in selected[period]['rows']} for period in (base,comparison)}
    port_rows=[]
    for port,country in port_ids:
        record_a=keyed[base].get((port,country))
        record_b=keyed[comparison].get((port,country))
        va=record_a['value_usd'] if record_a else None
        vb=record_b['value_usd'] if record_b else None
        port_rows.append({'port_code':port,'country_code':country,'base_usd':va,'comparison_usd':vb,
                          'base_present':record_a is not None,'comparison_present':record_b is not None,
                          'delta_usd':vb-va if va is not None and vb is not None else None})
    port_rows.sort(key=lambda x:(-max(x['base_usd'] or 0,x['comparison_usd'] or 0),x['port_code'],x['country_code']))
    x,y=a['total_usd'],b['total_usd']
    return {**contract,'status':'derived','base_usd':x,'comparison_usd':y,'change_usd':y-x,
            'change_pct':round(100*(y-x)/x,2) if x else None,
            'port_rows':port_rows,'sources':[{'period':s['period'],'source_url':s['source_url'],
                         'source_sha256':s['source_sha256'],'archive_physical_rows':s['archive_physical_rows'],
                         'matching_row_count':s['matching_row_count'],'hs6':s['hs6'],
                         'schema_version':s.get('schema_version',SCHEMA_VERSION)} for s in (a,b)]}

def load_browser_summary(path):
    payload=json.loads(Path(path).read_text())
    if payload.get('schema_version')!='lithographie.census-port-hs6.summary.v1':
        raise ValueError('not a Census browser-scan summary')
    if payload.get('hs6')!='760110' or payload.get('flow')!='M':raise ValueError('unexpected source scope')
    archives=payload['archives']
    if len(archives)!=2 or set(x['period'] for x in archives)!={'202401','202501'}:raise ValueError('unexpected matched periods')
    for x in archives:
        if not re.fullmatch('[0-9a-f]{64}',x.get('source_sha256','')):raise ValueError('missing archive digest')
        if not x['source_url'].startswith('https://www.census.gov/trade/downloads/'):
            raise ValueError('unsupported source')
        for k in ('archive_bytes','archive_physical_rows','matching_row_count','total_usd','air_value_usd','vessel_value_usd','container_value_usd'):
            if type(x[k]) is not int or x[k]<0:raise ValueError(f'invalid {k}')
        if x['archive_physical_rows']<x['matching_row_count']:raise ValueError('invalid archive coverage')
        if x['container_value_usd']>x['vessel_value_usd'] or x['air_value_usd']+x['vessel_value_usd']>x['total_usd']:
            raise ValueError('invalid transport subtotal')
    return payload

def build_summary_comparison(payload):
    x=load_browser_summary(payload) if isinstance(payload,(str,Path)) else payload
    a,b=sorted(x['archives'],key=lambda v:v['period'])
    v,w=a['total_usd'],b['total_usd']
    return {'status':'summary_only','hs6':x['hs6'],'base':'202401','comparison':'202501','base_usd':v,
            'comparison_usd':w,'change_usd':w-v,'change_pct':round(100*(w-v)/v,2) if v else None,
            'port_rows':[],'sources':x['archives'],
            'reason':'Monthly HS6 totals verified from full source scans. Complete local port-country rows not yet available.',
            'unit':'nominal USD','excludes':['shipment','carrier','company','vessel identity','port ranking']}

def convert_browser_csv(csv_file,manifest_file):
    """Rebuild two source-bound HS6 extracts; require independent checksums for ALL measures."""
    manifest=load_browser_summary(manifest_file)
    archives={a['period']:a for a in manifest['archives']}
    grouped={k:[] for k in archives}
    with open(csv_file,newline='',encoding='utf-8') as stream:
        reader=csv.DictReader(stream)
        wanted={'period','country_code','port_code','value_usd','air_value_usd','vessel_value_usd','container_value_usd'}
        if set(reader.fieldnames or ())!=wanted:raise ValueError('unexpected evidence CSV columns')
        for row in reader:
            period=row['period'].replace('-','')
            if period not in archives:raise ValueError('unexpected month in source extract')
            entry={k:row[k] for k in ('country_code','port_code')}
            for k in ('value_usd','air_value_usd','vessel_value_usd','container_value_usd'):
                if not re.fullmatch(r'\d+',row[k]):raise ValueError(f'invalid {k}')
                entry[k]=int(row[k])
            grouped[period].append(entry)
    validated={}
    for period,items in grouped.items():
        source=archives[period]
        for field in ('value_usd','air_value_usd','vessel_value_usd','container_value_usd'):
            observed=sum(row[field] for row in items)
            expected=source['total_usd'] if field=='value_usd' else source[field]
            if observed!=expected:
                raise ValueError(f'checksum mismatch {period} {field}: rows {observed}, source {expected}')
        extracted={'schema_version':SCHEMA_VERSION,'period':period,'flow':'M','hs6':manifest['hs6'],
                   'source_url':source['source_url'],'source_sha256':source['source_sha256'],
                   'archive_full_scan':True,'matching_rows_complete':True,
                   'archive_physical_rows':source['archive_physical_rows'],'matching_row_count':source['matching_row_count'],
                   'total_usd':source['total_usd'],'rows':items,
                   'extraction_note':'Browser-scanned official archive; SHA256 verified in browser. Original ZIP not bundled.'}
        validated[period]=validate_extract(extracted)
    return validated

def rows_to_csv(result):
    if result.get('status') not in ('derived','summary_only'):raise ValueError('chart input requires completed comparison')
    stream=io.StringIO();w=csv.writer(stream)
    w.writerow(['period','port_code','country_code','value_usd'])
    if result['status']=='summary_only':
        for period,key in ((result['base'],'base_usd'),(result['comparison'],'comparison_usd')):
            w.writerow([period,'ALL','ALL',result[key]])
        return stream.getvalue()
    for row in result['port_rows']:
        for period,key in ((result['base'],'base_usd'),(result['comparison'],'comparison_usd')):
            w.writerow([period,row['port_code'],row['country_code'],row[key] if row[key] is not None else ''])
    return stream.getvalue()
