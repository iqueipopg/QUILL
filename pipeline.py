"""
MAWF Pipeline — Multi-Agent Written Feedback
Runs the 5-agent pipeline: A1→A2→A3→A4→A5

Usage:
    python pipeline.py --essay essay.txt --rubric rubric.txt
    python pipeline.py --essay essay.txt  # without rubric
"""
import argparse
import json
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from agents.agent1_structure import Agent1Structure
from agents.agent2_content import Agent2Content
from agents.agent3_language import Agent3Language
from agents.agent4_synthesizer import Agent4Synthesizer
from agents.agent5_moderator import Agent5Moderator
from agents.logger import get_logger

logger = get_logger("Pipeline")


def _share_model(source, target):
    """Share a loaded model from source agent to target agent (no-op for API backends)."""
    if source.backend != "local":
        return
    target.model = source.model
    target.tokenizer = source.tokenizer
    target._loaded_path = source._loaded_path
    target._has_chat_template = source._has_chat_template


def _run_eval_agent(agent, essay, rubric):
    """Run a single evaluation agent and return (key, result, elapsed)."""
    t = time.time()
    result = agent.evaluate(essay, rubric)
    elapsed = round(time.time() - t, 1)
    return result, elapsed


def run_pipeline(essay, rubric=None, output_dir="./outputs"):
    """Run the full 5-agent feedback pipeline.

    Supports parallel A1-A3 evaluation when configured (needs enough VRAM
    for separate model instances). Falls back to sequential with model reuse.

    Args:
        essay: Student essay text.
        rubric: Optional rubric/prompt text.
        output_dir: Directory to save outputs.

    Returns:
        dict with all intermediate and final results.
    """
    import yaml
    with open("config.yaml") as f:
        config = yaml.safe_load(f) or {}

    parallel = config.get("pipeline", {}).get("parallel_evaluation", False)
    sleep_between_agents = 5 if config.get("backend") in ("groq", "gemini") else 0

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    results = {"essay_length": len(essay), "rubric_provided": rubric is not None}
    t_start = time.time()

    # ── Phase 1: Evaluation (A1, A2, A3) ─────────────────────────
    logger.info("=" * 60)
    logger.info("PHASE 1: Evaluation (A1 Structure, A2 Content, A3 Language)")
    logger.info("  mode: %s", "PARALLEL" if parallel else "sequential")
    logger.info("=" * 60)

    a1 = Agent1Structure()
    a2 = Agent2Content()
    a3 = Agent3Language()

    if parallel:
        # Each agent loads its own model instance — needs ~3x VRAM
        logger.info("Loading 3 model instances for parallel evaluation...")
        a1.load_model()
        a2.load_model()
        a3.load_model()

        with ThreadPoolExecutor(max_workers=3) as pool:
            futures = {
                pool.submit(_run_eval_agent, a1, essay, rubric): "a1",
                pool.submit(_run_eval_agent, a2, essay, rubric): "a2",
                pool.submit(_run_eval_agent, a3, essay, rubric): "a3",
            }
            for future in as_completed(futures):
                key = futures[future]
                result, elapsed = future.result()
                if key == "a1":
                    results["a1_structure"] = result
                    results["a1_elapsed_s"] = elapsed
                elif key == "a2":
                    results["a2_content"] = result
                    results["a2_elapsed_s"] = elapsed
                else:
                    results["a3_language"] = result
                    results["a3_elapsed_s"] = elapsed
                logger.info("%s done in %.1fs", key.upper(), elapsed)

        # Free extra model instances, keep a1's for later phases
        a2.free_vram()
        a3.free_vram()
    else:
        # Sequential with model reuse (single GPU)
        t = time.time()
        a1.load_model()
        results["a1_structure"] = a1.evaluate(essay, rubric)
        results["a1_elapsed_s"] = round(time.time() - t, 1)
        logger.info("A1 done in %.1fs", results["a1_elapsed_s"])
        if sleep_between_agents:
            time.sleep(sleep_between_agents)

        t = time.time()
        _share_model(a1, a2)
        results["a2_content"] = a2.evaluate(essay, rubric)
        results["a2_elapsed_s"] = round(time.time() - t, 1)
        logger.info("A2 done in %.1fs", results["a2_elapsed_s"])
        if sleep_between_agents:
            time.sleep(sleep_between_agents)

        t = time.time()
        _share_model(a1, a3)
        results["a3_language"] = a3.evaluate(essay, rubric)
        results["a3_elapsed_s"] = round(time.time() - t, 1)
        logger.info("A3 done in %.1fs", results["a3_elapsed_s"])

    if sleep_between_agents:
        time.sleep(sleep_between_agents)

    # ── Phase 2: Synthesis (A4) ──────────────────────────────────
    logger.info("=" * 60)
    logger.info("PHASE 2: Synthesis (A4 Synthesizer)")
    logger.info("=" * 60)

    t = time.time()
    a4 = Agent4Synthesizer()
    _share_model(a1, a4)
    results["a4_synthesized"] = a4.synthesize(
        results["a1_structure"],
        results["a2_content"],
        results["a3_language"],
        essay=essay,
        rubric=rubric,
    )
    results["a4_elapsed_s"] = round(time.time() - t, 1)
    logger.info("A4 done in %.1fs", results["a4_elapsed_s"])

    if sleep_between_agents:
        time.sleep(sleep_between_agents)

    # ── Phase 3: Moderation (A5) ─────────────────────────────────
    logger.info("=" * 60)
    logger.info("PHASE 3: Moderation (A5 Moderator)")
    logger.info("=" * 60)

    t = time.time()
    a5 = Agent5Moderator()
    _share_model(a1, a5)
    results["a5_moderated"] = a5.moderate(results["a4_synthesized"], essay=essay)
    results["a5_elapsed_s"] = round(time.time() - t, 1)
    logger.info("A5 done in %.1fs", results["a5_elapsed_s"])

    # ── Cleanup ──────────────────────────────────────────────────
    a1.free_vram()

    results["total_elapsed_s"] = round(time.time() - t_start, 1)
    logger.info("=" * 60)
    logger.info("Pipeline complete in %.1fs", results["total_elapsed_s"])

    # ── Save ─────────────────────────────────────────────────────
    ts = time.strftime("%Y%m%d_%H%M%S")
    out_path = output_dir / f"feedback_{ts}.json"
    with open(out_path, "w") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    logger.info("Output saved to %s", out_path)

    return results


def print_feedback(results):
    """Pretty-print the final moderated feedback to console."""
    feedback = results.get("a5_moderated", {}).get("moderated_feedback", {})
    if not feedback:
        feedback = results.get("a4_synthesized", {})

    print("\n" + "=" * 60)
    print("FEEDBACK REPORT")
    print("=" * 60)

    if feedback.get("summary"):
        print(f"\nOverall ({feedback.get('overall_score', '?')}/5): {feedback['summary']}")

    for section in ["structure_feedback", "content_feedback", "language_feedback"]:
        if feedback.get(section):
            title = section.replace("_feedback", "").upper()
            print(f"\n--- {title} ---")
            print(feedback[section])

    if feedback.get("priority_actions"):
        print("\n--- PRIORITY ACTIONS ---")
        for i, action in enumerate(feedback["priority_actions"], 1):
            print(f"  {i}. {action}")

    mod_summary = results.get("a5_moderated", {}).get("moderation_summary", {})
    if mod_summary:
        print(f"\n[Moderation: {mod_summary.get('changes_made', 0)} changes made]")

    print("=" * 60)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="MAWF: Multi-Agent Written Feedback")
    parser.add_argument("--essay", required=True, help="Path to student essay text file")
    parser.add_argument("--rubric", default=None, help="Path to rubric/prompt text file")
    parser.add_argument("--output-dir", default="./outputs", help="Output directory")
    args = parser.parse_args()

    essay_text = Path(args.essay).read_text(encoding="utf-8")
    rubric_text = Path(args.rubric).read_text(encoding="utf-8") if args.rubric else None

    results = run_pipeline(essay_text, rubric_text, args.output_dir)
    print_feedback(results)
