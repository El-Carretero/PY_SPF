# Review-PDF production

This is a documented review derivative of **XL-STD-DOC-001, Revision A**. The
uploaded standard governs; no official `xlapplas-doc.cls`, separate design
contract, logo production asset, approval signature, or approval record was
supplied. The exact permitted text signature is used instead of recreating a logo.
The output remains **REVIEW / Draft 0.1 / INTERNAL**. It does not claim laboratory
approval or status as an operating procedure.

## Rebuild

Requirements: Python 3, PyMuPDF, Pandoc 3, XeLaTeX, Inkscape, Chromium, the
installed URW Gothic OTF family, DejaVu Sans Mono, Latin Modern Math, and Mermaid
CLI 11.12.0 and Mermaid 11.17.2 (both pinned by `package-lock.json` and
recorded in the build manifest). A current Node.js release supported by those
packages is required.
Use an ordinary local documentation-build environment; this tooling
does not import the control application or access the equipment.

Run from `docs/spitfire_control_flow/`. The npm dependencies belong only to this
document renderer and do not alter controller dependencies. An installed system
Chromium is used rather than downloading a browser.

```sh
PUPPETEER_SKIP_DOWNLOAD=1 npm ci --prefix tools
python tools/build_pdf.py --mmdc tools/node_modules/.bin/mmdc --strict
python tools/validate_pdf.py XL-TR-SPF-001_Spitfire-Control-Flow_Review01.pdf \
  --output /tmp/spitfire-pdf-preflight.json --render-dir /tmp/spitfire-pdf-pages
```

Mermaid source comments may set `%% caption: ...` and `%% layout: landscape`.
Landscape is reserved for wide technical evidence under PAG-02. Figures remain
editable `.mmd` and `.svg`, with searchable vector PDF exports. The local Mermaid parser and renderer run through Puppeteer `setContent` with
all browser network requests blocked. Styling-only source `init` directives are
suppressed for the PDF theme; the editable Mermaid sources retain their content.
Browser-computed static SVG styles and preserved word spaces prevent exporter
font substitution and joined words. Sequence-message labels use opaque white
backgrounds and a small baseline offset to prevent lifelines or reply strokes
from crossing text. Cached rendering is reused only when the
source, controlled theme, renderer, and Mermaid versions match. Additional
Mermaid blocks under `evidence/` are validated and exported but do not enter the
main PDF. The six-column signal-reference section uses landscape pages.

The build uses the **ONE** profile: the full six-unit content width. A4 geometry,
22/18/19/20 mm margins, exact URW Gothic font files, 9.2/12.2 pt body, neutral
palette, rule weights, captions, running identity, control record, linked contents,
metadata and bookmarks are implemented by the derivative class and template.
Working TeX and rendered QA pages stay outside the repository.

The preflight reports clipping and possible text overlaps; these are not a visual
approval. Inspect **every page after the final build**, plus representative dense,
figure, and table pages at actual size. Record page ranges, reviewer identity and
disposition in the final validation evidence. Automated inspection must not mark
human engineering review or laboratory approval as complete.
