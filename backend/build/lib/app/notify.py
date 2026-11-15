"""Push notifications to the household's phones."""

import logging
from typing import Protocol

log = logging.getLogger(__name__)


class Notifier(Protocol):
    def send(self, tokens: list[str], title: str, body: str, link: str) -> list[str]:
        """Send to every device token. Returns the tokens that are no longer valid."""
        ...


class LogNotifier:
    """Used locally and in tests: records what would have been sent."""

    def __init__(self) -> None:
        self.sent: list[tuple[list[str], str, str]] = []

    def send(self, tokens: list[str], title: str, body: str, link: str) -> list[str]:
        log.info("Push (not sent): %s - %s to %d device(s)", title, body, len(tokens))
        self.sent.append((tokens, title, body))
        return []


class FcmNotifier:
    """Firebase Cloud Messaging web push."""

    def send(self, tokens: list[str], title: str, body: str, link: str) -> list[str]:
        from firebase_admin import messaging

        if not tokens:
            return []
        message = messaging.MulticastMessage(
            tokens=tokens,
            notification=messaging.Notification(title=title, body=body),
            webpush=messaging.WebpushConfig(
                fcm_options=messaging.WebpushFCMOptions(link=link) if link else None
            ),
        )
        response = messaging.send_each_for_multicast(message)
        invalid = []
        for token, result in zip(tokens, response.responses, strict=True):
            if result.success:
                continue
            if isinstance(result.exception, messaging.UnregisteredError):
                invalid.append(token)
            else:
                log.warning("Push to one device failed: %s", result.exception)
        return invalid
