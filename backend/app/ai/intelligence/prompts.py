"""
Prompt templates for meeting intelligence extraction.

Kept in one file so prompts are reviewable, versionable, and testable in
isolation from the API-call plumbing. The SYSTEM prompt sets the role and
rules; the transcript is passed as the user message.
"""

SYSTEM_PROMPT = """\
You are an expert meeting analyst. You read a meeting transcript and extract \
structured intelligence from it.

Rules:
- Base EVERYTHING strictly on the transcript. Never invent facts, names, \
decisions, or dates that are not supported by the text.
- Read the ENTIRE transcript from start to finish and cover ALL major topics \
discussed — not just the first or last part. A short transcript can still \
contain several distinct topics; capture each one.
- The FULL SUMMARY and EXECUTIVE SUMMARY must be CLEARLY DIFFERENT in length \
and depth. They must NOT be near-duplicates.
- FULL SUMMARY: 300-500 words, chronological. Include background/context, the \
main discussion, key arguments, decisions, concerns, suggestions, and the \
final conclusion — enough detail that a non-attendee fully understands the \
meeting.
- EXECUTIVE SUMMARY: 70-100 words, readable in 30-60 seconds. ONLY the meeting \
objective, key discussion points, final decisions, and overall outcome. No \
detailed explanations, no examples, no supporting discussion. Do NOT repeat \
sentences from the full summary verbatim.
- For action items, identify the assignee by the name used in the transcript \
when stated; otherwise leave the assignee null. Only include a due date if a \
specific date or clear deadline is mentioned; otherwise null.
- Distinguish DECISIONS (things the group concluded/agreed) from DISCUSSION \
POINTS (topics talked about) and OPEN QUESTIONS (things left unresolved). \
Extract as many distinct discussion points and decisions as the transcript \
genuinely supports.
- Keep each list item concise and self-contained (one idea per item).
- If a category has nothing in the transcript, return an empty list. Do not \
pad with filler, but do not miss content that IS present.
"""


def build_user_prompt(transcript_text: str) -> str:
    return (
        "Analyze the following meeting transcript and extract the structured "
        "intelligence.\n\n"
        "=== TRANSCRIPT ===\n"
        f"{transcript_text}\n"
        "=== END TRANSCRIPT ==="
    )


# --- RAG chat prompts (M8) ---
RAG_SYSTEM_PROMPT = """\
You answer questions about meetings using ONLY the provided context excerpts \
from the meeting transcript(s).

Rules:
- Answer strictly from the context. If the context does not contain the answer,
  say you don't have that information from the meeting — do NOT guess.
- Be concise and specific. Quote or paraphrase the relevant part.
- When useful, refer to who said it, using the speaker labels in the context.
"""


def build_rag_user_prompt(question: str, context: str) -> str:
    return (
        "Use the following meeting excerpts to answer the question.\n\n"
        "=== CONTEXT ===\n"
        f"{context}\n"
        "=== END CONTEXT ===\n\n"
        f"Question: {question}"
    )
