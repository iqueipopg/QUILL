"""Agent 3: Language Quality Assessor
Assesses grammar, vocabulary, academic register, and clarity.
"""
from agents.base import BaseAgent

SYSTEM_PROMPT = (
    "You are an expert writing evaluator specializing in language quality assessment. "
    "You evaluate ONLY the linguistic aspects of student writing: "
    "grammar correctness, spelling, vocabulary range and appropriateness, "
    "academic register, sentence variety, and overall clarity.\n\n"
    "You do NOT evaluate essay structure, content accuracy, or argumentation — "
    "other specialists handle those dimensions.\n\n"
    "Always respond in valid JSON with this exact schema:\n"
    '{\n'
    '  "grammar_score": <1-5>,\n'
    '  "vocabulary_score": <1-5>,\n'
    '  "academic_register_score": <1-5>,\n'
    '  "clarity_score": <1-5>,\n'
    '  "sentence_variety_score": <1-5>,\n'
    '  "overall_language_score": <1-5>,\n'
    '  "error_annotations": [\n'
    '    {"original": "...", "corrected": "...", "error_type": "grammar/spelling/word_choice/register"}\n'
    '  ],\n'
    '  "strengths": ["..."],\n'
    '  "suggestions": ["..."]\n'
    '}\n\n'
    'CRITICAL: Use these exact JSON keys, do NOT paraphrase: '
    'grammar_score, vocabulary_score, academic_register_score, clarity_score, '
    'sentence_variety_score, overall_language_score, error_annotations, strengths, '
    'suggestions. Do not invent synonyms like "sentence_variability_score" or '
    '"overall_language_quality_score".'
)


class Agent3Language(BaseAgent):
    def __init__(self):
        super().__init__("agent3_language")
        cfg = self.config.get("language", {})
        self.temperature = cfg.get("temperature", 0.2)
        self.max_tokens = cfg.get("max_tokens", 600)

    def evaluate(self, essay, rubric=None):
        """Evaluate the language quality of a student essay.

        Args:
            essay: The student's written text.
            rubric: Optional rubric for context (e.g., expected register level).

        Returns:
            dict with language evaluation, or None on parse failure.
        """
        self.load_model()

        prompt = "Evaluate the LANGUAGE QUALITY of the following student essay.\n\n"
        if rubric:
            prompt += f"ASSIGNMENT CONTEXT:\n{rubric}\n\n"
        prompt += f"STUDENT ESSAY:\n{essay}\n\n"
        prompt += (
            "Identify specific errors with corrections. "
            "Respond ONLY with the JSON evaluation.\n"
            "Respond ONLY with the JSON object using the EXACT key names from the schema."
        )

        result, raw = self.generate_json(
            prompt,
            max_new_tokens=self.max_tokens,
            temperature=self.temperature,
            system_prompt=SYSTEM_PROMPT,
            schema_keys=["overall_language_score", "grammar_score", "error_annotations"],
        )

        if result is None:
            self.logger.warning("Failed to parse JSON from A3 output: %s", raw[:200])
            return {"parse_error": True, "raw_output": raw}

        self.logger.info(
            "A3 Language: overall=%s, grammar=%s, vocabulary=%s, errors=%d",
            result.get("overall_language_score"),
            result.get("grammar_score"),
            result.get("vocabulary_score"),
            len(result.get("error_annotations", [])),
        )
        return result
