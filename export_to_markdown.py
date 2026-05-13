"""Export each essay record in outputs/experiment_full/ to a human-readable .md.
Output goes to outputs/experiment_full/markdown/."""
import json
from pathlib import Path

SRC_DIR = Path("outputs/experiment_full")
OUT_DIR = SRC_DIR / "markdown"
OUT_DIR.mkdir(parents=True, exist_ok=True)

SOURCE_LABELS = {
    "A_baseline": "A — Single-prompt baseline (LLM, holistic)",
    "B_multiagent": "B — Multi-agent pipeline (LLM, 5 specialised agents)",
    "C_human": "C — Human (LEAF dataset, educational consultant)",
}

def _get_overall_score(rec, source):
    """Extract the system's overall_score for A or B from the raw JSON.
    Returns None for C (LEAF human feedback is qualitative only)."""
    raw = rec.get("raw", {})
    if source == "A_baseline":
        a_raw = raw.get("A", {})
        if isinstance(a_raw, dict):
            return a_raw.get("overall_score")
    elif source == "B_multiagent":
        b_raw = raw.get("B", {})
        if not isinstance(b_raw, dict):
            return None
        candidate_paths = [
            ["moderated_feedback", "overall_score"],
            ["a5_moderated", "moderated_feedback", "overall_score"],
            ["a5_moderated", "overall_score"],
            ["final_feedback", "overall_score"],
        ]
        for path in candidate_paths:
            cur = b_raw
            ok = True
            for k in path:
                if isinstance(cur, dict) and k in cur:
                    cur = cur[k]
                else:
                    ok = False
                    break
            if ok and cur is not None:
                return cur
    return None

def render_essay_md(rec):
    eid = rec["essay_id"]
    essay = rec["essay_text"].strip()
    prompt = (rec.get("prompt") or "").strip()
    blind = rec["blind"]
    key = rec["key"]

    lines = []
    lines.append(f"# {eid}")
    lines.append("")
    lines.append("## Original essay")
    lines.append("")
    if prompt:
        lines.append(f"**Assignment prompt:** {prompt}")
        lines.append("")
    for line in essay.split("\n"):
        lines.append(f"> {line}" if line.strip() else ">")
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("## The three feedbacks")
    lines.append("")
    lines.append("Below are three different pieces of feedback on the essay above, labelled X, Y, and Z. They appear in randomised order — see the mapping at the bottom for which is which.")
    lines.append("")
    for label in ["X", "Y", "Z"]:
        lines.append(f"### Feedback {label}")
        lines.append("")
        text = blind[label]["text"].strip()
        lines.append(text)
        lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("### Source mapping (reviewer reference — do NOT include in the survey)")
    lines.append("")
    for label in ["X", "Y", "Z"]:
        src = key[label]
        score = _get_overall_score(rec, src)
        if src == "C_human":
            score_str = " — qualitative only (no numeric grade)"
        elif score is not None:
            score_str = f" — system overall_score: {score}/5"
        else:
            score_str = " — system overall_score: (not found)"
        lines.append(f"- **{label}** = {SOURCE_LABELS.get(src, src)}{score_str}")
    lines.append("")
    return "\n".join(lines)

def render_index_md(records):
    lines = []
    lines.append("# Experiment pilot — index")
    lines.append("")
    lines.append(f"{len(records)} essays. Each linked file contains the original essay plus three feedbacks (X/Y/Z) and a source mapping for reviewer reference.")
    lines.append("")
    lines.append("| Essay | Words | X | Y | Z |")
    lines.append("|---|---|---|---|---|")
    for rec in records:
        eid = rec["essay_id"]
        words = len(rec["essay_text"].split())
        key = rec["key"]
        x_src = key["X"].replace("_", " ")
        y_src = key["Y"].replace("_", " ")
        z_src = key["Z"].replace("_", " ")
        lines.append(f"| [{eid}](./{eid}.md) | {words} | {x_src} | {y_src} | {z_src} |")
    lines.append("")
    return "\n".join(lines)

records = []
for p in sorted(SRC_DIR.glob("leaf_*.json")):
    with open(p) as f:
        rec = json.load(f)
    records.append(rec)
    out_path = OUT_DIR / f"{rec['essay_id']}.md"
    out_path.write_text(render_essay_md(rec), encoding="utf-8")
    print(f"wrote {out_path}")

index_path = OUT_DIR / "README.md"
index_path.write_text(render_index_md(records), encoding="utf-8")
print(f"\nindex: {index_path}")
print(f"total: {len(records)} essays")
