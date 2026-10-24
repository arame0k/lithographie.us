"""Small read-only HTML research instrument; works without client-side JavaScript.

Install optional Unpoly to enhance navigation; HTML forms and links remain canonical.
No client-side calculation is authoritative.
"""
import html
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
from urllib.parse import parse_qs,urlparse
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from workflow import build_comparison,build_summary_comparison,load_browser_summary,load_extracts,rows_to_csv

HERE=Path(__file__).resolve().parent
DATA=HERE/'data'
SPOT=HERE.parent/'engine'/'census-browser-spotcheck.json'
BASE='202401';COMPARE='202501';HS='760110'

def esc(value):return html.escape(str(value),quote=True)
def money(n):return '—' if n is None else f'${n:,.0f}'
def pct(n):return '—' if n is None else f'{"▲" if n>=0 else "▼"} {abs(n):,.1f}%'
def delta(n):return 'NOT MATCHED' if n is None else f'{"▲" if n>=0 else "▼"} {money(abs(n))}'
def get_report():
    report=build_comparison(load_extracts(DATA),HS,BASE,COMPARE)
    if report['status']=='unavailable' and (DATA/'browser_scanned_totals.json').exists():
        return build_summary_comparison(load_browser_summary(DATA/'browser_scanned_totals.json'))
    return report
def spotcheck():
    if not SPOT.exists():return []
    payload=json.loads(SPOT.read_text())
    return payload['rows'] if payload.get('status')=='partial_observed_records' else []

def source_rows(report):
    if report['status'] not in ('derived','summary_only'):
        return '<p class="muted">Matched-month comparison is blocked until both complete sources are available.</p>'
    return ''.join(f'''<tr><td>{esc(r['period'])}</td><td>U.S. Census</td><td>{r['archive_physical_rows']:,}</td><td>{r['matching_row_count']:,}</td><td><code title="SHA256">{esc(r['source_sha256'][:18])}…</code></td><td><a href="{esc(r['source_url'])}" rel="noreferrer" target="_blank">SOURCE ▸</a></td></tr>''' for r in report['sources'])

def fragments(report,selected=None):
    ok=report['status'] in ('derived','summary_only');spot=spotcheck();months=f'{BASE[:4]} / 01   ◀▶   {COMPARE[:4]} / 01'
    if ok:
        change_value=report['change_usd']; summary=f'''<section class="metric-grid">
          <div class="metric"><label>2024 / JANUARY</label><strong>{money(report['base_usd'])}</strong><small>Observed · nominal USD</small></div>
          <div class="metric"><label>2025 / JANUARY</label><strong>{money(report['comparison_usd'])}</strong><small>Observed · nominal USD</small></div>
          <div class="metric"><label>CHANGE</label><strong class="{'positive' if change_value>=0 else 'negative'}">{pct(report['change_pct'])}</strong><small>{money(abs(change_value))} {'increase' if change_value>=0 else 'decrease'}</small></div>
        </section>'''
        rows=''.join(f'''<tr><td><a href="/evidence?port={esc(r['port_code'])}&country={esc(r['country_code'])}" up-target="#inspector" up-history="false">{esc(r['port_code'])}</a></td><td>{esc(r['country_code'])}</td><td class="number">{money(r['base_usd'])}</td><td class="number">{money(r['comparison_usd'])}</td><td class="number">{delta(r['delta_usd'])}</td></tr>''' for r in report['port_rows'][:30])
        if report['status']=='summary_only':
            rows='<tr><td colspan="5" class="muted">Port-country rows are not available locally. No corridor ranking.</td></tr>'
        graphic='<img class="chart" src="/plot.svg" alt="ggplot2 paired-period port origin comparison">' if shutil.which('Rscript') else '<div class="chart-unavailable"><span>GGPLOT2 RENDERER</span><b>R is not installed in this environment.</b><p>Verified records and comparisons remain available. Run with R and ggplot2 to generate the plot.</p><code>Rscript chart.R data.csv chart.svg</code></div>'
    else:
        summary='<section class="blocked"><span class="triangle">△</span><div><strong>COMPARISON UNAVAILABLE</strong><p>Full January 2024 and 2025 HS6 extracts are required. A five-row spot check is not a monthly total.</p></div></section>'
        rows='<tr><td colspan="5" class="muted">No ranking from partial evidence.</td></tr>'
        graphic='<div class="chart-unavailable"><span>GGPLOT2 RENDERER</span><b>Waiting for verified matching-month extracts.</b><p>No chart is generated from incomplete coverage.</p></div>'
    table=f'''<div class="section-title"><span>01 / PORT × ORIGIN</span><span>HS {HS} · IMPORT VALUE</span></div><div class="table-scroll"><table><thead><tr><th>PORT</th><th>ORIGIN</th><th class="number">2024 USD</th><th class="number">2025 USD</th><th class="number">CHANGE</th></tr></thead><tbody>{rows}</tbody></table></div>'''
    evidence=(f'''<div class="section-title"><span>02 / SOURCE RECORDS</span><span>SHA256 / ARCHIVE SCAN</span></div><div class="table-scroll"><table><thead><tr><th>MONTH</th><th>PROVIDER</th><th>ARCHIVE ROWS</th><th>MATCHED HS6</th><th>SHA256</th><th>LINK</th></tr></thead><tbody>{source_rows(report)}</tbody></table></div><p class="caption">Source ZIPs scanned in browser. 80 matching port-country rows are included. Original ZIP bytes are not bundled.</p>''' if ok else f'''<div class="section-title"><span>02 / VERIFIED SPOT CHECK</span><span>5 RECORDS · PARTIAL</span></div><div class="table-scroll"><table><thead><tr><th>MONTH</th><th>HS6</th><th>PORT</th><th>ORIGIN</th><th class="number">VALUE USD</th></tr></thead><tbody>{''.join(f"<tr><td>202501</td><td>{HS}</td><td>{esc(x['port_code'])}</td><td>{esc(x['country_code'])}</td><td class='number'>{money(x['value_usd'])}</td></tr>" for x in spot)}</tbody></table></div><p class="caption">Partial sample. Not included in totals, ranks, or charts. <a href="https://www.census.gov/foreign-trade/data/PORTHS6MM.html">Census archive ▸</a></p>''')
    panel=f'''<section id="workspace" class="workspace"><div class="eyebrow">RESEARCH / MATCHED PERIOD ANALYSIS</div><h1>Commodity comparison</h1><div class="summaryline">U.S. IMPORTS &nbsp;·&nbsp; HS {HS} &nbsp;·&nbsp; {months} &nbsp;·&nbsp; PORT AGGREGATES</div><form method="get" action="/" up-target="#workspace" up-history="true" class="toolbar"><div class="tabs"><span class="tab active">COMPARISON</span><a class="tab" href="/evidence" up-target="#inspector" up-history="false">EVIDENCE ▸</a></div><div class="selects"><label>COMMODITY<select name="hs"><option value="760110">760110 · Unwrought aluminum (not alloyed)</option></select></label><label>PERIOD<select name="period"><option value="jan">January 2024 / 2025</option></select></label><button type="submit">REFRESH ▸</button></div></form>{summary}<div class="section-title"><span>CHART / PORT-COUNTRY COMPARISON</span><span>R · GGPLOT2</span></div>{graphic}{table}{evidence}<p class="footnote">Observation: Census port by HS6 monthly import aggregates. No shipment, carrier, consignee, or vessel linkage.</p></section>'''
    if not selected:
        inspector='<div class="eyebrow">INSPECTOR / EVIDENCE</div><h2>Select a port</h2><p class="muted">Select a code in the comparison table to inspect its source values.</p>'
    else:
        port,country=selected
        match=next((r for r in report['port_rows'] if r['port_code']==port and r['country_code']==country),None)
        if match:
            raw=load_extracts(DATA)
            observed=[]
            for source in raw:
                record=next((v for v in source['rows'] if v['port_code']==port and v['country_code']==country),None)
                observed.append(f'''<div class="inspector-period">{esc(source['period'][:4])} / JANUARY</div>''' +
                    (f'''<div class="inspector-row">TOTAL <b>{money(record['value_usd'])}</b></div>
                       <div class="inspector-row">VESSEL <b>{money(record['vessel_value_usd'])}</b></div>
                       <div class="inspector-row">AIR <b>{money(record['air_value_usd'])}</b></div>
                       <div class="inspector-row">CONTAINER* <b>{money(record['container_value_usd'])}</b></div>''' if record else '<p class="muted">No matching record reported.</p>') +
                    f'''<p class="source-ref">SHA256 {esc(source['source_sha256'][:18])}… <a target="_blank" href="{esc(source['source_url'])}">SOURCE ▸</a></p>''')
            inspector=f'''<div class="eyebrow">INSPECTOR / OBSERVED AGGREGATE</div><h2>Port {esc(port)}</h2><div class="inspector-row">ORIGIN CODE <b>{esc(country)}</b></div>{''.join(observed)}<p class="muted">*Containerized vessel is a subset of vessel. Records are monthly aggregates, not shipments.</p><a href="/evidence" up-target="#inspector" up-history="false">CLOSE ▸</a>'''
        else:inspector='<h2>No matching record</h2>'
    return panel,f'<aside id="inspector" class="inspector">{inspector}</aside>'

def page(report):
    panel,inspect=fragments(report)
    return f'''<!DOCTYPE html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>Lithographie / Research</title><link rel="stylesheet" href="/styles.css"><script defer src="https://unpkg.com/unpoly@3/unpoly.min.js"></script></head><body><header class="top"><div class="identity"><b>LITHOGRAPHIE</b><small>BY AIC / ADJACENT INTEGRATION COMPANY</small></div><div class="descriptor"><div>LITHOGRAPHIE / TRADE RESEARCH INSTRUMENT / 01</div><strong>Commodity and maritime trade / United States</strong><span>U.S. CENSUS · HS6 PORT RECORDS</span></div></header><nav class="nav"><span class="menu">☰</span><span>DATA ▾</span><span class="nav-on">ANALYZE ▾</span><span>GEOGRAPHY ▾</span><span class="disabled">ACTIVE &nbsp; COMPARISON</span><span class="right">ARCHIVE EVIDENCE · NOMINAL USD</span></nav><main class="layout">{panel}{inspect}</main><footer>LITHOGRAPHIE / AIC <span>RESEARCH BUILD · OBSERVED AGGREGATES</span></footer></body></html>'''

class Handler(BaseHTTPRequestHandler):
    def send(self,code,body,ct='text/html; charset=utf-8'):
        body=body.encode('utf-8') if isinstance(body,str) else body
        self.send_response(code);self.send_header('Content-Type',ct);self.send_header('Content-Length',str(len(body)))
        self.send_header('X-Content-Type-Options','nosniff');self.end_headers();self.wfile.write(body)
    def do_GET(self):
        parsed=urlparse(self.path);q=parse_qs(parsed.query)
        if parsed.path=='/styles.css':return self.send(200,(HERE/'styles.css').read_bytes(),'text/css; charset=utf-8')
        if parsed.path=='/':
            if q.get('hs',[HS])[0]!=HS or q.get('period',['jan'])[0]!='jan':return self.send(400,'Unsupported selection; no source coverage.')
            report=get_report()
            return self.send(200,fragments(report)[0] if self.headers.get('X-Up-Target') else page(report))
        if parsed.path=='/evidence':
            port=q.get('port',[''])[0];country=q.get('country',[''])[0]
            if (port or country) and (not re.fullmatch(r'\d{4}',port) or not re.fullmatch(r'\d{4}',country)):
                return self.send(400,'Invalid evidence code')
            report=get_report();partial=fragments(report,(port,country) if port else None)[1]
            return self.send(200,partial if self.headers.get('X-Up-Target') else page(report).replace(fragments(report)[1],partial))
        if parsed.path in ('/data.csv','/plot.svg'):
            report=get_report()
            if report['status'] not in ('derived','summary_only'):return self.send(409,'Verified matched-month source coverage required.')
            content=rows_to_csv(report)
            if parsed.path=='/data.csv':return self.send(200,content,'text/csv; charset=utf-8')
            if not shutil.which('Rscript'):return self.send(503,'Rscript/ggplot2 not installed.')
            with tempfile.TemporaryDirectory() as tmp:
                inp=Path(tmp)/'input.csv';out=Path(tmp)/'chart.svg';inp.write_text(content)
                try:
                    subprocess.run(['Rscript',str(HERE/'chart.R'),str(inp),str(out)],check=True,timeout=35,capture_output=True)
                except (subprocess.SubprocessError,OSError):return self.send(503,'ggplot2 render unavailable.')
                return self.send(200,out.read_bytes(),'image/svg+xml')
        if parsed.path=='/health':
            report=get_report();return self.send(200,json.dumps({'status':'ok','coverage':report['status'],'renderer':bool(shutil.which('Rscript'))}),'application/json')
        self.send(404,'Not found')
    def log_message(self,format,*args):pass

if __name__=='__main__':
    port=int(os.environ.get('LITHOGRAPHIE_PORT','8765'))
    print(f'Lithographie research http://127.0.0.1:{port}/',flush=True)
    ThreadingHTTPServer(('127.0.0.1',port),Handler).serve_forever()
