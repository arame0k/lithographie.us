"""Typed evidence queries for real port/HS6 flows, not speculative BOL graphs."""
from census_port_hs6 import quarter_routes


def port_corridors(conn,year,hs_prefix,flow,top=20):
    """A trade corridor is an aggregate port/country/commodity pairing, not a shipment."""
    if not (1<=top<=100):raise ValueError('top must be between 1 and 100')
    quarter=quarter_routes(conn,year,hs_prefix,flow,limit=top)
    archive_rows=conn.execute(
        "SELECT period,sha256,source_url,layout_url,selection,physical_rows,stored_rows "
        "FROM port_hs6_archives WHERE period IN (?,?,?) AND flow=? ORDER BY period",
        (*(year+f'{m:02d}' for m in (1,2,3)),flow)).fetchall()
    source_archives=[dict(zip(('period','sha256','source_url','layout_url','selection','physical_rows','stored_rows'),r)) for r in archive_rows]
    base={'source_archives':source_archives,'preset':'country_to_customs_port' if flow=='M' else 'customs_port_to_destination',
          'year':year,'flow':flow,'hs_prefix':hs_prefix,'evidence_level':'observed_aggregate',
          'months':quarter['month_ids'],'coverage_complete':quarter['coverage_complete'],
          'unit':'nominal USD','claims_excluded':['company','carrier','vessel','bill_of_lading']}
    if not quarter['coverage_complete']:
        return {**base,'status':'unavailable','reason':'incomplete monthly archive coverage or filtered source',
                'edges':[],'nodes':[],'total_value_usd':None,'unshown_value_usd':None,'mode_value_usd':None}
    rows=quarter['routes']
    edges=[];nodes={}
    for r in rows:
        country='country:'+r['country_code'];port='port:'+r['port_code']
        source,target=(country,port) if flow=='M' else (port,country)
        nodes[country]={'id':country,'kind':'census_country_code','code':r['country_code']}
        nodes[port]={'id':port,'kind':'us_customs_port_code','code':r['port_code']}
        edges.append({'source':source,'target':target,'value_usd':r['value_usd'],
                      'source_type':'customs_aggregate','flow':flow,'hs_prefix':hs_prefix,
                      'port_code':r['port_code'],'country_code':r['country_code'],
                      'scope':'Q1 sum of monthly HS6 observations'})
    where='period IN (?,?,?) AND flow=? AND substr(hs6,1,?)=?'
    params=(*(year+f'{x:02d}' for x in (1,2,3)),flow,len(hs_prefix),hs_prefix)
    mode=conn.execute('SELECT COALESCE(SUM(air_value_usd),0),COALESCE(SUM(vessel_value_usd),0),COALESCE(SUM(container_value_usd),0) FROM port_hs6 WHERE '+where,params).fetchone()
    return {**base,'status':'observed','reason':None,'edges':edges,'nodes':list(nodes.values()),
            'total_value_usd':quarter['total_usd'],
            'unshown_value_usd':quarter['total_usd']-sum(e['value_usd'] for e in edges),
            'mode_value_usd':{'air':mode[0],'vessel':mode[1],
                              'containerized_within_vessel':mode[2]},
            'note':'containerized value is a vessel subset; do not add it to vessel value'}


def compare_quarters(conn,base_year,comparison_year,hs_prefix,flow):
    """Like-for-like reported values; no causal or supplier-risk interpretation."""
    a=quarter_routes(conn,base_year,hs_prefix,flow,limit=1)
    b=quarter_routes(conn,comparison_year,hs_prefix,flow,limit=1)
    out={'base_year':base_year,'comparison_year':comparison_year,'hs_prefix':hs_prefix,'flow':flow,
         'scope':'US Census monthly port HS6; Q1 matched periods',
         'base_months':a['month_ids'],'comparison_months':b['month_ids']}
    if not a['coverage_complete'] or not b['coverage_complete']:
        return {**out,'status':'unavailable','reason':'both quarters need complete unfiltered monthly archives',
                'base_usd':None,'comparison_usd':None,'change_usd':None,'change_pct':None}
    x=a['total_usd'];y=b['total_usd']
    return {**out,'status':'derived','reason':None,'base_usd':x,'comparison_usd':y,'change_usd':y-x,
            'change_pct':100*(y-x)/x if x else None,
            'interpretation':'change in reported nominal trade value; not proof of cause or physical volume'}


def main():
    import argparse,json,sqlite3
    from pathlib import Path
    cli=argparse.ArgumentParser(description=__doc__)
    cli.add_argument('--db',type=Path,default=Path(__file__).resolve().parent/'lithographie.sqlite')
    cli.add_argument('--hs',required=True)
    cli.add_argument('--flow',choices=('M','X'),required=True)
    cli.add_argument('--top',type=int,default=20)
    cli.add_argument('--out',type=Path)
    mode=cli.add_mutually_exclusive_group(required=True)
    mode.add_argument('--year')
    mode.add_argument('--compare',nargs=2,metavar=('BASE_YEAR','COMPARISON_YEAR'))
    a=cli.parse_args()
    conn=sqlite3.connect(a.db)
    try:
        result=(port_corridors(conn,a.year,a.hs,a.flow,a.top) if a.year else
                compare_quarters(conn,a.compare[0],a.compare[1],a.hs,a.flow))
    finally:conn.close()
    result_json=json.dumps(result,indent=2)
    if a.out:a.out.write_text(result_json)
    else:print(result_json)
if __name__=='__main__':main()
