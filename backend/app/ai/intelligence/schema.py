"""
The LLM's structured-output contract.

This Pydantic model is what we FORCE the LLM to return (via OpenAI structured
outputs / JSON schema). Making the shape explicit means:
  * the model can't wander off-format (no fragile free-text parsing),
  * the provider is swappable — any backend that fills this shape works,
  * persistence is a straight field-to-table mapping.

Field names double as instructions to the model, so they're descriptive.
"""

from typing import Literal

from pydantic import BaseModel, Field


class ActionItemData(BaseModel):
    """A concrete task someone must do after the meeting."""

    description: str = Field(description="What needs to be done, imperative and specific")
    assignee_name: str | None = Field(
        default=None, description="Person responsible, as named in the meeting, or null"
    )
    due_date: str | None = Field(
        default=None, description="Deadline as an ISO date (YYYY-MM-DD), or null"
    )
    priority: Literal["low", "medium", "high"] = Field(
        default="medium", description="Urgency inferred from the discussion"
    )


class MeetingIntelligence(BaseModel):
    """Everything extracted from one meeting transcript in a single pass."""

    full_summary: str = Field(
        description=(
            "A DETAILED 300-500 word summary that walks through the meeting "
            "CHRONOLOGICALLY: background/context, the main discussion, key "
            "arguments raised, decisions made, concerns, suggestions, and the "
            "final conclusion. Written so someone who did NOT attend fully "
            "understands what happened. Must be clearly more detailed than the "
            "executive summary and must NOT just repeat it."
        )
    )
    executive_summary: str = Field(
        description=(
            "A CONCISE 70-100 word management summary readable in 30-60 "
            "seconds. Cover ONLY: the meeting objective, the key discussion "
            "points, the final decisions, and the overall outcome. NO detailed "
            "explanations, NO examples, NO supporting discussion."
        )
    )
    discussion_points: list[str] = Field(
        default_factory=list, description="Key topics discussed"
    )
    decisions: list[str] = Field(
        default_factory=list, description="Concrete decisions the group agreed on"
    )
    risks: list[str] = Field(
        default_factory=list, description="Risks, blockers, or concerns raised"
    )
    open_questions: list[str] = Field(
        default_factory=list, description="Unresolved questions left open"
    )
    follow_ups: list[str] = Field(
        default_factory=list, description="Follow-up items for future meetings"
    )
    action_items: list[ActionItemData] = Field(
        default_factory=list, description="Concrete assignable tasks with owners/deadlines"
    )
