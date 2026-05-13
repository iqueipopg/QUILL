"""Run conditions A (baseline) and B (multi-agent pipeline) on each essay in a subset.
Condition C (human) comes from the LEAF feedback in the subset.
Saves outputs/experiment_pilot/<essay_id>.json with all 3 conditions side by side."""
import json, time, random
from pathlib import Path
from baseline import BaselineAgent
from pipeline import run_pipeline
from agents.logger import get_logger

logger = get_logger("Experiment")

SUBSET = "data/leaf/subset_full.json"
OUT_DIR = Path("outputs/experiment_full")
OUT_DIR.mkdir(parents=True, exist_ok=True)
random.seed(42)

def _format_annotations(annotations):
    """Format A3's error_annotations into a readable corrections list.
    Returns empty string if no annotations."""
    if not annotations:
        return ""
    lines = ["Specific corrections noted in your essay:"]
    for a in annotations:
        if not isinstance(a, dict):
            continue
        orig = a.get("original", "").strip()
        corr = a.get("corrected", "").strip()
        etype = a.get("error_type", "").strip()
        if not orig or not corr:
            continue
        if etype:
            lines.append(f"- '{orig}' → '{corr}' ({etype})")
        else:
            lines.append(f"- '{orig}' → '{corr}'")
    return "\n".join(lines) if len(lines) > 1 else ""

def _prose_from_components(summary, structure_fb, content_fb, language_fb, priority_actions):
    """Assemble feedback components into plain prose paragraphs. No markdown headers,
    no bullet lists for priority actions (they become a single sentence)."""
    paragraphs = []
    if summary:
        paragraphs.append(summary.strip())
    if structure_fb:
        paragraphs.append(structure_fb.strip())
    if content_fb:
        paragraphs.append(content_fb.strip())
    if language_fb:
        paragraphs.append(language_fb.strip())
    if priority_actions:
        cleaned = [a.strip().rstrip(".") for a in priority_actions if a and a.strip()]
        if cleaned:
            if len(cleaned) == 1:
                paragraphs.append(f"The main thing to focus on going forward: {cleaned[0]}.")
            else:
                joined = "; ".join(cleaned[:-1]) + f"; and {cleaned[-1]}"
                paragraphs.append(f"Going forward, focus on these things: {joined}.")
    return "\n\n".join(paragraphs)

def extract_b_text(pipeline_result):
    """Pipeline output -> plain prose + appended 'Specific corrections' from A3."""
    final = pipeline_result.get("moderated_feedback") or pipeline_result.get("final_feedback") or {}
    if isinstance(final, dict) and "moderated_feedback" in final:
        final = final["moderated_feedback"]
    if not final:
        a5 = pipeline_result.get("a5_moderated", {})
        final = a5.get("moderated_feedback") or pipeline_result.get("a4_synthesized", {})
    main = _prose_from_components(
        summary=final.get("summary"),
        structure_fb=final.get("structure_feedback"),
        content_fb=final.get("content_feedback"),
        language_fb=final.get("language_feedback"),
        priority_actions=final.get("priority_actions") or [],
    )
    annotations = pipeline_result.get("a3_language", {}).get("error_annotations")
    corrections_block = _format_annotations(annotations) if annotations else ""
    if corrections_block:
        return main + "\n\n" + corrections_block
    return main

def extract_a_text(baseline_result):
    if baseline_result.get("parse_error"):
        return "[PARSE ERROR]"
    return _prose_from_components(
        summary=baseline_result.get("summary"),
        structure_fb=baseline_result.get("structure_feedback"),
        content_fb=baseline_result.get("content_feedback"),
        language_fb=baseline_result.get("language_feedback"),
        priority_actions=baseline_result.get("priority_actions") or [],
    )

with open(SUBSET) as f:
    essays = json.load(f)

baseline = BaselineAgent()

for idx, essay in enumerate(essays):
    eid = essay["essay_id"]
    logger.info("=== %s (essay %d/%d) ===", eid, idx + 1, len(essays))

    # Condition A — single-prompt baseline
    t0 = time.time()
    a_raw = baseline.evaluate(essay["essay_text"], essay.get("prompt"))
    a_elapsed = time.time() - t0
    a_text = extract_a_text(a_raw)
    logger.info("A done in %.1fs", a_elapsed)

    time.sleep(5)

    # Condition B — multi-agent pipeline
    t0 = time.time()
    b_raw = run_pipeline(
        essay["essay_text"],
        essay.get("prompt"),
        output_dir=str(OUT_DIR / "_pipeline_runs"),
    )
    b_elapsed = time.time() - t0
    b_text = extract_b_text(b_raw)
    logger.info("B done in %.1fs", b_elapsed)

    # Condition C — LEAF human
    c_text = essay["human_feedback"]

    # Blind random labels X/Y/Z for the survey
    labels = ["X", "Y", "Z"]
    sources = ["A_baseline", "B_multiagent", "C_human"]
    texts = [a_text, b_text, c_text]
    order = list(range(3))
    random.shuffle(order)
    label_map = {labels[i]: {"source": sources[order[i]], "text": texts[order[i]]} for i in range(3)}

    record = {
        "essay_id": eid,
        "essay_text": essay["essay_text"],
        "prompt": essay.get("prompt", ""),
        "elapsed": {"A": a_elapsed, "B": b_elapsed},
        "blind": label_map,
        "key": {labels[i]: sources[order[i]] for i in range(3)},
        "raw": {"A": a_raw, "B": b_raw, "C": c_text},
    }
    with open(OUT_DIR / f"{eid}.json", "w") as f:
        json.dump(record, f, indent=2, ensure_ascii=False)
    logger.info("saved %s", eid)

    if idx < len(essays) - 1:
        logger.info("TPM cooldown: sleeping 30s before next essay...")
        time.sleep(30)

logger.info("all done")
