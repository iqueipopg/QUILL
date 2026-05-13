"""Agent 1: Structure Analyzer
Evaluates macro-structure, paragraph coherence, logical flow, and transitions.
"""
from agents.base import BaseAgent

SYSTEM_PROMPT = (
    "You are an expert writing evaluator specializing in essay structure analysis. "
    "You evaluate ONLY the structural aspects of student writing: "
    "introduction presence and quality, body paragraph organization, conclusion, "
    "logical flow between paragraphs, and use of transitions.\n\n"
    "You do NOT evaluate grammar, spelling, content accuracy, or argumentation quality — "
    "other specialists handle those dimensions.\n\n"
    "Always respond in valid JSON with this exact schema:\n"
    '{\n'
    '  "has_introduction": true/false,\n'
    '  "has_conclusion": true/false,\n'
    '  "paragraph_count": <int>,\n'
    '  "logical_flow_score": <1-5>,\n'
    '  "transition_quality_score": <1-5>,\n'
    '  "overall_structure_score": <1-5>,\n'
    '  "strengths": ["..."],\n'
    '  "weaknesses": ["..."],\n'
    '  "suggestions": ["..."]\n'
    '}\n\n'
    'CRITICAL: Use these exact JSON keys, do NOT paraphrase: '
    'has_introduction, has_conclusion, paragraph_count, logical_flow_score, '
    'transition_quality_score, overall_structure_score, strengths, weaknesses, '
    'suggestions.'
)


class Agent1Structure(BaseAgent):
    def __init__(self):
        super().__init__("agent1_structure")
        cfg = self.config.get("structure", {})
        self.temperature = cfg.get("temperature", 0.2)
        self.max_tokens = cfg.get("max_tokens", 600)

    def evaluate(self, essay, rubric=None):
        """Evaluate the structural quality of a student essay.

        Args:
            essay: The student's written text.
            rubric: Optional assignment rubric/prompt for context.

        Returns:
            dict with structure evaluation, or None on parse failure.
        """
        self.load_model()

        prompt = "Evaluate the STRUCTURE of the following student essay.\n\n"
        if rubric:
            prompt += f"ASSIGNMENT RUBRIC:\n{rubric}\n\n"
        prompt += f"STUDENT ESSAY:\n{essay}\n\n"
        prompt += "Respond ONLY with the JSON evaluation."

        result, raw = self.generate_json(
            prompt,
            max_new_tokens=self.max_tokens,
            temperature=self.temperature,
            system_prompt=SYSTEM_PROMPT,
            schema_keys=["overall_structure_score", "strengths", "suggestions"],
        )

        if result is None:
            self.logger.warning("Failed to parse JSON from A1 output: %s", raw[:200])
            return {"parse_error": True, "raw_output": raw}

        self.logger.info(
            "A1 Structure: overall=%s, flow=%s, transitions=%s",
            result.get("overall_structure_score"),
            result.get("logical_flow_score"),
            result.get("transition_quality_score"),
        )
        return result
