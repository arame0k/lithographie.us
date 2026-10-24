"""Format-specific parsing, retaining field semantics and coverage contracts."""
from decimal import Decimal,InvalidOperation
from html.parser import HTMLParser
import json
import re


def _decimal(value,field):
    try:
        if isinstance(value,bool) or value is None:raise ValueError()
        n=Decimal(str(value))
        if not n.is_finite() or n<0:raise ValueError()
        return format(n,'f')
    except (ValueError,InvalidOperation,TypeError):raise ValueError(f'invalid {field}') from None

def _json(raw):
    try:return json.loads(raw.decode('utf-8'))
    except (ValueError,UnicodeError) as e:raise ValueError('invalid UTF-8 JSON') from e

def parse_comtrade_world(raw,scope):
    payload=_json(raw)
    if not isinstance(payload,dict) or payload.get('error') not in ('',None):raise ValueError('Comtrade API returned an error')
    data=payload.get('data')
    if not isinstance(data,list):raise ValueError('Comtrade data array missing')
    count=payload.get('count',len(data))
    if type(count)!=int or count>=500 or count!=len(data):raise ValueError('API row count is truncated or inconsistent')
    if len(data)!=1:raise ValueError('expected precisely one world aggregate; empty or ambiguous API response')
    item=data[0]
    if not isinstance(item,dict):raise ValueError('invalid Comtrade observation')
    expected={'period':scope.get('period'),'cmdCode':scope.get('hs'),'flowCode':scope.get('flow'),'reporterCode':'842','partnerCode':'0'}
    for field,val in expected.items():
        if val is None or str(item.get(field))!=val:raise ValueError(f'Comtrade scope mismatch: {field}')
    val=_decimal(item.get('primaryValue'),'primaryValue')
    weight=item.get('netWgt')
    net=_decimal(weight,'netWgt') if weight is not None else None
    return [{'key':f"{scope['period']}:{scope['hs']}:{scope['flow']}:842:0",
      'type':'trade_statistic_world','data':{'period':scope['period'],'hs_code':scope['hs'],
      'flow':scope['flow'],'reporter_m49':'842','partner_m49':'0','value_usd':val,
      'net_weight_kg':net,'is_quantity_estimated':item.get('isQtyEstimated'),
      'is_net_weight_estimated':item.get('isNetWgtEstimated'),
      'is_reported':item.get('isReported'), 'is_aggregate':item.get('isAggregate'),
      'classification':str(item.get('classificationCode') or 'HS (edition not established)'),
      'source_granularity':'Comtrade world partner aggregate; no port / company / shipment'}}]

class _HTMLCountryParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.stack = []
        self.tables = []

    def handle_starttag(self, tag, attrs):
        if tag == 'table':
            self.stack.append({'rows': [], 'cells': [], 'cell': None})
        elif self.stack and tag == 'tr':
            self.stack[-1]['cells'] = []
        elif self.stack and tag in ('td', 'th'):
            self.stack[-1]['cell'] = ''

    def handle_data(self, text):
        if self.stack and self.stack[-1]['cell'] is not None:
            self.stack[-1]['cell'] += text

    def handle_endtag(self, tag):
        if not self.stack:
            return
        table = self.stack[-1]
        if tag in ('td', 'th') and table['cell'] is not None:
            table['cells'].append(' '.join(table['cell'].split()))
            table['cell'] = None
        elif tag == 'tr' and table['cells']:
            table['rows'].append(table['cells'])
            table['cells'] = []
        elif tag == 'table':
            self.tables.append(self.stack.pop()['rows'])

def parse_html_country_codes(raw,scope):
    try:html=raw.decode('utf-8','strict')
    except UnicodeError as e:raise ValueError('HTML is not UTF-8') from e
    p=_HTMLCountryParser();p.feed(html)
    rows=[];seen=set();header_ok=False
    for table in p.tables:
        has_header=any(len(row)>=3 and row[0].strip().lower()=='name' and
               row[1].strip().lower().startswith('country code') and
               row[2].strip().lower().startswith('iso code') for row in table)
        if not has_header:
            continue
        header_ok=True
        for row in table:
            if len(row)<3:continue
            name,code,iso=row[:3]
            if not re.fullmatch(r'\d{4}',code) or not re.fullmatch(r'[A-Za-z]{2}',iso):continue
            if code in seen:raise ValueError('duplicate Census country code')
            if not name:raise ValueError('empty country name')
            seen.add(code)
            rows.append({'key':code,'type':'geographic_reference','data':{
                'country_code':code,'display_name':name,'iso2':iso.upper(),
                'code_system':'US Census Schedule C; not UN M49'}})
    if not header_ok or not rows:raise ValueError('Schedule C table headings or code rows missing; webpage may have changed')
    return rows

def parse_gleif_entity(raw,scope):
    payload=_json(raw)
    item=payload.get('data') if isinstance(payload,dict) else None
    if not isinstance(item,dict) or item.get('type')!='lei-records':raise ValueError('not a GLEIF LEI record')
    a=item.get('attributes')
    if not isinstance(a,dict) or a.get('lei')!=scope.get('lei') or item.get('id')!=scope.get('lei'):
        raise ValueError('GLEIF LEI scope mismatch')
    entity=a.get('entity'); entity=entity if isinstance(entity,dict) else {}
    name=entity.get('legalName');name=name.get('name') if isinstance(name,dict) else None
    if not isinstance(name,str) or not name.strip():raise ValueError('GLEIF legal name missing')
    registration=a.get('registration');registration=registration if isinstance(registration,dict) else {}
    return [{'key':a['lei'],'type':'legal_entity_reference','data':{
        'lei':a['lei'],'legal_name':name.strip(),'registration_status':registration.get('status'),
        'identity_link_to_trade_records':'not_established'}}]

def parse_census_browser_extract(raw,scope):
    from research.workflow import validate_extract,SCHEMA_VERSION
    payload=_json(raw)
    r=validate_extract(payload)
    if not r['archive_full_scan'] or not r['matching_rows_complete']:
        raise ValueError('browser extract does not assert complete HS coverage')
    if scope.get('period')!=r['period']:raise ValueError('browser extract period scope mismatch')
    if r.get('schema_version')!=SCHEMA_VERSION:raise ValueError('unknown extraction schema')
    # The independent scan manifest supplies source hashes, total archive row counts,
    # and four different reported-value checksums. Local extract validation must
    # never be allowed to rewrite these assertions.
    from pathlib import Path
    from research.workflow import load_browser_summary
    manifest=load_browser_summary(Path(__file__).resolve().parents[1]/'research/data/browser_scanned_totals.json')
    reference=next((x for x in manifest['archives'] if x['period']==r['period']),None)
    if (reference is None or reference['source_sha256']!=r['source_sha256'] or
        reference['source_url']!=r['source_url'] or
        reference['archive_physical_rows']!=r['archive_physical_rows'] or
        reference['matching_row_count']!=r['matching_row_count'] or
        reference['total_usd']!=r['total_usd']):
        raise ValueError('browser extract source scope or checksum does not match independent scan manifest')
    for measure in ('air_value_usd','vessel_value_usd','container_value_usd'):
        if sum(row[measure] for row in r['rows'])!=reference[measure]:
            raise ValueError(f'browser extract {measure} does not match independent source scan')
    return [{'key':f"{r['period']}:{r['hs6']}:{row['country_code']}:{row['port_code']}",
      'type':'customs_port_aggregate','data':{
          'period':r['period'],'hs6':r['hs6'],'country_code':row['country_code'],
          'port_code':row['port_code'],
          **{k:row[k] for k in ('value_usd','air_value_usd','vessel_value_usd','container_value_usd')},
          'archive_sha256_reported':r['source_sha256'],
          'verification':'browser_full_scan_extract; original ZIP bytes not stored'}} for row in r['rows']]
