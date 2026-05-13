"""Agent 2: Content Alignment Evaluator
Checks whether the student addresses the assignment prompt and satisfies rubric criteria.
"""
from agents.base import BaseAgent

SYSTEM_PROMPT = (
    "You are an expert writing evaluator specializing in content alignment analysis. "
    "You evaluate ONLY whether the student's response addresses the assignment prompt "
    "and covers the required rubric criteria: thesis statement, supporting evidence, "
    "argumentation depth, and topic relevance.\n\n"
    "You do NOT evaluate grammar, structure, or language quality — "
    "other specialists handle those dimensions.\n\n"
    "Always respond in valid JSON with this exact schema:\n"
    '{\n'
    '  "thesis_present": true/false,\n'
    '  "thesis_quality_score": <1-5>,\n'
    '  "prompt_adherence_score": <1-5>,\n'
    '  "evidence_quality_score": <1-5>,\n'
    '  "argumentation_depth_score": <1-5>,\n'
    '  "overall_content_score": <1-5>,\n'
    '  "rubric_coverage": [\n'
    '    {"criterion": "...", "status": "met/partially_met/not_met", "comment": "..."}\n'
    '  ],\n'
    '  "strengths": ["..."],\n'
    '  "weaknesses": ["..."],\n'
    '  "suggestions": ["..."]\n'
    '}\n\n'
    'CRITICAL: Use these exact JSON keys, do NOT paraphrase: '
    'thesis_present, thesis_quality_score, prompt_adherence_score, '
    'evidence_quality_score, argumentation_depth_score, overall_content_score, '
    'rubric_coverage, strengths, weaknesses, suggestions.'
)


class Agent2Content(BaseAgent):
    def __init__(self):
        super().__init__("agent2_content")
        cfg = self.config.get("content", {})
        self.temperature = cfg.get("temperature", 0.2)
        self.max_tokens = cfg.get("max_tokens", 600)

    def evaluate(self, essay, rubric=None):
        """Evaluate content alignment of a student essay against the rubric.

        Args:
            essay: The student's written text.
            rubric: The assignment prompt or rubric (strongly recommended).

        Returns:
            dict with content evaluation, or None on parse failure.
        """
        self.load_model()

        prompt = "Evaluate the CONTENT ALIGNMENT of the following student essay.\n\n"
        if rubric:
            prompt += f"ASSIGNMENT RUBRIC/PROMPT:\n{rubric}\n\n"
            prompt += (
                "For each rubric criterion, indicate whether it is met, partially met, "
                "or not met, with a brief comment.\n\n"
            )
        else:
            prompt += (
                "No rubric was provided. Evaluate based on general academic writing "
                "expectations: clear thesis, evidence, and argumentation.\n\n"
            )
        prompt += f"STUDENT ESSAY:\n{essay}\n\n"
        prompt += "Respond ONLY with the JSON evaluation."

        result, raw = self.generate_json(
            prompt,
            max_new_tokens=self.max_tokens,
            temperature=self.temperature,
            system_prompt=SYSTEM_PROMPT,
            schema_keys=["overall_content_score", "strengths", "suggestions"],
        )

        if result is None:
            self.logger.warning("Failed to parse JSON from A2 output: %s", raw[:200])
            return {"parse_error": True, "raw_output": raw}

        self.logger.info(
            "A2 Content: overall=%s, thesis=%s, evidence=%s",
            result.get("overall_content_score"),
            result.get("thesis_quality_score"),
            result.get("evidence_quality_score"),
        )
        return result
