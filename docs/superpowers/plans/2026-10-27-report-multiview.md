# HTML multiview implementation plan

> For agentic workers: use superpowers:subagent-driven-development with separate backend, frontend and integration ownership.

**Goal:** Four-view candidate/GT comparisons, truthful interface/material overlays, and reliable interactive model inspection.

**Architecture:** Extend isolated display workers and portable report assets. Preserve score loading, evaluation identity and legacy report support. Add optional private jig input separately from public input material.

**Tech Stack:** Python 3.12, OCP, VTK, manifold3d, existing CADViewer adaptation and Three.js 0.160.0.

**Spec:** ../specs/2026-10-27-report-multiview-design.md

## Global Constraints

- Candidate left, GT right; shared origin/camera/scale.
- iso=(1,-1,1), front=(0,-1,0), top=(0,0,1), right=(1,0,0); top up=(0,1,0), other up=(0,0,1).
- Preserve scoring algorithms, weights, original/derived evidence and historical outputs.
- Keep ordinary mesh/render failures outside scoring; no fabricated Interface score.
- Keep relative resource URLs, no source path disclosure, no CDN, retain CADViewer and Three.js licenses.
- New reports use new output directories; existing reports remain intact.

## Task 1: Display backend

Own src/display_assets.py, src/display_worker.py, new src/display_comparison.py if needed, tests/test_display_assets.py and new focused geometry tests.

- [x] Write synthetic tests for exact directions, shared bounds, four angle assets and material partitions, then observe failure.
- [x] Generate four split and overlay images in a single preview worker. Preserve thumbnail alias and isolated timeout behavior.
- [x] Produce matched/extra/missing mesh layers using manifold3d with shared translation, finite/closed meshes and honest unavailable states.
- [x] Accept optional already-verified interfaces mapping on build_display_assets; generate real KOR/KIR layers when supplied, with matching GT identity.
- [x] Run targeted tests including real VTK and Boolean tests; report commands and results.

## Task 2: Report UI and viewer

Own src/html_reporting.py rendering functions, report_assets/report.js and report.css, report_assets/viewer/*.js, tests/viewer.test.mjs and tests/test_html_reporting.py. Coordinate build_report integration edits with root.

- [x] Write behavior tests for four views/lightbox data, absence semantics and exact camera presets; observe failures.
- [x] Add four-view comparison/overlay galleries, truthful legends, lightbox with Esc and arrows, task filter, prompt/editing materials and download hooks.
- [x] Reuse CADViewer and expose reset, standard angles, direction axes and optional difference layers with rotation. Update fallback images when view/mode changes under file://.
- [x] Preserve all metric/null/lower-bound distinctions and keyboard navigation. Add stable fixture deep links.
- [x] Run frontend contract and Node viewer tests, then report results.

## Task 3: Metadata, interfaces, downloads and integration

Own src/report_inputs.py, new src/report_interfaces.py and src/report_downloads.py, render_report.py, plugin integration, docs/source records and acceptance outputs.

- [x] Add tests for explicit task metadata, safe GT-bound jig manifests, verified model downloads and candidate-only ZIP; observe failures.
- [x] Integrate optional --interfaces and report metadata without exposing private paths or changing scores.
- [x] Mirror shared files to plugin and update snapshot/package resource allowlists and display source hashes.
- [x] Run repository-required suites; independently review feature diff and address material findings.
- [x] Rebuild existing 18-case report in a new dated output; validate source hashes unchanged, image coverage and real browser interactions.

## Ownership/interactions

Backend produces previews/difference schema consumed by UI. Root produces row.downloads, data.downloads, row.task_type, row.prompt and private interfaces consumed by backend; root integrates build_report only after frontend finishes. No parallel edits to the same file.

## Progress

Baseline: clean evaluator 654df4f and plugin dd44435; display tests 12 passed/2 optional geometry skipped, Node viewer 7 passed. Existing retained worktrees reused. Design implements the user's specified reversible local feature work; no additional permission gate.

### Completed locally — 2026-10-27

- Backend, frontend and integration work is implemented and mirrored across 20 shared files. The final report is `html-report-final-v2` in the dated acceptance directory; prior report directories remain intact. Repository publication was explicitly authorized by the user on 2026-10-27; this change is prepared for the `html-report-20261027` source and report release.
- Independent review found that Manifold accepted the actual 130/world mesh while reducing its volume by approximately 0.97%. The display-only importer now checks original signed mesh volume against imported volume with tolerance `max(1e-6 mm³, 1e-6 × |original volume|)`. It reports `difference_mesh_volume_changed` when this check fails. The original model and ordinary overlay remain available; no scoring evidence is rewritten.
- The final report contains 18 cases, 36 coordinate frames and 288 PNGs. Difference status is 32 completed and 4 unavailable: the scoring frames for 109/130/146 lack aligned candidates, and 130/world fails the import-volume check. All completed partitions passed the final volume-conservation audit.
- UI review additions are complete: detail position follows the same filtered/sorted sequence as buttons and keyboard navigation; measured-score colors use the documented 90/60 display thresholds, with a visible legend. Lower bounds and absent scores remain ungraded by color. Static images retain angle labels; XYZ axes remain in the interactive viewer as the accepted presentation scope.
- Final automated validation: evaluator 215 tests passed; plugin 426 tests run, 423 passed and 3 skipped; Node viewer/browser 15 passed. Focused HTML 19 tests and backend 27 tests also passed. Counts supersede earlier implementation checkpoints.
- Final artifact audit passed: 535 manifest-listed files, 164 mesh JSONs, 51 verified STEP downloads, 18 original-candidate ZIP members and 587 unchanged original scoring-evidence files. ZIP container timestamps may differ after rebuilding; every archived candidate member remains byte-identical. Shared sources, source manifests, viewer provenance and report-generator hashes were checked.
- Browser checks passed for synchronized rotation, four standard views in difference mode, gallery lightbox arrows/Escape, 390 px layout without horizontal overflow, faithful unscored display for 109 and measured/descending navigation from 128 at 1/14 to 101 at 2/14. Offline browser regression tests cover static directions, reset, fixture links and keyboard navigation.
- Optional GT-bound interface manifests and synthetic KOR/KIR tests are supported. The official private jigs for these 18 cases were not available, so this delivery shows whole-model diagnostics and does not claim official Interface Match results or a reproduced editing benchmark.

Acceptance evidence is retained outside the repository in the dated `HTML多视角优化_20261027` directory: `验收说明.md`, `final-artifact-audit.json/md`, `independent-review.md`, implementation notes, final test logs, `final-v2-viewer.jpg` and `final-v2-difference.jpg`. The subsequent user-authorized release publishes this implementation and the verified report ZIP; source and artifact identities are recorded in the release documentation.
