from pathlib import Path
from playwright.sync_api import sync_playwright
import os
import shutil
ROOT=Path(__file__).resolve().parent.parent
ARTIFACTS=ROOT/"engine"/"artifacts"
ARTIFACTS.mkdir(exist_ok=True)
with sync_playwright() as p:
 b=p.chromium.launch(headless=True,executable_path=os.environ.get('CHROMIUM_PATH') or shutil.which('chromium') or None,args=['--no-sandbox','--disable-dev-shm-usage'])
 for width in [1440,390]:
  page=b.new_page(viewport={'width':width,'height':900},device_scale_factor=1)
  errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
  page.set_content((ROOT/'Lithographie_Research_Workbench.html').read_text(),wait_until='domcontentloaded',timeout=30000)
  page.wait_for_timeout(450)
  print('viewport',width,'title',page.locator('#title').inner_text(),'scripts',page.evaluate('window.lithoIntel.engine.validate()'),'errors',errors[:2])
  print('status',page.locator('#count').inner_text(),'controls',page.locator('#intel-hs').count())
  assert 'intelligence' in page.locator('#title').inner_text().lower()
  assert page.locator('.intel-commodity').count()==5
  assert page.locator('.intel-chart-wrap svg').count()==1
  assert page.locator('.intel-chart-wrap svg rect[data-intel-period]').count()==6
  assert page.locator('.operation .caret').count()==4
  assert page.locator('.intel-commodity').first.evaluate('(el)=>getComputedStyle(el).borderRadius') == '0px'
  assert page.locator('.operating-strip').evaluate('(el)=>getComputedStyle(el).backgroundImage') == 'none'
  assert len(errors)==0,errors
  page.screenshot(path=str(ARTIFACTS/f'intelligence-{width}.png'),full_page=True)
  page.locator('[data-intel-tab="origins"]').click()
  assert page.locator('[data-intel-partner]').count()>=7
  assert 'PARTNER' in page.locator('#viz').inner_text()
  page.locator('[data-intel-partner="124"]').first.hover()
  assert 'Canada' in page.locator('#inspector-title').inner_text()
  page.locator('[data-intel-tab="evidence"]').click()
  assert page.locator('.intel-evidence').count()==1
  assert page.locator('#intel-census-sample tbody tr').count()==5
  assert 'ZIP HASH · NOT ARCHIVED' in page.locator('#intel-census-sample').inner_text()
  assert '0701' in page.locator('#intel-census-sample').inner_text()
  assert page.locator('#viz').inner_text().count('COMPLETE')>0
  for view in ['flow','distribution','matrix','ranks','field','scenario','spatial','bivariate','records','ports','entities','sources','intelligence']:
   page.locator(f'.tab[data-view="{view}"]').evaluate('(el)=>el.click()')
   page.wait_for_timeout(50)
   print(view, page.locator('#title').inner_text()[:25],page.locator('#viz').count())
   assert page.locator('#viz').inner_html().strip()
   assert not any(x in page.locator('body').inner_text() for x in ['↗','→','↔','⌄','↻'])
  assert len(errors)==0,errors[:3]
  # check overflow for header, main can be dense but must not spill viewport unscrollably
  print('end errors',errors,'scroll width',page.evaluate('document.documentElement.scrollWidth'),'client',width)
  page.close()
 b.close()
