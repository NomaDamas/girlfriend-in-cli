"""Queue-based in-process relay for Random Chat V1.

This is deliberately small and local-testable. It models the hosted relay
contract without storing message transcripts or collecting real identity.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from queue import Empty, Queue
from threading import Lock
from uuid import uuid4


@dataclass(frozen=True)
class RelayEvent:
    type: str
    sender: str = ""
    text: str = ""
    handle: str = ""
    badge: str = ""
    reason: str = ""
    report_reason: str = ""


@dataclass
class RelayClient:
    client_id: str
    handle: str
    badge: str = ""
    partner_id: str = ""
    inbox: Queue[RelayEvent] = field(default_factory=Queue)

    def poll(self, timeout: float = 0.0) -> RelayEvent | None:
        try:
            return self.inbox.get(timeout=timeout) if timeout > 0 else self.inbox.get_nowait()
        except Empty:
            return None


class RandomChatRelay:
    """Ephemeral two-person matchmaking relay."""

    def __init__(self) -> None:
        self._waiting: list[str] = []
        self._clients: dict[str, RelayClient] = {}
        self._reports: list[dict[str, str]] = []
        self._lock = Lock()

    @property
    def reports(self) -> list[dict[str, str]]:
        return list(self._reports)

    def join(self, handle: str, badge: str = "") -> RelayClient:
        client = RelayClient(client_id=uuid4().hex, handle=handle[:40] or "anonymous", badge=badge)
        with self._lock:
            self._clients[client.client_id] = client
            partner = self._pop_waiting_partner(exclude=client.client_id)
            if partner is None:
                self._waiting.append(client.client_id)
                client.inbox.put(RelayEvent(type="queued"))
                return client
            self._pair(client, partner)
            return client

    def send_message(self, client_id: str, text: str) -> None:
        text = (text or "").strip()
        if not text:
            return
        self._send_to_partner(client_id, RelayEvent(type="message", sender=client_id, text=text[:8000]))

    def send_typing(self, client_id: str) -> None:
        self._send_to_partner(client_id, RelayEvent(type="typing", sender=client_id))

    def send_read(self, client_id: str) -> None:
        self._send_to_partner(client_id, RelayEvent(type="read", sender=client_id))

    def leave(self, client_id: str, reason: str = "leave") -> None:
        with self._lock:
            client = self._clients.pop(client_id, None)
            if client is None:
                return
            self._waiting = [item for item in self._waiting if item != client_id]
            partner = self._clients.get(client.partner_id)
            if partner is not None:
                partner.partner_id = ""
                partner.inbox.put(RelayEvent(type="leave", sender=client_id, reason=reason))

    def skip(self, client_id: str) -> None:
        with self._lock:
            client = self._clients.get(client_id)
            if client is None:
                return
            partner = self._clients.get(client.partner_id)
            if partner is not None:
                partner.partner_id = ""
                partner.inbox.put(RelayEvent(type="leave", sender=client_id, reason="skip"))
            client.partner_id = ""
            self._waiting.append(client_id)
            client.inbox.put(RelayEvent(type="queued", reason="skip"))

    def report(self, client_id: str, reason: str) -> None:
        with self._lock:
            client = self._clients.get(client_id)
            if client is None:
                return
            self._reports.append(
                {
                    "reporter": client_id,
                    "reported": client.partner_id,
                    "reason": reason[:500],
                }
            )
            self._send_to_partner_locked(
                client_id,
                RelayEvent(type="reported", sender=client_id, report_reason=reason[:500]),
            )

    def _pair(self, client: RelayClient, partner: RelayClient) -> None:
        client.partner_id = partner.client_id
        partner.partner_id = client.client_id
        client.inbox.put(RelayEvent(type="matched", handle=partner.handle, badge=partner.badge))
        partner.inbox.put(RelayEvent(type="matched", handle=client.handle, badge=client.badge))

    def _pop_waiting_partner(self, exclude: str) -> RelayClient | None:
        while self._waiting:
            partner_id = self._waiting.pop(0)
            if partner_id == exclude:
                continue
            partner = self._clients.get(partner_id)
            if partner is not None and not partner.partner_id:
                return partner
        return None

    def _send_to_partner(self, client_id: str, event: RelayEvent) -> None:
        with self._lock:
            self._send_to_partner_locked(client_id, event)

    def _send_to_partner_locked(self, client_id: str, event: RelayEvent) -> None:
        client = self._clients.get(client_id)
        if client is None or not client.partner_id:
            return
        partner = self._clients.get(client.partner_id)
        if partner is not None:
            partner.inbox.put(event)
