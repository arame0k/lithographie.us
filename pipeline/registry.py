"""Allowlisted source contracts. Configs describe meaning, not assumed cross-source joins."""
from dataclasses import dataclass
import re
from urllib.parse import urlencode

@dataclass(frozen=True)
class SourceSpec:
    source_id: str
    adapter: str
    method: str
    url: str
    observation_type: str
    period: str = ''
    max_bytes: int = 20_000_000
    provenance: str = 'direct_source'

CENSUS_EXTRACT_2024=SourceSpec('census_browser_hs6_extract','census_extract','browser_extract','https://www.census.gov/trade/downloads/2024/Port/im_hs6_m/PORTHS6MM2401.ZIP','customs_port_aggregate','202401',provenance='browser_full_scan_unbundled_zip')
CENSUS_EXTRACT_2025=SourceSpec('census_browser_hs6_extract','census_extract','browser_extract','https://www.census.gov/trade/downloads/2025/Port/im_hs6_m/PORTHS6MM2501.ZIP','customs_port_aggregate','202501',provenance='browser_full_scan_unbundled_zip')
CENSUS_BULK=SourceSpec('census_port_hs6_imports','census_zip','bulk_zip','https://www.census.gov/foreign-trade/data/PORTHS6MM.html','customs_port_aggregate',max_bytes=50_000_000,provenance='original_zip')
COMTRADE_WORLD=SourceSpec('comtrade_world_monthly','comtrade_world','api_json','https://comtradeapi.un.org/public/v1/preview/C/M/HS','trade_statistic_world',max_bytes=4_000_000)
CENSUS_COUNTRIES=SourceSpec('census_country_codes','census_country_html','html_scrape','https://www.census.gov/foreign-trade/schedules/c/countrycode.html','geographic_reference',max_bytes=3_000_000)
# Read-only browser-captured excerpts. These are NOT full wire responses or entire HTML pages.
CENSUS_COUNTRY_BROWSER_FRAGMENT=SourceSpec('census_country_browser_excerpt','census_country_html',
    'browser_extract','https://www.census.gov/foreign-trade/schedules/c/countrycode.html',
    'geographic_reference',provenance='browser_html_excerpt; not full country register')
COMTRADE_WORLD_BROWSER=SourceSpec('comtrade_world_browser_capture','comtrade_world',
    'browser_extract','https://comtradeapi.un.org/public/v1/preview/C/M/HS',
    'trade_statistic_world',provenance='browser_returned_api_json; original HTTP bytes not archived')
GLEIF_LEI=SourceSpec('gleif_lei_record','gleif_record','api_json','https://api.gleif.org/api/v1/lei-records/','legal_entity_reference',max_bytes=4_000_000)
ALL_SOURCES=(CENSUS_BULK,CENSUS_EXTRACT_2024,CENSUS_EXTRACT_2025,COMTRADE_WORLD,CENSUS_COUNTRIES,GLEIF_LEI,CENSUS_COUNTRY_BROWSER_FRAGMENT,COMTRADE_WORLD_BROWSER)
SOURCES={i.source_id:i for i in ALL_SOURCES if i.adapter!='census_extract'}

def source_url(spec,**scope):
    if spec.adapter=='census_extract':return spec.url
    if spec.adapter=='census_country_html':return spec.url
    if spec.adapter=='comtrade_world':
        period,hs,flow=scope.get('period',''),scope.get('hs',''),scope.get('flow','')
        if not re.fullmatch(r'20\d{2}(0[1-9]|1[0-2])',period) or not re.fullmatch(r'\d{2,6}',hs) or flow not in ('M','X'):
            raise ValueError('Comtrade scope requires a month, HS2-HS6 and flow M/X')
        # Public preview requires lowercase reportercode (different from authenticated API).
        return spec.url+'?'+urlencode({'reportercode':'842','partnerCode':'0','period':period,'cmdCode':hs,'flowCode':flow,'maxRecords':'500'})
    if spec.adapter=='gleif_record':
        lei=scope.get('lei','')
        if not re.fullmatch('[A-Z0-9]{20}',lei):raise ValueError('invalid LEI')
        return spec.url+lei
    if spec.adapter=='census_zip':
        from engine.census_port_hs6 import source_url as census_url
        return census_url(scope.get('period',''),'M')
    raise ValueError('unrecognized source')
