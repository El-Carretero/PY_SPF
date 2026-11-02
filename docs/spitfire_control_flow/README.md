# Spitfire hardware–software integrated control flow

**XL-TR-SPF-001 · REVIEW · Draft 0.2 · 2 November 2026 · INTERNAL**

## Executive result

**A RUN request, software acceptance, a transmitted command, a controller readback, and measured optical emission are different events.** The available evidence supports an integrated functional description and specific software/log observations; it does not establish the complete firmware circuit, certify the installed interlocks, or demonstrate optical emission.

The requested equipment is a **2005 Spectra-Physics Spitfire, SPTF-100F-1KHPR**. The supplied manufacturer document describes **Spitfire Pro F/40F/PM**. Its operating principles are cited as **MANUAL**, while applicability to every installed component remains **UNKNOWN** until a matching nameplate, ship report, wiring record and firmware specification are available. This report is a reverse-engineering analysis, not an operating procedure or authorization to energize a laser.

### Interpretation boundary

This report is provided in matching English and Korean editions under the supplied xLaPPLAs publication format. Source references and technical claim boundaries are the same in both editions. Its central finding is that software readiness and the GUI's `EMISSION` label do not establish amplified optical output. In the retained records, BWD remained latched despite matching reset ACKs; the manufacturer's normal recovery condition requires stable mode-locked seed light and both BWD photodetector indicators green.

## Scope and baselines

| Baseline | Immutable identity | Interpretation |
|---|---|---|
| Native PY_SPF 1.0 | `cebcc28490f48e9e5d4d1c2e2feef34d638244e7` | Current field-analysis baseline used for the PC1 records. |
| Original executable | `analysis/reference/SPITFIRE.EXE`, hash in manifest | Recovered original x86 behavior and isolated emulation; not a claimed XP-PC live actuation trial. |
| Manufacturer description | 330A Rev. A, *Spitfire Pro User's Manual* | Manufacturer-described hardware behavior, with the model-applicability limit above. |

Other repository branches and version-identification details are recorded in [branch baselines](evidence/branch_baselines.json). A branch name alone is not a software-version guarantee. No control-program source, configuration, dependency or installed equipment setting was changed for this documentation task.

## Reading order and deliverables

1. [Main operation flow](01_main_operation.md): power-on, software readiness, RUN, expected amplification, STOP and recovery boundaries.
2. [Signal and interlock logic](02_signal_interlock.md): optical/electrical signal routes and independent protection functions.
3. [State transitions](03_state_machine.md): software states and observations without inventing a unified firmware state machine.
4. [Communication sequences](04_communication_sequence.md): startup, commands, readbacks, reset and STOP.
5. [Signal reference](05_signal_reference.md): origin, path, interpretation, abnormal result, monitoring lifetime and recovery.
6. [Evidence and unknowns](06_evidence_and_unknowns.md): provenance, verification boundaries, missing sources and proposed measurements.

The English review PDF is [XL-TR-SPF-001_Spitfire-Control-Flow_Review02.pdf](XL-TR-SPF-001_Spitfire-Control-Flow_Review02.pdf); the Korean counterpart is [XL-TR-SPF-001_Spitfire-Control-Flow_KO_Review02.pdf](XL-TR-SPF-001_Spitfire-Control-Flow_KO_Review02.pdf). The Korean Markdown sources are in [ko/README.md](ko/README.md). Editable Mermaid remains in Markdown; incorporated `.mmd`, `.svg` and `.pdf` figures are in `figures/en/` and `figures/ko/`. Build instructions and validation tools are in [tools/README.md](tools/README.md). The evidence directory contains sanitized, traceable summaries and the time-ordered BWD response CSV. Full manufacturer PDFs and private machine images are not redistributed.

## Evidence legend

| Required grade | Meaning in this publication |
|---|---|
| **CODE VERIFIED** | Behavior directly identified in a named, immutable Python source baseline. |
| **XP/LOG VERIFIED** | Original recovered x86/oracle evidence or a specified recorded log. The provenance facet always states which; an emulator is not a physical XP-PC experiment. |
| **MANUAL** | Statement in the named manufacturer's manual and cited printed/PDF page. |
| **INFERRED** | Explicit reasoning from cited facts; not a recovered manufacturer requirement. |
| **UNKNOWN** | The supplied sources do not establish the claim. |

Solid diagram arrows denote the described functional or software relationship, not an invented hidden electrical gate. Dashed arrows identify a correspondence, inference or unverified transfer. Evidence grades and source IDs are recorded in the surrounding prose and tables instead of the diagram elements; unverified behavior remains identified in plain language. No color alone carries a result. Source IDs, paths, immutable commits and page conventions are defined in [the evidence registry](evidence/source_registry.json).

## Consequential findings

- **CODE VERIFIED / XP/LOG VERIFIED:** Native 1.0 retains the original global `ON`/`OFF` command family, but adds matched-tag handling, bounded query retries, UI-thread scheduling and recovery behavior. These changes do not reveal the firmware's complete actuator sequence.
- **CODE VERIFIED:** Empower opt-out in Native 1.0 defaults to a board-side write during initialization. The setting affects board configuration and selected GUI interpretation; it does not establish the installed external-pump wiring.
- **MANUAL:** BWD is a bandwidth detector. Both red/blue spectral photodetector signals must satisfy their thresholds before normal reset recovery; an electronic Internal timing source does not establish this optical condition.
- **XP/LOG VERIFIED:** Retained physical logs contain 10,464 BWD response lines, zero with either latch bit clear, and 44 matching reset receipts. These are sampled records with gaps; no continuously observed all-times claim is made.
- **CODE VERIFIED:** The original-style `EMISSION` label follows Empower status bits and is skipped while Empower opt-out is set. It is not an independent measurement of the Spitfire output beam.
- **UNKNOWN:** The exact installed model/manual correspondence, firmware-internal global-command effects, complete interlock wiring and actual emitted optical output remain unverified.

## Safety and authority

**WARNING — energized laser and high-voltage hazards.** A diagram or software readback cannot establish beam containment, personnel protection, stored-energy discharge or interlock integrity. Incorrect reliance on software indicators can cause exposure, electrical injury or equipment damage. This report is analysis-only: do not execute its literal command examples, bridge an interlock, or use it instead of a model-matched manufacturer procedure and authorized local SOP.

The manufacturer also describes special alignment operation in which the pumped system can lase with seed input blocked; an absent Seed or a hidden GUI `EMISSION` label must not be used as a proof of no hazardous output (MAN-330A, printed A-2 / PDF 96; see the applicability limit). Recommendations in the final chapter are proposals for supervised verification, not completed tests or safe operating values.

## Document control and review status

| Role or field | Record |
|---|---|
| Document class / number | Technical Report / proposed `XL-TR-SPF-001` |
| Issue | REVIEW, Draft 0.2, 2 November 2026 |
| Classification / issuer | INTERNAL / xLaPPLAs, Department of Physics, UNIST |
| Prepared by | Codex automated analysis for the requester; source-bound synthesis and document production |
| Technical reviewer | Human reviewer not recorded; pending |
| Approver | Human approval not recorded; pending |
| Principal Investigator reference | Inhyuk Nam, laboratory identity supplied by the publication standard; no approval inferred |
| Formatting authority | XL-STD-DOC-001 Revision A, SHA256 in the source manifest |

The GitHub upload is a private repository review issue, not a claim of institutional approval or an approved operating procedure. The document number is proposed pending the owner's controlled-register check. Typed default names in the supplied standard were not converted into fictitious signatures.

## Authoring capsule and production record

The machine-readable capsules are [tools/publication.json](tools/publication.json) and [tools/publication-ko.json](tools/publication-ko.json). The supplied standard governs A4 geometry, typography, grayscale, running identification, captions, tables, searchable embedded fonts and review records. The Korean edition uses an embedded Korean typeface for Hangul while retaining the same page geometry, hierarchy and nominal text sizes. Its official application template and machine-readable design contract were not supplied; the editable class is a documented derivative of the normative PDF, rather than a purported official template. The final build and page-inspection records state which checks were actually completed.

The source record is [evidence/source_manifest.json](evidence/source_manifest.json). The original attachments are retained by the project owner. All listed commands and state bits are evidence within their baseline scope; recovered implementation behavior is not promoted to a manufacturer hardware specification.
