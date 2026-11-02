# Publication-standard implementation review

Document: **XL-TR-SPF-001, REVIEW, Draft 0.1, INTERNAL, 2 November 2026**.
Governing source: **XL-STD-DOC-001, Revision A**, supplied 63-page PDF. The
source manifest records the attachment hash. This is a review issue, not an
approved controlled release, laboratory approval, or operating procedure.

## Profile and authority

The **Technical Report (TR)** profile is selected because the deliverable records
an investigation, methods, evidence, findings and uncertainty (Section 10.4,
TRP-01). A manual or SOP profile would incorrectly imply validated operating
instructions. The proposed number remains subject to the owner's register check.

No official `xlapplas-doc.cls`, machine-readable design contract, controlled
application template, logo-production asset, human review or approval record was
provided. The derivative class implements the normative PDF's stated rules. It
does not claim to be an official approved template or an approved deviation.
IDN-07's permitted text signature is used; no logo is redrawn. The standard's
institutional names are context rather than signatures. Human engineering review
and release approval remain pending (AI-03, AI-04, AI-07, CMP-01).

## Implemented rules and evidence

| Rules | Implementation and inspection boundary |
|---|---|
| IDN-01/02/07/09 | Exact xLaPPLAs name, expanded name and UNIST affiliation; text signature; issuer and classification retained. |
| PAG-01–04 | A4, inner/outer/top/bottom margins 22/18/19/20 mm; ONE profile across the six-unit grid. Wide main diagrams and six-column signal reference use landscape content under PAG-02. |
| PAG-05–10 | Single reading order; running report identity, number/revision/status, classification and folios; cover folio suppressed. |
| TYP-01–06/10 | Exact embedded URW Gothic Book/Demi OTF, DejaVu Sans Mono and Latin Modern Math; body 9.2/12.2 pt, ragged right; section 18/22 pt, tables/captions 8.2/10.5 pt, running identity 7/8.5 pt. Monospaced commands retain the nominal text size. |
| TYP-07/08 | Explicit authored section numbers retained; no second automatic numbering layer. Linked contents and PDF bookmarks follow the heading hierarchy. |
| COL-01/02, REP-01–03 | Black, white and neutral grays; solid/dashed lines and evidence labels convey meaning without color. Primary diagram strokes use 2 px before placement; the final figure-size check preserves readability. |
| TAB-01–05 | Left-aligned narrative cells, unique section/table labels, strong top/bottom and header rules, repeated column heads plus explicit continuation notices. Wide signal tables are landscape. |
| FIG-01–05 | Technical diagrams only; stable Figure 1A–4D IDs, captions below figures, editable Mermaid plus vector SVG/PDF. No manufacturer image or copyrighted manual page is redistributed. |
| WRT-04/05, TRP-01 | Important claims carry a source grade and baseline; manufacturer applicability, firmware unknowns, command acceptance and optical output remain separate. |
| AI-01–07 | Governing PDF reviewed; authoring capsule and editable tools supplied; no approval, field actuation, measurement or validation completion invented. |
| PDF-01–06 | Searchable text, embedded fonts, metadata, links, bookmarks, structural preflight and all-page rendered inspection are required. Actual results are recorded separately against the final PDF hash. |

## Rendering controls

The installed Mermaid CLI and library versions, input hashes and production-tool
hashes are in `publication-build.json`. Every Mermaid fence in the seven main
sources and additional Markdown evidence is parsed and rendered by Mermaid.
Puppeteer receives only local source/bundle content through `setContent`; browser
network requests are blocked. No control application is imported or equipment
endpoint accessed.

The PDF rendering theme suppresses styling-only Mermaid init directives while
preserving editable source content. Browser-computed SVG styles are frozen to
prevent Inkscape's CSS fallback from silently replacing the required typeface.
SVG word spaces are preserved. Existing edge-label backgrounds are aligned to
their text and made opaque so connector strokes do not obscure labels. Sequence
message text has an opaque background, foreground ordering and a 6 px upward
baseline adjustment inside the reserved label band to prevent reply strokes or
lifelines from intersecting letters in the vector export. The two
main landscape maps use compact layout spacing without removing nodes or arrows.
These are disclosed production transformations, not alterations to evidence.

The build rejects a PDF-incorporated figure with a final text size below 8 pt
when `--strict` is used. Supporting evidence diagrams are validated and exported
without being forced into an A4 report frame. The signal-reference tables retain
one complete row per record; repeated headers identify continued tables.

## Check disposition

C01–C10 are assessed using the final build, source audit and structural preflight.
C11 requires actual inspection of every final exported page; it must not be
inferred from an automated check or an earlier proof. The inspection record must
identify the exact final PDF hash and reviewed page ranges. C12's **approved PDF**
requirement is **pending human release approval**; the GitHub package is a review
artifact with editable sources. It must not be relabeled RELEASED from this
production record alone.

The final `publication-build.json`, `publication-preflight.json` and visual-review
record provide the measured output disposition. This file states implementation
and authority boundaries; it is not a signature or a completed release approval.
