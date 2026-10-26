# HTML multiview comparison

The requested report covers the official CADGenBench report's presentation capabilities and adds rotatable candidate/reference STEP-derived geometry. Keep candidate left and ground truth right, a restrained Chinese UI, and existing v4 scores unchanged.

## Visual design

The detail page contains a synchronized interactive comparison, four fixed orthographic comparisons (ISO, Front, Top, Right), and four material/interface overlays. Images open in a keyboard-accessible lightbox. Candidate-only, reference-only, transparent overlay, difference layers, reset, and standard directions remain available in the viewer. Static views and image enlargement work with file:// and without WebGL; HTTP enables interactive WebGL. Input material, meaningful metrics and concise analysis remain visible, with internal evidence inventories excluded.

All renderers use iso=(1,-1,1), front=(0,-1,0), top=(0,0,1), right=(1,0,0); top up=(0,1,0), other up=(0,0,1). Every comparison shares one origin, camera and scale. No model-specific normalization, new alignment, scaling or reflection is allowed.

## Difference semantics

Default whole-model display uses mesh solid Boolean regions: matched=P intersection G (blue), extra=P minus G (red), missing=G minus P (amber), with optional translucent candidate context. It is explicitly a tessellated whole-model visual diagnostic, not an Interface Match measurement.

An optional private interface manifest supplies GT-bound, hash-verified STEP jig regions and KOR/KIR types. In GT coordinates, construct inflated AABB(R) with margin=max(2mm,0.2*longest extent). KOR shell=(inflated intersection GT) minus R; KIR shell=(inflated minus GT) minus R. KOR matched=R minus P, extra=R intersection P, missing=shell minus P. KIR matched=R intersection P, extra=shell intersection P, missing=R minus P. This enables actual Interface overlay without importing a score. Missing/failed interface input is disclosed and never relabeled as a completed interface check.

## Data contract

Keep display.views.world/scoring and thumbnail compatibility. Each frame gains previews[angle]={split,overlay} relative PNG/SVG URLs. Each frame gains difference={status,scope,layers:{matched,extra,missing},reason?}, where layers are optional relative display mesh URLs and scope is whole_model or interface. No private paths enter browser JSON. Single-sided geometry and render failures retain available views.

Private model sources remain in ReportBundle.model_sources. Verified STEP copies may be packaged for download, with a candidate-only submission ZIP. Inputs may carry explicit task_type, prompt and optional editing illustrations; missing metadata is unknown, never guessed from numerical IDs. Task filtering and task summaries use explicit metadata and v4 participant denominators. No official Interface score or watertight/bbox claim is fabricated.

## Delivery and validation

Change the evaluator worktree first, mirror shared files to the plugin, refresh display-source hashes and packaging lists, and preserve algorithm/vendor/weight bytes. Rebuild the existing 18-case report into a new dated directory. Test real synthetic geometry, camera agreement, missing layers, immutable scoring inputs, file:// images, HTTP rotation and keyboard navigation. Source edits and a local verified report are the deliverable; a new external publication is outside this feature request.
