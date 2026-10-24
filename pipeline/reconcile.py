"""Reproducible comparison from *current, explicitly typed* evidence.

Only match months with the same calendar month, measure, HS classification and
acquisition tier. Never treat a missing port-country row as zero.
"""
import csv,io,re,sqlite3


def _raw_archives(vault,periods,hs6):
    try:
        keys=vault.conn.execute('''SELECT period,sha256,source_url,physical_rows,stored_rows,selection
          FROM port_hs6_archives WHERE flow='M' AND period IN (?,?)''',periods).fetchall()
    except sqlite3.OperationalError:return None
    if len(keys)!=2 or any(x[5]!='complete_file' or x[3]!=x[4] for x in keys):return None
    raws=[]
    for period in periods:
        records=vault.conn.execute('''SELECT country_code,port_code,value_usd,air_value_usd,
          vessel_value_usd,container_value_usd FROM port_hs6
          WHERE flow='M' AND period=? AND hs6=?''',(period,hs6)).fetchall()
        metadata=next(x for x in keys if x[0]==period)
        raws.append(({'source_id':'census_port_hs6_imports','period':period,'sha256':metadata[1],
                      'source_url':metadata[2],'physical_rows':metadata[3],
                      'original_zip_stored':True},
                    [dict(zip(('country_code','port_code','value_usd','air_value_usd','vessel_value_usd','container_value_usd'),row)) for row in records]))
    return raws

def _browser_extracts(vault,periods,hs6):
    latest=vault.current_records('census_browser_hs6_extract')
    grouped=[]
    for period in periods:
        rows=[r for r in latest if r['observation_type']=='customs_port_aggregate'
              and r['data']['period']==period and r['data']['hs6']==hs6]
        if not rows:return None
        sha={r['sha256'] for r in rows}; archive_hash={r['data']['archive_sha256_reported'] for r in rows}
        if len(sha)!=1 or len(archive_hash)!=1:raise ValueError('mixed evidence revisions in one month')
        grouped.append(({'source_id':'census_browser_hs6_extract','period':period,'sha256':next(iter(sha)),
                'reported_zip_sha256':next(iter(archive_hash)),'original_zip_stored':False},
                [r['data'] for r in rows]))
    return grouped

def _fingerprint_rows(rows):
    return {(r['country_code'],r['port_code']):tuple(r[x] for x in
             ('value_usd','air_value_usd','vessel_value_usd','container_value_usd')) for r in rows}

def compare_monthly_hs6(vault,hs6,base,comparison):
    if not re.fullmatch(r'\d{6}',hs6):raise ValueError('invalid HS6')
    if any(not re.fullmatch(r'20\d{2}(0[1-9]|1[0-2])',p) for p in (base,comparison)) or base>=comparison:
        raise ValueError('invalid periods or order')
    if base[4:]!=comparison[4:]:raise ValueError('different calendar month')
    periods=(base,comparison)
    source=_raw_archives(vault,periods,hs6)
    browser=_browser_extracts(vault,periods,hs6)
    if source is not None and browser is not None:
        if any(_fingerprint_rows(source[i][1])!=_fingerprint_rows(browser[i][1]) for i in (0,1)):
            return {'status':'source_conflict','reason':'Original archive rows disagree with browser-scanned extracts; review revisions before ranking','rows':[]}
    if source is not None:
        tier='original_census_zip'; chosen=source
    elif browser is not None:
        tier='browser_verified_extract; original ZIP bytes not stored';chosen=browser
    else:return {'status':'unavailable','reason':'Both complete matching-month HS6 scopes are required','rows':[]}
    a,b=chosen
    def keyed(rows):
        index={}
        for r in rows:
            key=(r['port_code'],r['country_code'])
            if key in index:raise ValueError('duplicate logical port-country key')
            index[key]=r
        return index
    left,right=keyed(a[1]),keyed(b[1])
    keys=left.keys()|right.keys()
    output=[]
    for port,country in keys:
        x=left.get((port,country));y=right.get((port,country))
        av=x['value_usd'] if x is not None else None
        bv=y['value_usd'] if y is not None else None
        output.append({'port_code':port,'country_code':country,'base_usd':av,'comparison_usd':bv,
            'change_usd':bv-av if av is not None and bv is not None else None,
            'base_present':x is not None,'comparison_present':y is not None})
    output.sort(key=lambda r:(-max(r['base_usd'] or 0,r['comparison_usd'] or 0),r['port_code'],r['country_code']))
    sumfield=lambda rows,key:sum(r[key] for r in rows)
    values=[sumfield(period_rows,'value_usd') for _,period_rows in chosen]
    return {'status':'derived','hs6':hs6,'flow':'M','base':base,'comparison':comparison,
        'evidence_tier':tier,'observation_type':'customs_port_aggregate','unit':'nominal USD',
        'base_usd':values[0],'comparison_usd':values[1],
        'change_usd':values[1]-values[0],
        'change_pct':round(100*(values[1]-values[0])/values[0],2) if values[0] else None,
        'base_vessel_usd':sumfield(a[1],'vessel_value_usd'),
        'comparison_vessel_usd':sumfield(b[1],'vessel_value_usd'),
        'base_rows':len(a[1]),'comparison_rows':len(b[1]),'rows':output,
        'sources':[a[0],b[0]],'unknowns':['shipment parties','carrier','vessel','ultimate destination','causal explanations']}

def chart_csv(result):
    if result.get('status')!='derived':raise ValueError('complete matched period evidence required')
    stream=io.StringIO();w=csv.writer(stream)
    w.writerow(['period','port_code','country_code','value_usd'])
    for row in result['rows']:
        for period,column in ((result['base'],'base_usd'),(result['comparison'],'comparison_usd')):
            w.writerow([period,row['port_code'],row['country_code'],
                row[column] if row[column] is not None else ''])
    return stream.getvalue()
