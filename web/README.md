# QUILL web demo

A FastAPI app that wraps the existing QUILL pipeline behind a one-page web UI.
Designed for the in-class presentation: paste an essay, hit Generate, see
Conditions A and B render side by side.

## Quick start

From the repo root:

```bash
bash web/run.sh
```

Then open <http://127.0.0.1:8000>.

This script:
- sources `GROQ_API_KEY` / `GEMINI_API_KEY` from `~/.bashrc` if present
- activates the project venv (`./venv`)
- starts uvicorn on port 8000 (override with `QUILL_PORT=8001 bash web/run.sh`)

## Modes

The page has a Live / Demo toggle (left column, below the textareas).

- **Live** — calls Groq (or whichever backend is configured in `config.yaml`).
  Total wall time ~30 s per essay (baseline ≈3 s + pipeline ≈25 s + 5 s
  pacing between agents). Required env var: `GROQ_API_KEY`.
- **Demo** — serves a precomputed essay from `web/precomputed/` and returns
  in <1 s. No network calls. Use this on the day if Groq is rate-limited,
  the wifi is unreliable, or you simply want a guaranteed working path.

The dropdown contains:
1. `essay_01`, `essay_02` — the hand-crafted samples in `samples/`. Use these
   for Live mode.
2. `leaf_000` … `leaf_007` — the eight essays already processed in the final
   experiment run. Best paired with Demo mode (precomputed answers come back
   instantly and match exactly what the survey participants saw).

## Endpoints

| Path | Method | Notes |
|---|---|---|
| `/` | GET | Serves `static/index.html`. |
| `/static/*` | GET | All static assets (CSS, JS, fonts, images). |
| `/api/health` | GET | `{status, backend, api_reachable, precomputed_available}`. |
| `/api/samples` | GET | Sample essay metadata for the dropdown. |
| `/api/sample/{name}` | GET | Full essay + prompt for a named sample. |
| `/api/generate` | POST | The work. Body `{essay, prompt?, mode, demo_essay_id?}`. |

API docs at <http://127.0.0.1:8000/docs> while the server is running.

## Troubleshooting

- **Port already in use** — `QUILL_PORT=8001 bash web/run.sh`.
- **`GROQ_API_KEY` not found** — `export GROQ_API_KEY=...` before launching,
  or add it to `~/.bashrc`. The script picks it up automatically. Without a
  key, the page's status dot turns amber and live mode will surface an error
  card; demo mode keeps working.
- **`429` from Groq during a run** — the page shows a friendly error and a
  "Switch to demo mode and retry" button. Click it. On a long talk, prefer
  demo mode for repeated runs to avoid TPM ceilings (we hit ours during the
  N=10 experiment on essay 9 of 10).
- **No precomputed essays** — `cp outputs/experiment_full/*.json web/precomputed/`
  to re-populate.
- **Live request feels stuck** — there is a 90 s server-side timeout; the
  page surfaces it cleanly. You can also reload the tab.

## Code structure

```
web/
├── app.py            # FastAPI app: endpoints, request handling, error UX
├── run.sh            # Convenience launcher
├── precomputed/      # leaf_000…leaf_007 records (for demo mode)
├── _live_runs/       # Pipeline scratch dumps from live mode (auto-created)
└── static/
    ├── index.html    # Single page — hero, problem, pipeline, conditions, run widget
    ├── styles.css    # quill.css from the design handoff, verbatim
    ├── landing.css   # Section/layout styles extracted from landing.html
    ├── app.js        # State machine + fetch + render
    └── app.css       # Interactive-widget styles (form, progress, results, accordions)
```

The only Python touched outside `web/` is `formatters.py` at the repo root
(extracted `extract_a_text` / `extract_b_text` from `run_experiment.py` so
they can be imported without running the experiment loop).

The Python pipeline (`pipeline.py`, `baseline.py`, `agents/`, `config.yaml`)
is **unchanged**.
