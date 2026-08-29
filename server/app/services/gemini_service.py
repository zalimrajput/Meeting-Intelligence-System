"""Google Gemini API service for Stage 2 Meeting Intelligence Extraction.

Extracts summaries, action items, decisions, deadlines, unresolved issues,
and sentiment analysis from diarized meeting transcripts using Gemini 2.5 Flash
with structured JSON response schemas.
"""

import json
import logging
import re
from dataclasses import dataclass
from typing import Any

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)

GEMINI_API_BASE = "https://generativelanguage.googleapis.com/v1beta/models"


@dataclass
class KeyPointItem:
    point_text: str
    timestamp_seconds: float | None = None


@dataclass
class ActionItemDTO:
    task_description: str
    assigned_to: str | None = None
    deadline_raw_text: str | None = None
    deadline_date: str | None = None  # ISO format "YYYY-MM-DD"
    timestamp_seconds: float | None = None


@dataclass
class DecisionDTO:
    decision_text: str
    decided_by: str | None = None
    timestamp_seconds: float | None = None


@dataclass
class UnresolvedIssueDTO:
    issue_text: str
    timestamp_seconds: float | None = None


@dataclass
class FollowUpDTO:
    description: str
    timestamp_seconds: float | None = None


@dataclass
class DeadlineDTO:
    description: str
    raw_text: str
    resolved_date: str | None = None
    timestamp_seconds: float | None = None


@dataclass
class MeetingIntelligenceResult:
    """Full intelligence analysis extracted from a meeting transcript."""

    title: str
    summary_short: str
    summary_detailed: str
    sentiment: str  # 'positive' | 'neutral' | 'negative' | 'mixed'
    sentiment_score: float  # -1.0 to 1.0
    key_points: list[KeyPointItem]
    action_items: list[ActionItemDTO]
    decisions: list[DecisionDTO]
    unresolved_issues: list[UnresolvedIssueDTO]
    follow_up_items: list[FollowUpDTO]
    deadlines: list[DeadlineDTO]
    raw_response: dict[str, Any]


class GeminiService:
    """Service communicating with Google Gemini API for structured extraction."""

    def __init__(self, api_key: str | None = None, model: str = "gemini-2.5-flash") -> None:
        self.api_key = api_key or settings.GEMINI_API_KEY
        self.model = model
        if not self.api_key:
            logger.warning("GEMINI_API_KEY is not configured in settings.")

    def _build_url(self) -> str:
        """Constructs the Gemini generateContent API endpoint URL."""
        return f"{GEMINI_API_BASE}/{self.model}:generateContent?key={self.api_key}"

    def _build_extraction_prompt(self, transcript: str) -> str:
        """Constructs the comprehensive system and analysis prompt for Gemini."""
        return f"""You are an elite AI Meeting Intelligence Analyst.
Analyze the following diarized meeting transcript and extract structured meeting takeaways.

Transcript:
\"\"\"
{transcript}
\"\"\"

Instructions:
1. Provide an updated descriptive meeting title.
2. Provide a 2-3 sentence executive summary (summary_short).
3. Provide a comprehensive detailed multi-paragraph meeting recap (summary_detailed).
4. Extract key discussion points with timestamp references (in seconds) if mentioned.
5. Identify all action items with:
   - task_description: Clear imperative task statement.
   - assigned_to: Name or speaker label of the assigned person (or null).
   - deadline_raw_text: Natural language deadline text like 'by Friday' (or null).
   - deadline_date: Estimated ISO format 'YYYY-MM-DD' if reasonably deducible (or null).
   - timestamp_seconds: Spoken timestamp in seconds (or null).
6. Extract all decisions agreed upon during the meeting.
7. Identify unresolved issues, open blockers, or topics tabled for later.
8. Identify follow-up items or reminders.
9. Detect explicit deadlines mentioned.
10. Determine overall meeting sentiment ('positive', 'neutral', 'negative', or 'mixed') and a score between -1.0 and 1.0.

You MUST respond strictly with a valid JSON object following this exact JSON schema:
{{
  "title": "string",
  "summary_short": "string",
  "summary_detailed": "string",
  "sentiment": "positive | neutral | negative | mixed",
  "sentiment_score": 0.0,
  "key_points": [
    {{ "point_text": "string", "timestamp_seconds": 0.0 }}
  ],
  "action_items": [
    {{
      "task_description": "string",
      "assigned_to": "string or null",
      "deadline_raw_text": "string or null",
      "deadline_date": "YYYY-MM-DD or null",
      "timestamp_seconds": 0.0
    }}
  ],
  "decisions": [
    {{
      "decision_text": "string",
      "decided_by": "string or null",
      "timestamp_seconds": 0.0
    }}
  ],
  "unresolved_issues": [
    {{
      "issue_text": "string",
      "timestamp_seconds": 0.0
    }}
  ],
  "follow_up_items": [
    {{
      "description": "string",
      "timestamp_seconds": 0.0
    }}
  ],
  "deadlines": [
    {{
      "description": "string",
      "raw_text": "string",
      "resolved_date": "YYYY-MM-DD or null",
      "timestamp_seconds": 0.0
    }}
  ]
}}
"""

    def parse_gemini_json(self, raw_json_str: str) -> MeetingIntelligenceResult:
        """Parses and sanitizes the JSON response from Gemini."""
        clean_text = raw_json_str.strip()
        # Remove potential markdown code fences ```json ... ```
        if clean_text.startswith("```json"):
            clean_text = clean_text[7:]
        elif clean_text.startswith("```"):
            clean_text = clean_text[3:]
        if clean_text.endswith("```"):
            clean_text = clean_text[:-3]
        clean_text = clean_text.strip()

        try:
            data = json.loads(clean_text)
        except json.JSONDecodeError as err:
            logger.error("Failed to parse Gemini JSON: %s (Raw: %s)", err, clean_text[:200])
            # Attempt to extract JSON substring
            match = re.search(r"(\{.*\})", clean_text, re.DOTALL)
            if match:
                data = json.loads(match.group(1))
            else:
                raise ValueError(f"Invalid JSON from Gemini: {err}") from err

        title = str(data.get("title", "Meeting Summary")).strip()
        summary_short = str(data.get("summary_short", "")).strip()
        summary_detailed = str(data.get("summary_detailed", "")).strip()

        raw_sentiment = str(data.get("sentiment", "neutral")).lower()
        if raw_sentiment not in ["positive", "neutral", "negative", "mixed"]:
            raw_sentiment = "neutral"

        try:
            sentiment_score = float(data.get("sentiment_score", 0.0))
            sentiment_score = max(-1.0, min(1.0, sentiment_score))
        except (ValueError, TypeError):
            sentiment_score = 0.0

        # Parse key points
        key_points = []
        for kp in data.get("key_points", []):
            if isinstance(kp, dict) and kp.get("point_text"):
                key_points.append(
                    KeyPointItem(
                        point_text=str(kp["point_text"]).strip(),
                        timestamp_seconds=(
                            float(kp["timestamp_seconds"])
                            if kp.get("timestamp_seconds") is not None
                            else None
                        ),
                    )
                )
            elif isinstance(kp, str) and kp.strip():
                key_points.append(KeyPointItem(point_text=kp.strip()))

        # Parse action items
        action_items = []
        for act in data.get("action_items", []):
            if isinstance(act, dict) and act.get("task_description"):
                action_items.append(
                    ActionItemDTO(
                        task_description=str(act["task_description"]).strip(),
                        assigned_to=str(act["assigned_to"]).strip() if act.get("assigned_to") else None,
                        deadline_raw_text=str(act["deadline_raw_text"]).strip() if act.get("deadline_raw_text") else None,
                        deadline_date=str(act["deadline_date"]).strip() if act.get("deadline_date") else None,
                        timestamp_seconds=(
                            float(act["timestamp_seconds"])
                            if act.get("timestamp_seconds") is not None
                            else None
                        ),
                    )
                )

        # Parse decisions
        decisions = []
        for dec in data.get("decisions", []):
            if isinstance(dec, dict) and dec.get("decision_text"):
                decisions.append(
                    DecisionDTO(
                        decision_text=str(dec["decision_text"]).strip(),
                        decided_by=str(dec["decided_by"]).strip() if dec.get("decided_by") else None,
                        timestamp_seconds=(
                            float(dec["timestamp_seconds"])
                            if dec.get("timestamp_seconds") is not None
                            else None
                        ),
                    )
                )

        # Parse unresolved issues
        unresolved_issues = []
        for iss in data.get("unresolved_issues", []):
            if isinstance(iss, dict) and iss.get("issue_text"):
                unresolved_issues.append(
                    UnresolvedIssueDTO(
                        issue_text=str(iss["issue_text"]).strip(),
                        timestamp_seconds=(
                            float(iss["timestamp_seconds"])
                            if iss.get("timestamp_seconds") is not None
                            else None
                        ),
                    )
                )

        # Parse follow-up items
        follow_ups = []
        for fol in data.get("follow_up_items", []):
            if isinstance(fol, dict) and fol.get("description"):
                follow_ups.append(
                    FollowUpDTO(
                        description=str(fol["description"]).strip(),
                        timestamp_seconds=(
                            float(fol["timestamp_seconds"])
                            if fol.get("timestamp_seconds") is not None
                            else None
                        ),
                    )
                )

        # Parse deadlines
        deadlines = []
        for dl in data.get("deadlines", []):
            if isinstance(dl, dict) and (dl.get("description") or dl.get("raw_text")):
                deadlines.append(
                    DeadlineDTO(
                        description=str(dl.get("description", dl.get("raw_text", ""))).strip(),
                        raw_text=str(dl.get("raw_text", dl.get("description", ""))).strip(),
                        resolved_date=str(dl["resolved_date"]).strip() if dl.get("resolved_date") else None,
                        timestamp_seconds=(
                            float(dl["timestamp_seconds"])
                            if dl.get("timestamp_seconds") is not None
                            else None
                        ),
                    )
                )

        return MeetingIntelligenceResult(
            title=title,
            summary_short=summary_short,
            summary_detailed=summary_detailed,
            sentiment=raw_sentiment,
            sentiment_score=round(sentiment_score, 3),
            key_points=key_points,
            action_items=action_items,
            decisions=decisions,
            unresolved_issues=unresolved_issues,
            follow_up_items=follow_ups,
            deadlines=deadlines,
            raw_response=data,
        )

    async def extract_meeting_intelligence(
        self,
        formatted_transcript: str,
        timeout_seconds: float = 120.0,
    ) -> MeetingIntelligenceResult:
        """
        Sends transcript to Gemini API and parses extracted meeting intelligence.
        """
        models_to_try = [
            "gemini-2.5-flash",
            "gemini-3.5-flash",
            "gemini-flash-latest",
        ]
        # Remove duplicates while preserving order
        seen = set()
        models_to_try = [m for m in models_to_try if not (m in seen or seen.add(m))]

        prompt_text = self._build_extraction_prompt(formatted_transcript)
        payload = {
            "contents": [
                {
                    "parts": [
                        {"text": prompt_text}
                    ]
                }
            ],
            "generationConfig": {
                "temperature": 0.2,
                "responseMimeType": "application/json",
            },
        }

        last_error = None
        for current_model in models_to_try:
            url = f"{GEMINI_API_BASE}/{current_model}:generateContent?key={self.api_key}"
            logger.info("Calling Gemini (%s) for meeting intelligence extraction...", current_model)

            max_retries = 2
            backoff = 2.0

            for attempt in range(max_retries):
                try:
                    async with httpx.AsyncClient(timeout=120.0) as client:
                        response = await client.post(
                            url,
                            json=payload,
                            headers={"Content-Type": "application/json"},
                        )
                except (httpx.TimeoutException, httpx.NetworkError) as net_err:
                    last_error = f"Network/Timeout error on {current_model}: {net_err}"
                    logger.warning(
                        "Gemini request timed out or network error on %s (attempt %d/%d): %s",
                        current_model,
                        attempt + 1,
                        max_retries,
                        net_err,
                    )
                    import asyncio
                    await asyncio.sleep(backoff)
                    backoff *= 1.5
                    continue

                if response.status_code == 200:
                    res_data = response.json()
                    candidates = res_data.get("candidates", [])
                    if candidates:
                        parts = candidates[0].get("content", {}).get("parts", [])
                        if parts:
                            generated_text = parts[0].get("text", "")
                            return self.parse_gemini_json(generated_text)

                if response.status_code in [429, 503]:
                    last_error = f"Gemini API returned status {response.status_code} on {current_model}: {response.text}"
                    logger.warning(
                        "Gemini API returned %d on %s (attempt %d/%d). Retrying in %.1fs...",
                        response.status_code,
                        current_model,
                        attempt + 1,
                        max_retries,
                        backoff,
                    )
                    import asyncio
                    await asyncio.sleep(backoff)
                    backoff *= 1.5
                    continue
                elif response.status_code == 404:
                    last_error = f"Model {current_model} not found (404)."
                    break
                else:
                    err_msg = response.text
                    logger.error("Gemini API error (%s, status=%d): %s", current_model, response.status_code, err_msg)
                    last_error = f"Gemini API returned status {response.status_code}: {err_msg}"
                    break

        raise RuntimeError(last_error or "All Gemini models failed.")


gemini_service = GeminiService()
