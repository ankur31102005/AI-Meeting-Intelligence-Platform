"""Email delivery — Provider Pattern (same shape as storage/LLM providers).

Today: ConsoleEmailSender (logs the mail — perfect for dev, and CI).
Later: an SMTP/SES sender implements the same Protocol and a factory picks
it via settings. Zero changes in the services that send mail.
"""

from typing import Protocol

from app.core.logging import get_logger

logger = get_logger(__name__)


class EmailSender(Protocol):
    """Structural interface — any object with this method qualifies (duck
    typing, checked by type checkers), no inheritance required."""

    def send_password_reset(self, *, to_email: str, reset_link: str) -> None: ...


class ConsoleEmailSender:
    """Development sender: writes the mail to the structured log."""

    def send_password_reset(self, *, to_email: str, reset_link: str) -> None:
        logger.info(
            "email_password_reset",
            to=to_email,
            reset_link=reset_link,
            note="ConsoleEmailSender: no real email sent (development mode)",
        )


def get_email_sender() -> EmailSender:
    """Factory — future: return SmtpEmailSender when settings configure it."""
    return ConsoleEmailSender()
