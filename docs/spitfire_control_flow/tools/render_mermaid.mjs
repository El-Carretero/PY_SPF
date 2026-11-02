#!/usr/bin/env node
// Authorized local content only: no file:// navigation and no network requests.
// Mermaid's own parser and renderer are used; no SVG is hand-reconstructed.
import fs from 'node:fs/promises';
import path from 'node:path';
import {createRequire} from 'node:module';

const opts={};
for(let i=2;i<process.argv.length;i+=2)opts[process.argv[i].replace(/^--/,'')]=process.argv[i+1];
for(const key of ['tooling-root','chromium','source','output','config'])if(!opts[key])throw Error(`Missing --${key}`);
const require=createRequire(path.join(path.resolve(opts['tooling-root']),'package.json'));
const puppeteer=(await import(require.resolve('puppeteer'))).default;
const mermaidBundle=require.resolve('mermaid/dist/mermaid.min.js');
// Source init directives contain styling only in this package. Apply the
// controlled publication theme consistently; retain editable source unchanged.
const source=(await fs.readFile(opts.source,'utf8')).replace(/%%\{init:[\s\S]*?\}%%/g,'');
const config=JSON.parse(await fs.readFile(opts.config,'utf8'));
// Compact spacing makes the four-domain landscape maps legible at A4 size;
// this changes layout only, preserving every Mermaid node and connector.
if(/^\s*%%\s*layout:\s*landscape\s*$/m.test(source)){
 config.flowchart={...config.flowchart,nodeSpacing:12,rankSpacing:16,padding:8};
}
const browser=await puppeteer.launch({executablePath:opts.chromium,headless:true,args:['--no-sandbox','--disable-dev-shm-usage']});
try{
 const page=await browser.newPage();
 await page.setViewport({width:1800,height:1600,deviceScaleFactor:1});
 await page.setRequestInterception(true);
 page.on('request',request=>request.abort('blockedbyclient'));
 await page.setContent('<!doctype html><html><head><meta charset="utf-8"><style>html,body{margin:0;background:white;color:black;font-family:"URW Gothic"}</style></head><body><div id="container"></div></body></html>',{waitUntil:'domcontentloaded'});
 await page.addScriptTag({content:await fs.readFile(mermaidBundle,'utf8')});
 const rendered=await page.evaluate(async({source,config})=>{
  window.mermaid.initialize({...config,htmlLabels:false,flowchart:{...config.flowchart,htmlLabels:false},startOnLoad:false});
  await window.mermaid.parse(source);
  await document.fonts.ready;
  const {svg}=await window.mermaid.render('spitfireDiagram',source,document.getElementById('container'));
  const parsed=new DOMParser().parseFromString(svg,'image/svg+xml');
  if(parsed.querySelector('parsererror'))throw Error('Mermaid output is not well-formed SVG XML');
  if(parsed.querySelector('foreignObject'))throw Error('ForeignObject labels are not permitted in archival figure exports');
  // Freeze the browser-computed static presentation. Inkscape's CSS parser does
  // not implement all Mermaid animation/CSS-variable rules; without this step
  // it can silently replace 18px URW text with default 12px sans-serif text.
  const holder=document.createElement('div');holder.innerHTML=svg;document.body.appendChild(holder);
  const root=holder.querySelector('svg');
  root.setAttributeNS('http://www.w3.org/XML/1998/namespace','xml:space','preserve');
  const props=['font-family','font-size','font-weight','font-style','font-variant','text-anchor',
   'dominant-baseline','letter-spacing','white-space','fill','fill-opacity','stroke','stroke-width',
   'stroke-opacity','stroke-dasharray','stroke-linecap','stroke-linejoin','opacity'];
  const styles=[...root.querySelectorAll('*')].filter(e=>e.tagName!=='style').map(e=>[e,props.map(p=>[p,getComputedStyle(e).getPropertyValue(p)])]);
  for(const [e,style] of styles)for(const [p,v] of style)if(v)e.style.setProperty(p,v);
  // Mermaid splits a label into word tspans. SVG importers otherwise discard
  // each tspan's leading space, joining words in searchable vector exports.
  for(const e of root.querySelectorAll('text,tspan'))e.style.setProperty('white-space','pre');
  // Keep connector labels legible: Mermaid's translucent background can leave
  // a dark arrow running through letters in grayscale vector exports. Align
  // its existing background to the actual text bounds and make it opaque.
  for(const rect of root.querySelectorAll('.edgeLabel rect.background')){
   const text=rect.parentElement.querySelector('text');if(!text)continue;
   const b=text.getBBox();
   for(const [k,v] of Object.entries({x:b.x-2,y:b.y-1,width:b.width+4,height:b.height+2}))rect.setAttribute(k,v);
   rect.style.setProperty('fill','#FFFFFF');rect.style.setProperty('opacity','1');
  }
  // Sequence labels are deliberately drawn above lifelines and message rules.
  // Offset message text within Mermaid's reserved label band so an exporter's
  // baseline interpretation cannot put a dotted reply through its last line.
  for(const text of [...root.querySelectorAll('text.messageText,text.loopText,text.sectionTitle')]){
   if(text.classList.contains('messageText'))text.setAttribute('y',Number(text.getAttribute('y'))-6);
   const b=text.getBBox(),rect=document.createElementNS('http://www.w3.org/2000/svg','rect');
   for(const [k,v] of Object.entries({x:b.x-2,y:b.y-1,width:b.width+4,height:b.height+2}))rect.setAttribute(k,v);
   rect.setAttribute('fill','#FFFFFF');rect.setAttribute('stroke','none');
   rect.setAttribute('class','publication-label-background');
   const parent=text.parentElement;parent.appendChild(rect);parent.appendChild(text);
  }
  for(const s of root.querySelectorAll('style'))s.remove();
  return new XMLSerializer().serializeToString(root);
 },{source,config});
 await fs.writeFile(opts.output,rendered,'utf8');
 console.log(JSON.stringify({source:opts.source,output:opts.output,renderer:'Mermaid parser/render via Puppeteer setContent; network requests blocked'}));
}finally{await browser.close();}
