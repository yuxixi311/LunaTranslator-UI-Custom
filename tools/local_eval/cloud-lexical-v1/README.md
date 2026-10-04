# Cloud lexical source checkpoint

**NOT EXECUTED. Public source preparation snapshot, not a final execution consumer or a translation-quality result.**

This directory records a proposed conservative glossary activation mechanism and its bounded Linux runner. The pure policy, fake tests, illustrative fixture decisions and upstream notices are reusable. The checkpoint has no downloaded packages, installed environment, analyzer output, model output or execution claim.

The only packaging changes to the reviewed runner are its introductory text, the preparation hash and the separate public manifest filenames. The mechanism and runtime controls are unchanged. The public runner is a distinct source revision: prior review or approval of another manifest does not automatically approve this snapshot. The active frozen pilot is not changed by this export.

## Safe preparation

From this directory on Linux, run the standard-library fake tests:

    python -I -B -c "import sys; sys.path.insert(0, '.'); import unittest; unittest.main(module=None, argv=['unittest', 'test_pilot_runner', 'test_lexical_policy', 'test_public_snapshot'])"

The tests mock package transfers, installation metadata, analyzer objects and process launches. They do not download, install, import or run Sudachi, a translation model or a GPU stack. They do create temporary fake wheel/JSON data.

`PUBLIC_PREPARATION_MANIFEST.json` pins only the sanitized preparation inputs. `PUBLIC_SOURCE_MANIFEST.json` inventories this entire source snapshot. Their hashes describe these public bytes only. No `PUBLIC_EXECUTION_MANIFEST.json` is supplied, and neither public manifest is an execution approval. The runner's preparation-only `freeze` command can generate a distinct execution manifest for a future independent review; it is not a real pilot run.

## What the examples mean

The 16 synthetic cases and intended decisions are public mechanism diagnostics. They are not a new semantic holdout, observed POS output, or bilingual-human validation. Publishing them makes their exposure explicit. The other 32 exact source texts are already-public, previously used regression material, verified against the commit and files in `FIXTURE_PROVENANCE.json`. Original private grading criteria and model outputs are excluded.

The policy can consume only source text, the fixed canon and token records. It admits a key only if every literal occurrence exactly equals a known dictionary person-name token. POS remains a dictionary prediction; this does not resolve intended sense, role direction, ownership or omitted context. Even a complete 16/16 match would permit only consideration of a separately frozen semantic experiment.

## Before any real execution

A future consumer needs an explicitly approved environment and an independent review of its exact generated public execution manifest, target interpreter, dependency pins, resource limits and one-shot behavior. No real package or native-import verification has been performed for this snapshot. The dictionary target has not been checked against the selected wheel. See `PLAN.md`, `RUNNER.md` and `SOURCE_VERIFICATION.md`.

Keep later generated runtime paths, environment records, raw outputs, claims, wheels and installed files out of source publication. There is no Windows fallback or product dependency in this checkpoint. Original upstream license and legal notices are retained under `license_sources/`; their inclusion does not relicense the surrounding project.
