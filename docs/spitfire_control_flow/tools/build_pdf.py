#!/usr/bin/env python3
"""Rebuild the standards-derived review PDF from the accompanying Markdown.

Requires Python, Pandoc, XeLaTeX, Inkscape, Chromium, PyMuPDF and Mermaid CLI.
Only documentation assets are written. No Spitfire package is imported and no
equipment endpoint is accessed. Working TeX files stay outside the repository.
"""
from __future__ import annotations
import argparse,hashlib,json,os,re,shutil,subprocess,tempfile,xml.etree.ElementTree as ET
from datetime import date
from pathlib import Path
import fitz

ROOT=Path(__file__).resolve().parent.parent
TOOLS=ROOT/'tools'
INPUTS=['README.md','01_main_operation.md','02_signal_interlock.md','03_state_machine.md',
        '04_communication_sequence.md','05_signal_reference.md','06_evidence_and_unknowns.md']
FENCES=re.compile(r'^```mermaid[^\n]*\n(.*?)^```[ \t]*$',re.M|re.S)

def run(args,**kw):
    r=subprocess.run([str(x) for x in args],capture_output=True,text=True,**kw)
    if r.returncode:
        raise RuntimeError(f'Command failed ({r.returncode}): {args[0]}\n{r.stdout[-6000:]}\n{r.stderr[-6000:]}')
    return r
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def tex(s):
    out=''
    for c in s:
        out+= {'\\':r'\textbackslash{}','&':r'\&','%':r'\%','$':r'\$','#':r'\#',
            '_':r'\_','{':r'\{','}':r'\}','~':r'\textasciitilde{}','^':r'\textasciicircum{}'}.get(c,c)
    return out
def first_heading(text):
    m=re.search(r'^#{1,6}\s+(.+?)\s*#*$',text,re.M)
    return m[1] if m else 'Technical diagram'
def figure_properties(pdf,maxw,maxh):
    with fitz.open(pdf) as d:
        p=d[0];scale=min(maxw/p.rect.width,maxh/p.rect.height)
        spans=[s for b in p.get_text('dict')['blocks'] if 'lines' in b for line in b['lines'] for s in line['spans'] if s['text'].strip()]
        sizes=[s['size']*scale for s in spans]
        return {'width_pt':p.rect.width,'height_pt':p.rect.height,'placed_scale':scale,
            'effective_min_text_pt':min(sizes) if sizes else None,'text_spans':len(spans)}

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--mmdc',default=shutil.which('mmdc') or '/workspace/tooling/mermaid/node_modules/.bin/mmdc')
    ap.add_argument('--chromium',default=shutil.which('chromium') or '/usr/bin/chromium')
    ap.add_argument('--tooling-root',type=Path,help='npm project containing mermaid and puppeteer; defaults to parent of node_modules/.bin/mmdc')
    ap.add_argument('--output',type=Path)
    ap.add_argument('--build-dir',type=Path)
    ap.add_argument('--allow-partial',action='store_true',help='proof only; missing source files are recorded')
    ap.add_argument('--render-only',action='store_true')
    ap.add_argument('--min-figure-font',type=float,default=8.0)
    ap.add_argument('--strict',action='store_true',help='fail if a figure needs readability review')
    args=ap.parse_args()
    tooling=args.tooling_root or Path(args.mmdc).absolute().parent.parent.parent
    meta=json.loads((TOOLS/'publication.json').read_text())
    meta['display_date']=date.fromisoformat(meta['issue_date']).strftime('%-d %B %Y')
    missing=[name for name in INPUTS if not (ROOT/name).exists()]
    if missing and not args.allow_partial:raise SystemExit('Missing input files: '+', '.join(missing))
    build=args.build_dir or Path(tempfile.mkdtemp(prefix='spitfire-control-pdf-'))
    build.mkdir(parents=True,exist_ok=True)
    figures=ROOT/'figures';figures.mkdir(exist_ok=True)
    config=TOOLS/'mermaid-theme.json'
    puppet=build/'puppeteer.json'
    puppet.write_text(json.dumps({'executablePath':args.chromium,'args':['--no-sandbox','--disable-dev-shm-usage']}))
    cachepath=figures/'render-cache.json'
    cache=json.loads(cachepath.read_text()) if cachepath.exists() else {}
    mermaid_version=run([args.mmdc,'--version']).stdout.strip()
    library_version=json.loads((tooling/'node_modules/mermaid/package.json').read_text())['version']
    records=[];pieces=[];figure_index=0;newcache={};input_hashes={}
    extra=[str(p.relative_to(ROOT)) for p in sorted((ROOT/'evidence').glob('*.md')) if FENCES.search(p.read_text(encoding='utf-8'))]
    all_inputs=INPUTS+extra
    for name in all_inputs:
        path=ROOT/name
        if not path.exists():continue
        text=path.read_text(encoding='utf-8')
        input_hashes[name]=sha(path)
        block_index=0
        def render(match):
            nonlocal block_index,figure_index
            block_index+=1;figure_index+=1
            body=match[1].strip()+'\n'
            caption_match=re.search(r'^\s*%%\s*caption:\s*(.+)$',body,re.M)
            heads=list(re.finditer(r'^#{1,6}\s+(.+?)\s*#*$',text[:match.start()],re.M))
            caption=caption_match[1] if caption_match else (heads[-1][1] if heads else first_heading(text))
            if name not in extra and not re.match(r'^Figure\s+\d',caption):
                section=int(path.name[:2]);suffix=chr(64+block_index)
                caption=f'Figure {section}{suffix}. '+re.sub(r'^\d+(?:\.\d+)*\.?\s*','',caption)
            landscape=bool(re.search(r'^\s*%%\s*layout:\s*landscape\s*$',body,re.M))
            stem=f'{"evidence_" if name in extra else ""}{path.stem}_{block_index:02d}'
            source=figures/(stem+'.mmd');svg=figures/(stem+'.svg');pdf=figures/(stem+'.pdf')
            source.write_text(body,encoding='utf-8')
            digest=hashlib.sha256((body+config.read_text()+mermaid_version+library_version+sha(TOOLS/'render_mermaid.mjs')).encode()).hexdigest()
            if cache.get(stem)!=digest or not svg.exists() or not pdf.exists():
                run(['node',TOOLS/'render_mermaid.mjs','--tooling-root',tooling,'--chromium',args.chromium,
                     '--source',source,'--output',svg,'--config',config],cwd=ROOT)
                run(['inkscape',svg,'--export-type=pdf',f'--export-filename={pdf}'],cwd=ROOT)
            newcache[stem]=digest
            props=figure_properties(pdf,(258 if landscape else 170)*72/25.4,(138 if landscape else 220)*72/25.4)
            record={'index':figure_index,'input':name,'block':block_index,'caption':caption,
                'included_in_pdf':name not in extra,
                'layout':'landscape' if landscape else 'portrait','source':str(source.relative_to(ROOT)),
                'svg':str(svg.relative_to(ROOT)),'pdf':str(pdf.relative_to(ROOT)),'source_sha256':sha(source),
                **props}
            record['readability_review_required']=name not in extra and (props['effective_min_text_pt'] is None or props['effective_min_text_pt']<args.min_figure_font)
            records.append(record)
            cap=tex(caption);label='fig:'+stem
            caption_parts=re.match(r'^(Figure\s+\d+[A-Z]?\.)\s*(.*)',caption)
            if caption_parts:cap=r'\textbf{'+tex(caption_parts[1])+'} '+tex(caption_parts[2])
            fig=(r'\clearpage'+'\n'+(r'\begin{landscape}'+'\n' if landscape else '')+
                r'\begin{figure}[p]'+'\n'+r'\centering'+'\n'+
                f'\\includegraphics[width={258 if landscape else 170}mm,height={138 if landscape else 220}mm,keepaspectratio]{{{pdf.as_posix()}}}\n'+
                f'\\caption{{{cap}}}\\label{{{label}}}\n'+r'\end{figure}'+'\n'+
                (r'\end{landscape}'+'\n' if landscape else '')+r'\clearpage'+'\n')
            return fig
        text=FENCES.sub(render,text)
        if name in extra:continue  # Validate/render supporting diagrams without duplicating the report body.
        # Keep PDF hyperlinks usable outside a checked-out repository.
        def link(m):
            label,dest=m.groups()
            if dest.startswith(('http:','https:','#','mailto:')):return m[0]
            if dest.startswith('<') and dest.endswith('>'):dest=dest[1:-1]
            if dest.startswith('/'):return m[0]
            from urllib.parse import quote
            base=f'https://github.com/{meta["repository"]}/blob/{meta["documentation_ref"]}/docs/spitfire_control_flow/'
            return f'[{label}]({base}{quote(dest,safe="/#:?=&%")})'
        text=re.sub(r'(?<!!)\[([^\]]+)\]\(([^)]+)\)',link,text)
        def reference_link(m):
            prefix,dest=m.groups()
            if dest.startswith(('http:','https:','#','mailto:','/')):return m[0]
            from urllib.parse import quote
            base=f'https://github.com/{meta["repository"]}/blob/{meta["documentation_ref"]}/docs/spitfire_control_flow/'
            return prefix+base+quote(dest,safe='/#:?=&%')
        text=re.sub(r'^(\[[^\]\n]+\]:\s*)(\S+)',reference_link,text,flags=re.M)
        if name=='05_signal_reference.md':
            # Six-column technical reference tables need PAG-02 landscape width.
            text='::: {.landscape}\n\n'+text+'\n\n:::\n'
        if pieces:pieces.append('\\clearpage\n')
        pieces.append(text)
    cachepath.write_text(json.dumps(newcache,indent=2)+'\n')
    changed=[n for n,digest in input_hashes.items() if sha(ROOT/n)!=digest]
    if changed:raise RuntimeError('Inputs changed during rendering; rebuild: '+', '.join(changed))
    manifest={'document':meta,'input_sha256':input_hashes,
        'tool_sha256':{p.name:sha(p) for p in sorted(TOOLS.iterdir()) if p.is_file() and p.suffix in {'.py','.lua','.tex','.cls','.mjs','.json'}},
        'missing_inputs':missing,'partial_proof':bool(missing),'renderer':{'mermaid_cli_installation':mermaid_version,'mermaid_library':library_version,'chromium':args.chromium,'route':'Puppeteer setContent plus local Mermaid bundle; no URL navigation; all network requests blocked'},
        'figures':records,'landscape_sections':['05_signal_reference.md — wide six-column signal tables, PAG-02'],
        'mermaid_style_override':'Styling-only source init directives are suppressed for PDF rendering; controlled theme used before layout. Mermaid content and editable sources are retained.',
        'readability_review_required':[r['source'] for r in records if r['readability_review_required']],
        'visual_review':'PENDING: validate exported PDF and inspect every rendered page after final build'}
    (build/'report-source.md').write_text('\n\n'.join(pieces),encoding='utf-8')
    (build/'metadata.json').write_text(json.dumps(meta),encoding='utf-8')
    if not args.render_only:
        texpath=build/'report.tex'
        run(['pandoc',build/'report-source.md','--from=markdown+raw_tex','--to=latex','--standalone',
             '--no-highlight','--lua-filter',TOOLS/'pdf-code.lua','--template',TOOLS/'report-template.tex',
             '--metadata-file',build/'metadata.json','--output',texpath],cwd=ROOT)
        # TAB-05: Pandoc repeats headers but does not label continuation.
        # Add a continuation label only on a table's second and later pages.
        def continued_table(match):
            table=match[0]
            if r'\endhead' not in table or r'\endfirsthead' in table:return table
            start=table.find(r'\toprule');end=table.find(r'\endhead')
            if start<0:return table
            header=table[start:end]
            columns=header.count(r'\begin{minipage}')
            if not columns:return table
            continuation=(f'\\multicolumn{{{columns}}}{{@{{}}l@{{}}}}{{\\footnotesize\\itshape Table continued from previous page}}\\\\\n')
            return table[:start]+header+r'\endfirsthead'+'\n'+continuation+header+table[end:]
        texpath.write_text(re.sub(r'\\begin\{longtable\}[\s\S]*?\\end\{longtable\}',continued_table,texpath.read_text()))
        env=dict(os.environ);env['TEXINPUTS']=str(TOOLS)+os.pathsep+env.get('TEXINPUTS','')
        logs=[]
        for _ in range(3):
            rr=run(['xelatex','-interaction=nonstopmode','-halt-on-error','-file-line-error',f'-output-directory={build}',texpath],cwd=ROOT,env=env)
            logs.append(rr.stdout)
        output=(args.output or ROOT/meta['filename']).resolve();output.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(build/'report.pdf',output)
        log=(build/'report.log').read_text(errors='replace')
        manifest['pdf']={'file':str(output),'sha256':sha(output),'bytes':output.stat().st_size,
            'latex_overfull_boxes':re.findall(r'Overfull[^\n]*',log),'latex_missing_characters':re.findall(r'Missing character:[^\n]*',log)}
        manifest['build_directory']=str(build)
    manifest_path=ROOT/'evidence'/'publication-build.json'
    manifest_path.parent.mkdir(exist_ok=True)
    manifest_path.write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({'pdf':manifest.get('pdf'),'missing_inputs':missing,'figures':len(records),
        'readability_review_required':manifest['readability_review_required'],'build_directory':str(build)},indent=2))
    if args.strict and manifest['readability_review_required']:raise SystemExit(2)

if __name__=='__main__':main()
