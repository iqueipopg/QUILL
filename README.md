# QUILL — Quintet of Intelligent LLMs for Learning

A multi-agent system for automated feedback on student essays. Five cooperative LLM agents evaluate orthogonal dimensions of student writing (structure, content, language, then synthesise and moderate) to produce richer, more actionable feedback than a single-prompt LLM approach.

## Architecture

Five sequential agents:

1. **A1 Structure** — paragraph organization, logical flow, transitions
2. **A2 Content** — thesis quality, prompt adherence, evidence
3. **A3 Language** — grammar, vocabulary, register, with specific corrections (original → corrected + error type)
4. **A4 Synthesizer** — merges A1–A3 into a student-facing feedback report
5. **A5 Moderator** — filters harsh/vague/biased phrasing, ensures constructive tone

## Quickstart

```bash
# Setup (one-time)
source venv/bin/activate
export GROQ_API_KEY="..."   # or GEMINI_API_KEY, or run local Qwen

# Single essay through the pipeline
python pipeline.py --essay samples/essay_01.txt --rubric samples/rubric_01.txt

# Single-prompt baseline (for comparison)
python baseline.py --essay samples/essay_01.txt --rubric samples/rubric_01.txt

# Full experiment: A baseline vs B pipeline on a subset of LEAF essays
python build_subset.py
python run_experiment.py
python export_to_markdown.py
```

## Backends

Configurable in `config.yaml`:
- `groq` — Groq API (free tier, fast, llama-3.3-70b-versatile)
- `gemini` — Google Gemini API (free tier, slower per call)
- `local` — Qwen2.5-7B 4-bit on local GPU (8 GB VRAM sufficient)

## Repo layout

```
quill/
├── agents/                 # 5 agent implementations + BaseAgent + logger
├── pipeline.py             # Multi-agent orchestrator (Condition B)
├── baseline.py             # Single-prompt baseline (Condition A)
├── run_experiment.py       # End-to-end experiment runner (A + B on a subset)
├── build_subset.py         # Sample N essays from LEAF
├── export_to_markdown.py   # Per-essay .md exporter for the survey team
├── config.yaml             # Backend + per-agent generation params
├── data/leaf/              # LEAF dataset + sampled subsets
├── outputs/                # Experiment results + run logs
└── samples/                # Hand-crafted demo essays/rubrics
```

## Experiment

Three conditions compared on the same set of student essays:
- **A**: single-prompt baseline (same LLM, holistic prompt)
- **B**: QUILL multi-agent pipeline
- **C**: human expert feedback (LEAF corpus, Behzad et al., NAACL 2024)

Participants rate feedbacks on usefulness, clarity, and specificity (Likert 1–5) plus an overall ranking, with X/Y/Z labels hiding the source.

## Context

Developed for EDU3049-01 *AI Applied Education Theories and Implementation*, Sogang University, Spring 2026.

Authors: Ignacio Queipo de Llano Pérez-Gascón, Do-gyu Ha, Sergi Prieto Oliveras, Minjae Lee.
