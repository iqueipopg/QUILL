"""
Single-Prompt Baseline — Condition A for comparison experiment.
One LLM call with a comprehensive prompt asking for holistic feedback.
Uses the same model as the multi-agent pipeline.
"""
import json
import time
from pathlib import Path

from agents.base import BaseAgent
from agents.logger import get_logger

logger = get_logger("Baseline")

BASELINE_SYSTEM_PROMPT = (
    "You are an expert writing evaluator. Provide comprehensive feedback on a student's "
    "essay covering ALL of the following dimensions:\n"
    "1. STRUCTURE: introduction, body, conclusion, logical flow, transitions\n"
    "2. CONTENT: thesis, prompt adherence, evidence, argumentation\n"
    "3. LANGUAGE: grammar, vocabulary, academic register, clarity\n\n"
    "Guidelines:\n"
    "- Write in second person ('You did well...', 'Consider improving...')\n"
    "- Balance positive and constructive feedback\n"
    "- Be specific and actionable\n"
    "- Keep a supportive tone\n\n"
    "Always respond in valid JSON with this exact schema:\n"
    '{\n'
    '  "overall_score": <1-5>,\n'
    '  "summary": "1-2 sentence overall assessment",\n'
    '  "structure_feedback": "paragraph with structure feedback",\n'
    '  "content_feedback": "paragraph with content feedback",\n'
    '  "language_feedback": "paragraph with language feedback",\n'
    '  "priority_actions": ["action 1", "action 2", "action 3"]\n'
    '}'
)


class BaselineAgent(BaseAgent):
    """Single-prompt baseline for comparison with multi-agent pipeline."""

    def __init__(self):
        super().__init__("agent1_structure")  # reuse same model config
        cfg = self.config.get("baseline", {})
        self.temperature = cfg.get("temperature", 0.4)
        self.max_tokens = cfg.get("max_tokens", 1000)

    def evaluate(self, essay, rubric=None):
        self.load_model()

        prompt = "Provide comprehensive feedback on the following student essay.\n\n"
        if rubric:
            prompt += f"ASSIGNMENT RUBRIC/PROMPT:\n{rubric}\n\n"
        prompt += f"STUDENT ESSAY:\n{essay}\n\n"
        prompt += "Respond ONLY with the JSON feedback."

        result, raw = self.generate_json(
            prompt,
            max_new_tokens=self.max_tokens,
            temperature=self.temperature,
            system_prompt=BASELINE_SYSTEM_PROMPT,
        )

        if result is None or not isinstance(result, dict):
            logger.warning(
                "Failed to parse baseline JSON (got %s): %s",
                type(result).__name__, str(raw)[:200],
            )
            return {"parse_error": True, "raw_output": raw, "reason": "non_dict_response"}

        logger.info("Baseline: overall_score=%s", result.get("overall_score"))
        return result


def run_baseline(essay, rubric=None, output_dir="./outputs"):
    """Run single-prompt baseline evaluation."""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    t_start = time.time()
    agent = BaselineAgent()
    result = agent.evaluate(essay, rubric)
    elapsed = round(time.time() - t_start, 1)
    agent.free_vram()

    output = {
        "condition": "A_single_prompt",
        "essay_length": len(essay),
        "rubric_provided": rubric is not None,
        "feedback": result,
        "elapsed_s": elapsed,
    }

    ts = time.strftime("%Y%m%d_%H%M%S")
    out_path = output_dir / f"baseline_{ts}.json"
    with open(out_path, "w") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)
    logger.info("Baseline done in %.1fs — saved to %s", elapsed, out_path)

    return output


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Single-prompt baseline feedback")
    parser.add_argument("--essay", required=True)
    parser.add_argument("--rubric", default=None)
    parser.add_argument("--output-dir", default="./outputs")
    args = parser.parse_args()

    essay_text = Path(args.essay).read_text(encoding="utf-8")
    rubric_text = Path(args.rubric).read_text(encoding="utf-8") if args.rubric else None
    run_baseline(essay_text, rubric_text, args.output_dir)
