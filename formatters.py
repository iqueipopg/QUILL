"""Output formatters extracted from run_experiment.py so the web app
can render Condition A (baseline) and Condition B (multi-agent pipeline)
identically to the experiment outputs.

Importing run_experiment directly is not safe (it runs the full experiment
loop at module load), hence this small extraction.
"""

__all__ = [
    "format_annotations",
    "prose_from_components",
    "extract_a_text",
    "extract_b_text",
]


def format_annotations(annotations):
    """Format A3's error_annotations into a 'Specific corrections' block.
    Returns empty string if no usable annotations.
    """
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


def prose_from_components(summary, structure_fb, content_fb, language_fb, priority_actions):
    """Assemble feedback components into plain prose paragraphs."""
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


def extract_a_text(baseline_result):
    """Baseline (Condition A) → plain prose."""
    if not isinstance(baseline_result, dict) or baseline_result.get("parse_error"):
        return "[PARSE ERROR]"
    return prose_from_components(
        summary=baseline_result.get("summary"),
        structure_fb=baseline_result.get("structure_feedback"),
        content_fb=baseline_result.get("content_feedback"),
        language_fb=baseline_result.get("language_feedback"),
        priority_actions=baseline_result.get("priority_actions") or [],
    )


def extract_b_text(pipeline_result):
    """Pipeline (Condition B) → plain prose + appended 'Specific corrections' from A3."""
    final = pipeline_result.get("moderated_feedback") or pipeline_result.get("final_feedback") or {}
    if isinstance(final, dict) and "moderated_feedback" in final:
        final = final["moderated_feedback"]
    if not final:
        a5 = pipeline_result.get("a5_moderated", {})
        final = a5.get("moderated_feedback") or pipeline_result.get("a4_synthesized", {})
    if not isinstance(final, dict):
        final = {}
    main = prose_from_components(
        summary=final.get("summary"),
        structure_fb=final.get("structure_feedback"),
        content_fb=final.get("content_feedback"),
        language_fb=final.get("language_feedback"),
        priority_actions=final.get("priority_actions") or [],
    )
    annotations = pipeline_result.get("a3_language", {}).get("error_annotations")
    corrections_block = format_annotations(annotations) if annotations else ""
    if corrections_block:
        return main + "\n\n" + corrections_block
    return main
