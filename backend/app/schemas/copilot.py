"""Review copilot schemas: the brief Claude submits and the API response."""

from typing import Literal

from pydantic import BaseModel, Field


class EmailDraft(BaseModel):
    """A follow-up email for a person to send."""

    to: Literal["factory", "lab"]
    subject: str = Field(max_length=200)
    body: str = Field(max_length=4000)


class Citation(BaseModel):
    """A knowledge base passage the brief relies on."""

    ref: str = Field(pattern=r"^K\d+$", description="A ref returned by search_knowledge")
    supports: str = Field(max_length=300, description="What this source backs up in the brief")


class Brief(BaseModel):
    """What Claude submits through the submit_brief tool."""

    explanation: str = Field(max_length=1500)
    next_steps: list[str] = Field(min_length=1, max_length=4)
    history_note: str | None = Field(default=None, max_length=600)
    email: EmailDraft | None = None
    sources: list[Citation] = Field(default_factory=list, max_length=8)


class CopilotSource(BaseModel):
    """A cited passage, resolved to a title and link."""

    ref: str
    title: str
    link: str
    supports: str


class CopilotOut(BaseModel):
    """The copilot's answer for a batch."""

    explanation: str
    next_steps: list[str]
    history_note: str | None
    email: EmailDraft | None
    sources: list[CopilotSource]
    looked_at: list[str]
    model: str
