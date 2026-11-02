# Bilingual review-PDF production

The English and Korean editions are **XL-TR-SPF-001, REVIEW, Draft 0.2,
INTERNAL**, governed by **XL-STD-DOC-001, Revision A**. They use one shared class,
type scale, page geometry and figure-production route. The user explicitly
requested the complete Korean edition. Human engineering review and laboratory
release approval remain pending; the output does not claim to be an operating
procedure or an approved laboratory publication.

The supplied standard's official application class, separate design contract,
logo-production asset and approval records were not provided. The documented
review derivative uses IDN-07's permitted text signature rather than recreating
a logo. See `evidence/publication-standard-review.md` for the rule mapping and
review boundary.

## Requirements

Use an ordinary documentation-build environment with:

- Python 3, PyMuPDF and fontTools;
- Pandoc 3 and XeLaTeX with fontspec, unicode-math, xetexko and its cjk-ko
  dependency (including `kolabels-utf.sty`), plus the LaTeX packages named by
  `xlapplas-doc-review.cls`;
- URW Gothic OTF under `/usr/share/fonts/opentype/urw-base35/`, DejaVu Sans Mono,
  Latin Modern Math, and Noto Sans CJK Regular/Bold collections under
  `/usr/share/fonts/opentype/noto/`;
- Inkscape, system Chromium and a supported Node.js release;
- Mermaid CLI **11.12.0** and Mermaid **11.17.2**, pinned by `package-lock.json`.

A complete TeX Live Korean installation supplies both xetexko and cjk-ko. An
installation with `xetexko.sty` alone is insufficient if `kolabels-utf.sty` is
missing. Dependencies here belong to document production: these tools do not
import the controller application, change its dependencies, or access equipment.

## Build both editions

Run from `docs/spitfire_control_flow/`:

```sh
PUPPETEER_SKIP_DOWNLOAD=1 npm ci --prefix tools
python tools/build_pdf.py --language en --mmdc tools/node_modules/.bin/mmdc --strict
python tools/build_pdf.py --language ko --mmdc tools/node_modules/.bin/mmdc --strict
```

The output PDFs are:

- `XL-TR-SPF-001_Spitfire-Control-Flow_Review02.pdf`;
- `XL-TR-SPF-001_Spitfire-Control-Flow_KO_Review02.pdf`.

English input is the seven Markdown files in the document root. Korean input is
the corresponding seven files under `ko/`. Capsules are `publication.json` and
`publication-ko.json`. Figures and caches are isolated under `figures/en/` and
`figures/ko/`; source hashes, production-tool hashes, renderer versions and figure
readability measurements are in `evidence/publication-build-en.json` and
`evidence/publication-build-ko.json`. A full build rejects source changes during
rendering. `--strict` rejects incorporated figure text below 8 pt or missing
LaTeX glyphs. `--allow-partial` is only for explicitly labeled proofs.

## Type and layout

Both editions use A4, 22/18/19/20 mm inner/outer/top/bottom margins, the ONE profile
across the six-unit grid, 9.2/12.2 pt body, 8.2/10.5 pt tables and captions,
7/8.5 pt running identity, and a neutral palette. Wide technical figures and the
six-column signal reference use PAG-02 landscape content. Working TeX, temporary
font faces and QA page images stay outside the repository.

Latin text retains URW Gothic Book/Demi. The requested Korean edition uses Noto
Sans CJK KR Regular/Bold for Hangul through XeTeX-ko; the type scale, margins,
hierarchy and control fields remain shared. The build extracts collection faces
1 (Korean proportional) and 6 (Korean mono) into temporary OTFs with fontTools and
records their source hashes and family names. Noto's shared CFF data can retain a
`NotoSansCJKjp` internal font name in a PDF font report; the selected Korean face
and cmap are identified by the recorded collection index and name-table family.
No replacement glyph or substituted generic font is accepted merely because a
PDF opens.

## Mermaid and vector export

Mermaid comments may set `%% caption: ...` and `%% layout: landscape`. Existing
`Figure 1A.` and `그림 1A.` captions are retained without a duplicate prefix. Every
Mermaid fence in each edition's seven manuscripts is parsed and rendered; diagrams
remain editable `.mmd` and `.svg` with searchable vector PDF exports.

The local Mermaid parser/renderer runs through Puppeteer `setContent`, with all
browser network requests blocked. Styling-only source init directives are
suppressed for the controlled PDF theme; node/edge content is preserved.
Browser-computed SVG styles and word spaces are frozen to prevent exporter font
substitution and joined words. Connector labels have opaque backgrounds.
Sequence message text has foreground backgrounds and a small baseline offset so
lifelines or dotted replies cannot cross letters. Landscape maps use compact
spacing. Cache keys cover source, theme, renderer and Mermaid versions.

## Final inspection

```sh
python tools/validate_pdf.py XL-TR-SPF-001_Spitfire-Control-Flow_Review02.pdf \
  --output evidence/publication-preflight-en.json --render-dir /tmp/spitfire-en-pages
python tools/validate_pdf.py XL-TR-SPF-001_Spitfire-Control-Flow_KO_Review02.pdf \
  --output evidence/publication-preflight-ko.json --render-dir /tmp/spitfire-ko-pages
```

Preflight records text bounds, possible text overlaps, glyph replacement, A4
boxes, embedded fonts, metadata, bookmarks and link destinations. Its results do
not constitute visual approval. Inspect **every page of both final exports**,
including all figures and dense tables at actual size, then record page ranges,
reviewer identity, findings and exact PDF hashes in the final validation evidence.
Any changed page requires a new rendered inspection. Automated checks must not
mark human engineering review or laboratory approval complete.
