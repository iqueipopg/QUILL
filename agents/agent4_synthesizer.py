"""Agent 4: Feedback Synthesizer
Merges A1-A3 evaluations into a single, coherent, student-facing feedback report.
"""
import json
from agents.base import BaseAgent

SYSTEM_PROMPT = (
    "You are an expert educational feedback writer. Your job is to synthesize "
    "evaluations from three specialists (structure, content, language) into a single, "
    "coherent feedback report for a student.\n\n"
    "Guidelines:\n"
    "- Write in second person ('You did well...', 'Consider improving...')\n"
    "- Balance positive feedback with constructive criticism (start with strengths)\n"
    "- Make suggestions specific and actionable (not vague like 'improve your writing')\n"
    "- Organize by dimension: Structure, Content, Language\n"
    "- End with 2-3 priority action items\n"
    "- Keep a supportive, encouraging tone\n"
    "- Do NOT invent issues not mentioned by the specialists\n\n"
    "Always respond in valid JSON with this exact schema:\n"
    '{\n'
    '  "overall_score": <1-5>,\n'
    '  "summary": "1-2 sentence overall assessment",\n'
    '  "structure_feedback": "paragraph with structure feedback",\n'
    '  "content_feedback": "paragraph with content feedback",\n'
    '  "language_feedback": "paragraph with language feedback",\n'
    '  "priority_actions": ["action 1", "action 2", "action 3"]\n'
    '}\n\n'
    'CRITICAL: Use these exact JSON keys, do NOT paraphrase: '
    'overall_score, summary, structure_feedback, content_feedback, '
    'language_feedback, priority_actions.'
)


class Agent4Synthesizer(BaseAgent):
    def __init__(self):
        super().__init__("agent4_synthesizer")
        cfg = self.config.get("synthesizer", {})
        self.temperature = cfg.get("temperature", 0.5)
        self.max_tokens = cfg.get("max_tokens", 800)

    def synthesize(self, structure_eval, content_eval, language_eval, essay=None, rubric=None):
        """Synthesize three evaluations into unified student feedback.

        Args:
            structure_eval: Output from Agent1 (dict).
            content_eval: Output from Agent2 (dict).
            language_eval: Output from Agent3 (dict).
            essay: Optional original essay for reference.
            rubric: Optional rubric for context.

        Returns:
            dict with synthesized feedback.
        """
        self.load_model()

        prompt = (
            "Synthesize the following three specialist evaluations into a single, "
            "coherent feedback report for the student.\n\n"
        )

        prompt += "=== STRUCTURE EVALUATION (A1) ===\n"
        prompt += json.dumps(structure_eval, indent=2) + "\n\n"

        prompt += "=== CONTENT EVALUATION (A2) ===\n"
        prompt += json.dumps(content_eval, indent=2) + "\n\n"

        prompt += "=== LANGUAGE EVALUATION (A3) ===\n"
        prompt += json.dumps(language_eval, indent=2) + "\n\n"

        if rubric:
            prompt += f"ASSIGNMENT RUBRIC:\n{rubric}\n\n"

        prompt += "Respond ONLY with the JSON feedback report."

        result, raw = self.generate_json(
            prompt,
            max_new_tokens=self.max_tokens,
            temperature=self.temperature,
            system_prompt=SYSTEM_PROMPT,
            schema_keys=["overall_score", "summary", "priority_actions"],
        )

        if result is None:
            self.logger.warning("Failed to parse JSON from A4 output: %s", raw[:200])
            return {"parse_error": True, "raw_output": raw}

        self.logger.info("A4 Synthesizer: overall_score=%s", result.get("overall_score"))
        return result
