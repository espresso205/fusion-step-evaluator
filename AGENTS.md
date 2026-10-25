# Maintainer notes

This repository is an independent STEP evaluator. Read README.md and docs/SCORING_V4.md before changing current behavior, and docs/SCORING_V3.md when maintaining the explicit historical protocol. The stdio service in mcp_server.py is standard-library-only; evaluate.py routes v4 geometry work through evaluate_v4.py / worker_v4.py and keeps the legacy worker.py path for v2/v3.

docs/SOURCE_HASHES.json records the current source bytes and identifies new v4 files, entry routing changes, and preserved legacy/vendor sources. docs/SOURCE_HASHES_V3.json retains the reviewed pre-v4 snapshot. Do not silently edit an algorithm, vendor file, weight or scoring contract. An intentional change requires an explicit protocol/source record update and meaningful validation.

Default CLI and MCP evaluations use v4 geometry mode; read docs/SCORING_V4.md. Explicit v3 retains its original fixed-world rules and algorithms. In v4 only shape/dimension/mass are scored; distance/face_match/section are diagnostics with no awarded score and no effect on scored coverage. Unavailable scored measurements remain null with zero policy credit and a disclosed lower-bound total. Keep ranking_eligible false. Do not overwrite historical outputs or change annotation hashes to bypass provenance checks. Original and rigidly derived geometry hashes must both be verified; no scaling or reflection is allowed.

Run tests with Python 3.12 and installed evaluator dependencies:

    RUN_GEOMETRY_TESTS=1 python -B -m unittest discover -s tests -v

On PowerShell set `$env:RUN_GEOMETRY_TESTS = '1'` first. No Fusion or model call belongs in these tests. Keep runtime, private inputs, outputs, local config, credentials and .validation out of source commits. Distribution packaging must preserve all third-party licenses and source hashes; see docs/PACKAGING.md.
