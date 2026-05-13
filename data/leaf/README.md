# LEAF dataset

This directory hosts the LEAF corpus and the sampled subsets used by QUILL.

## Contents

| File | Committed? | Description |
|---|---|---|
| `leaf.jsonl` | **No** (gitignored) | Full LEAF corpus (~31 MB, ~5 000 essays with human-expert feedback). |
| `subset_pilot.json` | Yes | The 3-essay sample used for the validated pilot run. |
| `subset_full.json` | Yes | The 10-essay sample used for the final experiment. |

## How to obtain `leaf.jsonl`

LEAF was introduced by Behzad et al., *Assessing the State of the Argumentative Writing Skills of Korean L2 English Learners* (NAACL 2024). Obtain the corpus from the authors' release (or from a shared team channel) and place it at `data/leaf/leaf.jsonl`.

The two `subset_*.json` files are deterministic samples drawn from `leaf.jsonl` with `random.seed(42)` and a 150–800-word filter (see `build_subset.py`). With the same `leaf.jsonl` in place, `python build_subset.py` reproduces `subset_full.json` exactly.

If you only need the data the experiment actually used (e.g. you're working on the survey side), the two `subset_*.json` files already in the repo are sufficient — no need to download `leaf.jsonl`.
