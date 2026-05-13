"""Agent 5: Moderation Filter
Reviews synthesized feedback for tone, removing harsh, biased, or vague comments.
Ensures feedback is constructive, specific, and culturally sensitive.
"""
import json
from agents.base import BaseAgent

SYSTEM_PROMPT = (
    "You are a feedback moderator for education. Review AI-generated feedback and fix issues.\n"
    "Rules: (1) Rephrase harsh or condescending language. (2) Replace vague comments with "
    "actionable suggestions. (3) Remove bias against ESL or non-standard writing styles. "
    "(4) Keep genuine strengths. (5) Do NOT add new feedback.\n\n"
    "Respond ONLY in valid JSON:\n"
    '{"moderated_feedback": {"overall_score": <1-5>, "summary": "...", '
    '"structure_feedback": "...", "content_feedback": "...", "language_feedback": "...", '
    '"priority_actions": ["..."]}, '
    '"moderation_log": [{"action": "rephrased/removed/flagged", "original": "...", "reason": "..."}], '
    '"moderation_summary": {"changes_made": <int>, "tone_issues": <int>, '
    '"bias_flags": <int>, "vague_replacements": <int>}}\n\n'
    'CRITICAL: Use these exact top-level JSON keys, do NOT paraphrase: '
    'moderated_feedback, moderation_log, moderation_summary. Inside '
    'moderated_feedback use: overall_score, summary, structure_feedback, '
    'content_feedback, language_feedback, priority_actions. Inside '
    'moderation_summary use: changes_made, tone_issues, bias_flags, '
    'vague_replacements.'
)


class Agent5Moderator(BaseAgent):
    def __init__(self):
        super().__init__("agent5_moderator")
        cfg = self.config.get("moderator", {})
        self.temperature = cfg.get("temperature", 0.2)
        self.max_tokens = cfg.get("max_tokens", 600)

    def moderate(self, synthesized_feedback, essay=None):
        """Moderate synthesized feedback for tone, bias, and specificity.

        Args:
            synthesized_feedback: Output from Agent4 (dict).
            essay: Optional original essay for context.

        Returns:
            dict with moderated feedback and moderation log.
        """
        self.load_model()

        # Build a compact prompt — only send the feedback, not the full essay
        prompt = (
            "Moderate the following student feedback. Fix tone, bias, and vague comments.\n\n"
            "=== FEEDBACK ===\n"
        )
        prompt += json.dumps(synthesized_feedback, indent=1) + "\n\n"

        if essay:
            # Only include a short excerpt for context, not the full essay
            excerpt = essay[:500] + ("..." if len(essay) > 500 else "")
            prompt += f"=== ESSAY EXCERPT (context only) ===\n{excerpt}\n\n"

        prompt += "Respond ONLY with JSON. List ALL changes in moderation_log."

        result, raw = self.generate_json(
            prompt,
            max_new_tokens=self.max_tokens,
            temperature=self.temperature,
            system_prompt=SYSTEM_PROMPT,
            schema_keys=["moderated_feedback", "moderation_log", "moderation_summary"],
        )

        if result is None:
            self.logger.warning("Failed to parse JSON from A5 output: %s", raw[:200])
            return {
                "moderated_feedback": synthesized_feedback,
                "moderation_log": [],
                "moderation_summary": {
                    "changes_made": 0,
                    "tone_issues": 0,
                    "bias_flags": 0,
                    "vague_replacements": 0,
                    "note": "Moderation parse failed — feedback passed through unmoderated",
                },
            }

        # Validate moderation_log count matches changes_made
        summary = result.get("moderation_summary", {})
        log = result.get("moderation_log", [])
        if summary.get("changes_made", 0) != len(log):
            self.logger.warning(
                "moderation_log count (%d) != changes_made (%d) — correcting",
                len(log), summary.get("changes_made", 0),
            )
            summary["changes_made"] = len(log)

        self.logger.info(
            "A5 Moderator: %d changes (tone=%d, bias=%d, vague=%d)",
            summary.get("changes_made", 0),
            summary.get("tone_issues", 0),
            summary.get("bias_flags", 0),
            summary.get("vague_replacements", 0),
        )
        return result
