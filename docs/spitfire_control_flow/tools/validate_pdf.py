#!/usr/bin/env python3
"""Structural PDF preflight and page rendering; this never substitutes for visual review."""
import argparse,collections,hashlib,json,re,subprocess
from pathlib import Path
import fitz

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('pdf',type=Path)
    ap.add_argument('--output',type=Path,required=True)
    ap.add_argument('--render-dir',type=Path)
    ap.add_argument('--dpi',type=int,default=120)
    ap.add_argument('--forbid-text',action='append',default=[],help='Case-insensitive text excluded from this publication scope; repeat as needed')
    args=ap.parse_args()
    doc=fitz.open(args.pdf)
    pages=[];outside=[];overlaps=[];badchars=[];links=[];forbidden=[]
    for i,p in enumerate(doc):
        width,height=p.mediabox.width,p.mediabox.height
        links.extend({'source_page':i+1,**link} for link in p.get_links())
        for term in args.forbid_text:
            if term.casefold() in p.get_text().casefold():forbidden.append({'page':i+1,'term':term})
        lines=[]
        for block in p.get_text('dict')['blocks']:
            for line in block.get('lines',[]):
                text=''.join(s['text'] for s in line['spans'])
                if not text.strip():continue
                box=fitz.Rect(line['bbox'])
                row={'bbox':list(box),'text':text}
                if '\ufffd' in text:badchars.append({'page':i+1,**row})
                if box.x0 < -0.5 or box.y0 < -0.5 or box.x1>width+0.5 or box.y1>height+0.5:outside.append({'page':i+1,**row})
                lines.append(row)
        for j,a in enumerate(lines):
            ra=fitz.Rect(a['bbox'])
            for b in lines[j+1:]:
                rb=fitz.Rect(b['bbox']);r=ra&rb
                if r.width>3 and r.height>min(ra.height,rb.height)*0.45:
                    overlaps.append({'page':i+1,'a':a,'b':b,'intersection':list(r)})
        pages.append({'page':i+1,'width_pt':width,'height_pt':height,'rotation':p.rotation,
            'text_lines':len(lines),'links':len(p.get_links()),'images':len(p.get_images()),'form_xobjects':len(p.get_xobjects())})
        if args.render_dir:
            args.render_dir.mkdir(parents=True,exist_ok=True)
            p.get_pixmap(matrix=fitz.Matrix(args.dpi/72,args.dpi/72),alpha=False).save(args.render_dir/f'page-{i+1:03d}.png')
    rr=subprocess.run(['pdffonts',str(args.pdf)],text=True,capture_output=True,check=True)
    fonts=rr.stdout
    counts=collections.Counter(link['kind'] for link in links)
    invalid_links=[{'page':link['source_page'],'target_page':link.get('page')} for link in links if link['kind'] in (1,4) and not 0<=link.get('page',-1)<len(doc)]
    unembedded=[]
    for row in fonts.splitlines()[2:]:
        flags=re.search(r'\s(yes|no)\s+(yes|no)\s+(yes|no)\s+\d+\s+\d+\s*$',row)
        if flags and flags[1]=='no':unembedded.append(row)
    result={'pdf':str(args.pdf),'pdf_sha256':hashlib.sha256(args.pdf.read_bytes()).hexdigest(),'pages':len(doc),'metadata':doc.metadata,'bookmarks':doc.get_toc(),
        'page_records':pages,'fonts_pdffonts':fonts,'unembedded_fonts':unembedded,'pdf_language':doc.xref_get_key(doc.pdf_catalog(),'Lang'),
        'link_annotations':{'total':len(links),'uri':counts[2],'named_internal':counts[4],'local_file_launch':counts[3],'invalid_internal_targets':invalid_links},
        'forbidden_text_hits':forbidden,'outside_page_text':outside,
        'potential_text_overlaps':overlaps,'replacement_characters':badchars,
        'a4_mediaboxes':all(abs(x['width_pt']-595.276)<1 and abs(x['height_pt']-841.89)<1 for x in pages),
        'visual_review':'PENDING: inspect every exported page, including dense/table/figure pages at 100 percent (PDF-05/PDF-06)',
        'notes':['Overlap records are candidates, not automatic failures: diagram text, mathematical notation and table structures require visual interpretation.',
            'Vector figure Form XObjects require rendered inspection for text/figure interference; structural checks alone cannot certify layout.']}
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({'pages':len(doc),'bookmarks':len(result['bookmarks']),'a4_mediaboxes':result['a4_mediaboxes'],
        'outside_page_text':len(outside),'potential_text_overlaps':len(overlaps),'replacement_characters':len(badchars),
        'font_report':fonts},indent=2))

if __name__=='__main__':main()
