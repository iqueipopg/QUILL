"""QUILL web demo — FastAPI app.

Serves a single static page and exposes /api/* endpoints that wrap the
existing pipeline.run_pipeline() and baseline.BaselineAgent.evaluate()
functions. Supports a 'demo' mode that returns precomputed records from
web/precomputed/ (copies of outputs/experiment_full/*.json), so the in-class
presentation has a guaranteed-working fallback if Groq is unreachable on
the day.

Launch:
    bash web/run.sh
    # or:
    uvicorn web.app:app --host 127.0.0.1 --port 8000
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
import time
from functools import lru_cache
from pathlib import Path
from typing import Optional

import yaml
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

# Path setup — the repo root is the parent of this file's directory.
REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from baseline import BaselineAgent  # noqa: E402
from pipeline import run_pipeline    # noqa: E402
from formatters import extract_a_text, extract_b_text  # noqa: E402

# --- Logging ----------------------------------------------------------
logger = logging.getLogger("quill.web")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(name)-18s | %(levelname)-7s | %(message)s",
    datefmt="%H:%M:%S",
)

WEB_DIR = Path(__file__).resolve().parent
STATIC_DIR = WEB_DIR / "static"
PRECOMPUTED_DIR = WEB_DIR / "precomputed"
SAMPLES_DIR = REPO_ROOT / "samples"

# 90 seconds per request — pipeline is ~30s on Groq, baseline ~3s; the rest is margin.
GENERATE_TIMEOUT_S = 90.0


# --- Backend introspection -------------------------------------------
def load_config() -> dict:
    try:
        with open(REPO_ROOT / "config.yaml") as f:
            return yaml.safe_load(f) or {}
    except FileNotFoundError:
        return {}


@lru_cache(maxsize=1)
def get_baseline() -> BaselineAgent:
    """Singleton — avoids re-loading the model on every request."""
    return BaselineAgent()


def banner():
    cfg = load_config()
    backend = cfg.get("backend", "?")
    precomputed_count = len(list(PRECOMPUTED_DIR.glob("leaf_*.json"))) if PRECOMPUTED_DIR.exists() else 0
    bar = "=" * 60
    print(bar)
    print(" QUILL — Quintet of Intelligent LLMs for Learning")
    print(bar)
    print(f"   backend           : {backend}")
    print(f"   precomputed essays: {precomputed_count} (for demo mode)")
    print(f"   samples           : {len(list(SAMPLES_DIR.glob('essay_*.txt'))) if SAMPLES_DIR.exists() else 0}")
    print(f"   open              : http://127.0.0.1:8000")
    print(bar)


# --- App --------------------------------------------------------------
app = FastAPI(title="QUILL demo", version="1.0.0")
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.on_event("startup")
async def _startup():
    banner()


# --- Schemas ----------------------------------------------------------
class GenerateRequest(BaseModel):
    essay: str = Field(..., min_length=20, description="Student essay text")
    prompt: Optional[str] = Field(None, description="Optional assignment prompt / rubric")
    mode: str = Field("live", pattern="^(live|demo)$")
    demo_essay_id: Optional[str] = Field(None, description="Force a specific precomputed essay (demo mode only)")


class ConditionResult(BaseModel):
    text: str
    overall_score: Optional[int] = None
    elapsed: float


class GenerateResponse(BaseModel):
    a: ConditionResult
    b: ConditionResult
    intermediate: dict
    mode_used: str
    essay_id: Optional[str] = None


# --- Endpoints --------------------------------------------------------
@app.get("/")
def serve_index():
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/api/health")
def health():
    cfg = load_config()
    backend = cfg.get("backend", "unknown")
    api_reachable = _ping_backend(backend, cfg)
    return {
        "status": "ok",
        "backend": backend,
        "api_reachable": api_reachable,
        "precomputed_available": PRECOMPUTED_DIR.exists()
        and any(PRECOMPUTED_DIR.glob("leaf_*.json")),
    }


@app.get("/api/samples")
def list_samples():
    """Return short summaries for the sample essays in samples/."""
    items = []
    if SAMPLES_DIR.exists():
        for path in sorted(SAMPLES_DIR.glob("essay_*.txt")):
            text = path.read_text(encoding="utf-8")
            items.append({
                "name": path.stem,
                "filename": path.name,
                "preview": text[:80].replace("\n", " "),
                "word_count": len(text.split()),
                "rubric_filename": _matching_rubric(path.stem).name
                if _matching_rubric(path.stem).exists() else None,
            })
    # Also surface the precomputed LEAF essays so demo mode can replay them.
    for path in sorted(PRECOMPUTED_DIR.glob("leaf_*.json")):
        try:
            rec = json.loads(path.read_text(encoding="utf-8"))
            text = rec.get("essay_text", "")
            items.append({
                "name": rec.get("essay_id", path.stem),
                "filename": path.name,
                "preview": text[:80].replace("\n", " "),
                "word_count": len(text.split()),
                "rubric_filename": None,
                "is_precomputed": True,
            })
        except Exception:
            continue
    return {"samples": items}


@app.get("/api/sample/{name}")
def get_sample(name: str):
    # Sanitize: only basenames allowed.
    if "/" in name or ".." in name:
        raise HTTPException(status_code=400, detail="Invalid sample name")
    # Try samples/ first.
    essay_path = SAMPLES_DIR / f"{name}.txt"
    if essay_path.exists():
        rubric_path = _matching_rubric(name)
        return {
            "essay": essay_path.read_text(encoding="utf-8"),
            "prompt": rubric_path.read_text(encoding="utf-8") if rubric_path.exists() else "",
            "source": "samples",
        }
    # Then precomputed.
    pc_path = PRECOMPUTED_DIR / f"{name}.json"
    if pc_path.exists():
        rec = json.loads(pc_path.read_text(encoding="utf-8"))
        return {
            "essay": rec.get("essay_text", ""),
            "prompt": rec.get("prompt", ""),
            "source": "precomputed",
            "essay_id": rec.get("essay_id"),
        }
    raise HTTPException(status_code=404, detail=f"Sample '{name}' not found")


@app.post("/api/generate")
async def generate(req: GenerateRequest):
    word_count = len(req.essay.split())
    t0 = time.time()
    try:
        if req.mode == "demo":
            payload = _generate_demo(req)
        else:
            payload = await _generate_live(req)
        elapsed = round(time.time() - t0, 2)
        logger.info(
            "generate ok | mode=%s | words=%d | elapsed=%.2fs",
            payload["mode_used"], word_count, elapsed,
        )
        return payload
    except asyncio.TimeoutError:
        logger.warning("generate timeout | mode=%s | words=%d", req.mode, word_count)
        raise HTTPException(
            status_code=504,
            detail={
                "error": "timeout",
                "message": f"Generation exceeded {GENERATE_TIMEOUT_S}s. Try demo mode or a shorter essay.",
                "suggest_demo": True,
            },
        )
    except RuntimeError as e:
        # The pipeline raises RuntimeError after 5 retries on Groq 429.
        msg = str(e)
        if "rate limit" in msg.lower() or "429" in msg:
            logger.warning("generate rate-limited | %s", msg)
            raise HTTPException(
                status_code=503,
                detail={
                    "error": "rate_limited",
                    "message": "Groq rate-limited the request. Wait ~60 seconds or switch to demo mode.",
                    "suggest_demo": True,
                },
            )
        logger.exception("generate runtime error")
        raise HTTPException(
            status_code=503,
            detail={"error": "backend_error", "message": msg, "suggest_demo": True},
        )
    except Exception as e:
        logger.exception("generate failed")
        raise HTTPException(
            status_code=503,
            detail={"error": "unknown", "message": str(e), "suggest_demo": True},
        )


# --- Internals --------------------------------------------------------
def _matching_rubric(essay_stem: str) -> Path:
    # essay_01.txt → rubric_01.txt
    suffix = essay_stem.replace("essay_", "rubric_")
    return SAMPLES_DIR / f"{suffix}.txt"


def _ping_backend(backend: str, cfg: dict) -> bool:
    """Tiny no-cost (or near-no-cost) reachability check.
    Only does a network call for Groq/Gemini; for 'local' just checks env."""
    try:
        if backend == "groq":
            key_env = cfg.get("groq", {}).get("api_key_env", "GROQ_API_KEY")
            api_key = os.environ.get(key_env)
            if not api_key:
                return False
            import requests
            r = requests.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={"Authorization": f"Bearer {api_key}"},
                json={
                    "model": cfg.get("groq", {}).get("model", "llama-3.3-70b-versatile"),
                    "messages": [{"role": "user", "content": "hi"}],
                    "max_tokens": 5,
                },
                timeout=8,
            )
            return r.status_code == 200
        if backend == "gemini":
            key_env = cfg.get("gemini", {}).get("api_key_env", "GEMINI_API_KEY")
            return bool(os.environ.get(key_env))
        if backend == "local":
            return Path("models").exists()
    except Exception as e:
        logger.warning("backend ping failed: %s", e)
        return False
    return False


def _generate_demo(req: GenerateRequest) -> dict:
    """Serve a pre-computed record. Honors demo_essay_id when given,
    otherwise picks a stable hash-based one from the essay text."""
    files = sorted(PRECOMPUTED_DIR.glob("leaf_*.json"))
    if not files:
        raise RuntimeError("No precomputed records available for demo mode.")
    target = None
    if req.demo_essay_id:
        for path in files:
            if path.stem == req.demo_essay_id:
                target = path
                break
    if target is None:
        # Stable index based on the essay content so the same input
        # consistently maps to the same demo output during a talk.
        idx = hash(req.essay) % len(files)
        target = files[idx if idx >= 0 else -idx]
    rec = json.loads(target.read_text(encoding="utf-8"))

    key = rec.get("key", {})
    blind = rec.get("blind", {})
    a_label = next((lab for lab, src in key.items() if src == "A_baseline"), None)
    b_label = next((lab for lab, src in key.items() if src == "B_multiagent"), None)
    a_text = blind.get(a_label, {}).get("text", "") if a_label else ""
    b_text = blind.get(b_label, {}).get("text", "") if b_label else ""

    a_raw = rec.get("raw", {}).get("A", {}) or {}
    b_raw = rec.get("raw", {}).get("B", {}) or {}
    return {
        "a": {
            "text": a_text,
            "overall_score": a_raw.get("overall_score"),
            "elapsed": rec.get("elapsed", {}).get("A", 0.0),
        },
        "b": {
            "text": b_text,
            "overall_score": _b_overall(b_raw),
            "elapsed": rec.get("elapsed", {}).get("B", 0.0),
        },
        "intermediate": {
            "a1": b_raw.get("a1_structure"),
            "a2": b_raw.get("a2_content"),
            "a3": b_raw.get("a3_language"),
            "a4": b_raw.get("a4_synthesized"),
            "a5": b_raw.get("a5_moderated"),
        },
        "mode_used": "demo",
        "essay_id": rec.get("essay_id"),
    }


async def _generate_live(req: GenerateRequest) -> dict:
    """Run condition A and B against the actual backend."""
    loop = asyncio.get_event_loop()

    def _run():
        # Baseline (A) — blocking, runs on a thread pool.
        t_a = time.time()
        a_raw = get_baseline().evaluate(req.essay, req.prompt or None)
        a_elapsed = round(time.time() - t_a, 2)
        a_text = extract_a_text(a_raw)

        # Pipeline (B). Use a throwaway output_dir under web/ to keep the
        # repo's outputs/ dir clean of live-demo artifacts.
        t_b = time.time()
        live_dir = WEB_DIR / "_live_runs"
        live_dir.mkdir(exist_ok=True)
        b_raw = run_pipeline(req.essay, req.prompt or None, output_dir=str(live_dir))
        b_elapsed = round(time.time() - t_b, 2)
        b_text = extract_b_text(b_raw)
        return a_raw, a_text, a_elapsed, b_raw, b_text, b_elapsed

    a_raw, a_text, a_elapsed, b_raw, b_text, b_elapsed = await asyncio.wait_for(
        loop.run_in_executor(None, _run), timeout=GENERATE_TIMEOUT_S
    )

    return {
        "a": {
            "text": a_text,
            "overall_score": a_raw.get("overall_score") if isinstance(a_raw, dict) else None,
            "elapsed": a_elapsed,
        },
        "b": {
            "text": b_text,
            "overall_score": _b_overall(b_raw),
            "elapsed": b_elapsed,
        },
        "intermediate": {
            "a1": b_raw.get("a1_structure"),
            "a2": b_raw.get("a2_content"),
            "a3": b_raw.get("a3_language"),
            "a4": b_raw.get("a4_synthesized"),
            "a5": b_raw.get("a5_moderated"),
        },
        "mode_used": "live",
        "essay_id": None,
    }


def _b_overall(b_raw: dict) -> Optional[int]:
    if not isinstance(b_raw, dict):
        return None
    a5 = b_raw.get("a5_moderated") or {}
    moderated = a5.get("moderated_feedback") if isinstance(a5, dict) else None
    if isinstance(moderated, dict) and moderated.get("overall_score") is not None:
        return moderated["overall_score"]
    a4 = b_raw.get("a4_synthesized") or {}
    if isinstance(a4, dict) and a4.get("overall_score") is not None:
        return a4["overall_score"]
    return None


@app.exception_handler(HTTPException)
async def _http_exception_handler(_, exc: HTTPException):
    """Ensure error bodies are always JSON-shaped, even when detail is a dict."""
    if isinstance(exc.detail, dict):
        return JSONResponse(status_code=exc.status_code, content=exc.detail)
    return JSONResponse(status_code=exc.status_code, content={"message": str(exc.detail)})
