"""Tests for queue-based Random Chat relay."""

from girlfriend_generator.random_chat_relay import RandomChatRelay


def test_relay_matches_two_clients_and_exposes_badges() -> None:
    relay = RandomChatRelay()
    alpha = relay.join("alpha", badge="1 cleared · Yu-na")
    queued = alpha.poll()
    bravo = relay.join("bravo", badge="2 cleared · Mina, Reze")

    alpha_match = alpha.poll()
    bravo_match = bravo.poll()

    assert queued is not None and queued.type == "queued"
    assert alpha_match is not None and alpha_match.type == "matched"
    assert alpha_match.handle == "bravo"
    assert "Mina" in alpha_match.badge
    assert bravo_match is not None and bravo_match.type == "matched"
    assert bravo_match.handle == "alpha"


def test_relay_exchanges_messages_typing_and_read_events() -> None:
    relay = RandomChatRelay()
    alpha = relay.join("alpha")
    bravo = relay.join("bravo")
    alpha.poll()
    alpha.poll()
    bravo.poll()

    relay.send_typing(alpha.client_id)
    relay.send_message(alpha.client_id, "hello")
    relay.send_read(bravo.client_id)

    typing = bravo.poll()
    message = bravo.poll()
    read = alpha.poll()

    assert typing is not None and typing.type == "typing"
    assert message is not None and message.type == "message"
    assert message.text == "hello"
    assert read is not None and read.type == "read"


def test_skip_requeues_client_and_notifies_partner() -> None:
    relay = RandomChatRelay()
    alpha = relay.join("alpha")
    bravo = relay.join("bravo")
    alpha.poll()
    alpha.poll()
    bravo.poll()

    relay.skip(alpha.client_id)

    partner_event = bravo.poll()
    alpha_event = alpha.poll()
    assert partner_event is not None and partner_event.type == "leave"
    assert partner_event.reason == "skip"
    assert alpha_event is not None and alpha_event.type == "queued"


def test_report_is_recorded_without_message_transcript() -> None:
    relay = RandomChatRelay()
    alpha = relay.join("alpha")
    bravo = relay.join("bravo")
    alpha.poll()
    alpha.poll()
    bravo.poll()

    relay.report(alpha.client_id, "abuse")

    assert relay.reports == [
        {"reporter": alpha.client_id, "reported": bravo.client_id, "reason": "abuse"}
    ]
    assert "hello" not in str(relay.reports)
