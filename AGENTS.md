# Maintainer notes

This repository is an independent STEP evaluator. Read README.md and docs/SCORING_V3.md before changing behavior. The stdio service in mcp_server.py is standard-library-only; geometry runs through the unchanged evaluate.py / worker.py subprocess path.

Files recorded in docs/SOURCE_HASHES.json were copied byte-for-byte from the reviewed 2026-10-19 evaluator snapshot or the stated CADGenBench commit. Do not silently edit an algorithm, vendor file, weight or scoring contract. An intentional change requires an explicit protocol/source record update and meaningful validation.

Default CLI and all MCP evaluations use v3. A candidate with valid geometry and intact evidence participates even when a metric is unavailable: measured_score stays null, awarded_score is zero, and the total is marked policy_lower_bound with coverage. Keep ranking_eligible false. Do not overwrite historical output directories or change annotation hashes to bypass provenance checks.

Run tests with Python 3.12 and installed evaluator dependencies:

    RUN_GEOMETRY_TESTS=1 python -B -m unittest discover -s tests -v

On PowerShell set `$env:RUN_GEOMETRY_TESTS = '1'` first. No Fusion or model call belongs in these tests. Keep runtime, private inputs, outputs, local config, credentials and .validation out of source commits. Distribution packaging must preserve all third-party licenses and source hashes; see docs/PACKAGING.md.
