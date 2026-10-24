'use strict';
const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const root=path.resolve(__dirname,'..');
const html=fs.readFileSync(path.join(root,'Lithographie_Research_Workbench.html'),'utf8');
const view=fs.readFileSync(path.join(__dirname,'intelligence-view.js'),'utf8');
const style=fs.readFileSync(path.join(__dirname,'design-contract.css'),'utf8');
const surface=html.replace(/<script id="corpus" type="application\/json">[\s\S]*?<\/script>/,'').replace(/<script type="application\/json" id="census-inspected-sample">[\s\S]*?<\/script>/,'').replace(/<script type="application\/json" id="monthly-corpus">[\s\S]*?<\/script>/,'');
test('workbench and module have one identical design contract',()=>{
  assert.ok(html.includes('/* LITHOGRAPHIE DESIGN CONTRACT V5 */'+style));
});
test('all UI direction indicators use triangles, not arrow characters',()=>{
  assert.doesNotMatch(surface,/[→↗↓↑↔⌄↻←⇢⇄⇒➔❯›»]/u);
  assert.doesNotMatch(view,/[→↗↓↑↔⌄↻←⇢⇄⇒➔❯›»]/u);
  assert.match(surface,/class="caret"/);
  assert.match(style,/\.caret::after/);
});
test('research disclaimers use short evidence labels',()=>{
 assert.doesNotMatch(view,/The archive was not transferred to this database\./);
 assert.doesNotMatch(view,/These rows cannot support a monthly or quarterly comparison\./);
 assert.doesNotMatch(view,/Unrepresented value has unknown partner composition\./);
 assert.match(view,/INCOMPLETE MONTH/);
});
test('no mixed rounded, shadowed or gradient surfaces in final design system',()=>{
 assert.match(style,/border-radius:0/);
 assert.match(style,/box-shadow:none/);
 assert.match(style,/background-image:none/);
});
