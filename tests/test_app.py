from pathlib import Path

from rich.console import Console

from girlfriend_generator.app import (
    AppConfig,
    PendingDelivery,
    _finish_job,
    _handle_command,
    _handle_key,
    _render_screen,
    _render_trace,
    _show_ending,
    _sync_provider_trace,
    run_chat_app,
)
from girlfriend_generator.engine import ConversationSession
from girlfriend_generator.models import ProviderReply, RuntimeTrace
from girlfriend_generator.personas import load_persona
from girlfriend_generator.voice import DisabledVoiceInput, VoiceInputAdapter


def _load_test_persona():
    return load_persona(Path("personas/wonyoung-idol.json"))


def _render_to_text(renderable) -> str:
    console = Console(record=True, width=120)
    console.print(renderable)
    return console.export_text()


def test_listen_command_requires_configured_voice_input(tmp_path: Path) -> None:
    persona = _load_test_persona()
    session = ConversationSession(persona=persona)
    session.bootstrap()

    outcome = _handle_command(
        text="/listen",
        session=session,
        provider=object(),
        pending_job=None,
        pending_delivery=None,
        voice_input=DisabledVoiceInput(),
        voice_output_available=False,
        voice_output_enabled=False,
        show_trace=True,
        session_dir=tmp_path,
    )

    assert outcome["pending_job"] is None
    assert outcome["status_line"] == "Voice input unavailable."
    assert session.messages[-1].role == "system"
    assert "Voice input is disabled" in session.messages[-1].text


def test_listen_command_starts_background_job_when_voice_input_is_configured(
    tmp_path: Path,
) -> None:
    class FakeVoiceInput(VoiceInputAdapter):
        def __init__(self) -> None:
            super().__init__(name="external-command")

        def listen(self) -> str:
            return "지금 뭐 해?"

    persona = _load_test_persona()
    session = ConversationSession(persona=persona)
    session.bootstrap()

    outcome = _handle_command(
        text="/listen",
        session=session,
        provider=object(),
        pending_job=None,
        pending_delivery=None,
        voice_input=FakeVoiceInput(),
        voice_output_available=False,
        voice_output_enabled=False,
        show_trace=True,
        session_dir=tmp_path,
    )

    assert outcome["pending_job"] is not None
    assert outcome["pending_job"].kind == "listen"
    assert outcome["status_line"] == "Listening via external transcription command..."


def test_finish_job_turns_voice_transcript_into_reply_job() -> None:
    class FakeProvider:
        def generate_reply(self, persona, history, user_text, affection_score):
            return ProviderReply(
                text=f"reply to: {user_text}",
                typing_seconds=0.2,
                trace_note="turbo-heuristic: zero-network local reply",
            )

    class PreviousJob:
        kind = "listen"

    persona = _load_test_persona()
    session = ConversationSession(persona=persona)
    session.bootstrap()

    next_job, next_delivery, status = _finish_job(
        session=session,
        persona=persona,
        provider=FakeProvider(),
        result=(True, "오늘은 네 목소리 톤이 궁금했어."),
        previous_job=PreviousJob(),
        previous_delivery=None,
        previous_status="Listening via external transcription command...",
    )

    assert session.messages[-1].role == "user"
    assert session.messages[-1].text == "오늘은 네 목소리 톤이 궁금했어."
    assert next_job is not None
    assert next_job.kind == "reply"
    assert next_delivery is None
    assert status == "voice transcript captured"


def test_export_command_writes_local_transcript_files(tmp_path: Path) -> None:
    persona = _load_test_persona()
    session = ConversationSession(persona=persona)
    session.bootstrap()
    session.add_user_message("오늘은 네가 먼저 말 걸어줘서 좋네.")

    outcome = _handle_command(
        text="/export",
        session=session,
        provider=object(),
        pending_job=None,
        pending_delivery=None,
        voice_input=DisabledVoiceInput(),
        voice_output_available=False,
        voice_output_enabled=False,
        show_trace=True,
        session_dir=tmp_path,
    )

    exported_files = sorted(path.name for path in tmp_path.iterdir())

    assert outcome["status_line"] == "Session exported."
    assert len(exported_files) == 2
    assert any(name.endswith(".json") for name in exported_files)
    assert any(name.endswith(".md") for name in exported_files)
    assert str(tmp_path) in session.messages[-1].text


def test_render_screen_shows_typing_and_trace_visibility() -> None:
    persona = _load_test_persona()
    session = ConversationSession(persona=persona)
    session.bootstrap()
    trace = RuntimeTrace(
        persona_path=Path("personas/wonyoung-idol.json"),
        provider_name="heuristic",
        provider_model=None,
        performance_mode="turbo",
        voice_output_name="off",
        voice_input_name="off",
        pending_reply_kind="nudge",
        pending_nudge_in=12,
        pending_initiative_in=420,
    )

    renderable = _render_screen(
        console=Console(width=120),
        persona=persona,
        session=session,
        draft="지금 뭐 해?",
        trace=trace,
        show_trace=True,
        status_line="assistant is thinking...",
        assistant_typing=True,
        user_typing=True,
    )
    rendered = _render_to_text(renderable)

    assert "trace" in rendered
    assert "heuristic" in rendered
    assert "typing" in rendered


def test_render_trace_shows_idle_timers() -> None:
    persona = _load_test_persona()
    session = ConversationSession(persona=persona)
    session.bootstrap()
    trace = RuntimeTrace(
        persona_path=Path("personas/wonyoung-idol.json"),
        provider_name="heuristic",
        provider_model=None,
        performance_mode="turbo",
        voice_output_name="off",
        voice_input_name="external-command",
        pending_reply_kind="nudge",
        pending_nudge_in=12,
        pending_initiative_in=420,
    )

    rendered = _render_to_text(_render_trace(trace, persona, session))

    assert "Init" in rendered
    assert "420" in rendered
    assert "external-command" in rendered


def test_render_trace_shows_coach_strength_and_weakness() -> None:
    persona = _load_test_persona()
    session = ConversationSession(persona=persona)
    session.bootstrap()
    session.last_coach_strength = "상대의 말을 기억해서 꺼내는 편"
    session.last_coach_weakness = "질문이 너무 평면적임"
    session.last_coach_feedback = "조금 더 구체적으로 물어보면 훨씬 좋다"
    trace = RuntimeTrace(
        persona_path=Path("personas/wonyoung-idol.json"),
        provider_name="heuristic",
        provider_model=None,
        performance_mode="turbo",
        voice_output_name="off",
        voice_input_name="off",
    )

    rendered = _render_to_text(_render_trace(trace, persona, session))

    assert "Strength" in rendered
    assert "Weakness" in rendered
    assert "질문이 너무 평면적임" in rendered


def test_render_trace_shows_charm_feedback() -> None:
    persona = _load_test_persona()
    session = ConversationSession(persona=persona)
    session.bootstrap()
    session.last_coach_charm_point = "장난기 있는 리듬감"
    session.last_coach_charm_type = "playful"
    session.last_coach_charm_feedback = "가볍게 툭 던지는 톤이 매력으로 작동함"
    trace = RuntimeTrace(
        persona_path=Path("personas/wonyoung-idol.json"),
        provider_name="heuristic",
        provider_model=None,
        performance_mode="turbo",
        voice_output_name="off",
        voice_input_name="off",
    )

    rendered = _render_to_text(_render_trace(trace, persona, session))

    assert "Charm" in rendered
    assert "playful" in rendered
    assert "장난기 있는 리듬감" in rendered


def test_sync_provider_trace_exposes_remote_metadata() -> None:
    trace = RuntimeTrace(
        persona_path=Path("personas/wonyoung-idol.json"),
        provider_name="remote",
        provider_model=None,
        performance_mode="turbo",
        voice_output_name="off",
        voice_input_name="off",
    )

    class DummyProvider:
        last_trace = {
            "persona_ref": "persona_1",
            "persona_version": 3,
            "emotion": "playful",
            "initiative_reason": "scheduler",
            "memory_hits": ["late_reply_pattern"],
        }

    _sync_provider_trace(DummyProvider(), trace)

    assert trace.remote_persona_ref == "persona_1"
    assert trace.remote_persona_version == 3
    assert trace.remote_emotion == "playful"
    assert trace.remote_initiative_reason == "scheduler"
    assert trace.remote_memory_hits == ["late_reply_pattern"]


def test_trace_command_toggles_panel_visibility(tmp_path: Path) -> None:
    persona = _load_test_persona()
    session = ConversationSession(persona=persona)
    session.bootstrap()

    outcome = _handle_command(
        text="/trace",
        session=session,
        provider=object(),
        pending_job=None,
        pending_delivery=None,
        voice_input=DisabledVoiceInput(),
        voice_output_available=False,
        voice_output_enabled=False,
        show_trace=True,
        session_dir=tmp_path,
    )

    assert outcome["show_trace"] is False
    assert outcome["status_line"] == "Trace panel toggled."


def test_affection_command_posts_battle_power_report(tmp_path: Path) -> None:
    persona = _load_test_persona()
    session = ConversationSession(persona=persona)
    session.bootstrap()
    session.last_coach_charm_point = "자연스러운 장난기"
    session.last_coach_charm_type = "playful"
    session.last_coach_charm_feedback = "가볍게 웃기면서도 부담을 안 준다"
    session.add_user_message("오늘 너 생각나서 웃겼어 😊")

    outcome = _handle_command(
        text="/affection",
        session=session,
        provider=object(),
        pending_job=None,
        pending_delivery=None,
        voice_input=DisabledVoiceInput(),
        voice_output_available=False,
        voice_output_enabled=False,
        show_trace=True,
        session_dir=tmp_path,
    )

    posted = session.messages[-1].text
    assert "전투력 측정" in posted
    assert "Init" in posted
    assert "Emp" in posted
    assert "Charm Point" in posted
    assert "자연스러운 장난기" in posted
    assert outcome["status_line"] == "Battle power posted."


def test_voice_commands_toggle_when_backend_is_available(tmp_path: Path) -> None:
    persona = _load_test_persona()
    session = ConversationSession(persona=persona)
    session.bootstrap()

    enabled = _handle_command(
        text="/voice on",
        session=session,
        provider=object(),
        pending_job=None,
        pending_delivery=None,
        voice_input=DisabledVoiceInput(),
        voice_output_available=True,
        voice_output_enabled=False,
        show_trace=True,
        session_dir=tmp_path,
    )
    disabled = _handle_command(
        text="/voice off",
        session=session,
        provider=object(),
        pending_job=None,
        pending_delivery=None,
        voice_input=DisabledVoiceInput(),
        voice_output_available=True,
        voice_output_enabled=True,
        show_trace=True,
        session_dir=tmp_path,
    )

    assert enabled["voice_output_enabled"] is True
    assert enabled["status_line"] == "Voice output enabled."
    assert disabled["voice_output_enabled"] is False
    assert disabled["status_line"] == "Voice output disabled."


def test_handle_key_allows_user_send_while_assistant_delivery_is_pending(
    tmp_path: Path,
) -> None:
    """User can now send follow-up messages while assistant is busy.
    The in-flight delivery is abandoned so the new message can be processed."""
    persona = _load_test_persona()
    session = ConversationSession(persona=persona)
    session.bootstrap()

    class _StubProvider:
        def generate_reply(self, *args, **kwargs):
            from girlfriend_generator.models import ProviderReply
            return ProviderReply(text="ok", typing_seconds=0.1, trace_note="")

    outcome = _handle_key(
        key="\n",
        draft="지금 바로 답장해도 돼?",
        session=session,
        persona=persona,
        provider=_StubProvider(),
        pending_job=None,
        pending_delivery=PendingDelivery(
            kind="reply",
            text="곧 보낼 답장",
            due_at=9999999999.0,
            trace_note="typing",
        ),
        voice_input=DisabledVoiceInput(),
        voice_output_available=False,
        voice_output_enabled=False,
        show_trace=True,
        session_dir=tmp_path,
    )

    # Draft should be cleared (message was accepted)
    assert outcome["draft"] == ""
    # The pending delivery should have been abandoned
    assert outcome.get("sent") is True


def test_listen_command_blocks_while_assistant_delivery_is_pending(
    tmp_path: Path,
) -> None:
    persona = _load_test_persona()
    session = ConversationSession(persona=persona)
    session.bootstrap()

    outcome = _handle_command(
        text="/listen",
        session=session,
        provider=object(),
        pending_job=None,
        pending_delivery=PendingDelivery(
            kind="nudge",
            text="...",
            due_at=9999999999.0,
            trace_note="idle-nudge",
        ),
        voice_input=DisabledVoiceInput(),
        voice_output_available=False,
        voice_output_enabled=False,
        show_trace=True,
        session_dir=tmp_path,
    )

    assert outcome["pending_job"] is None
    assert outcome["status_line"] == "Assistant is still busy."
    assert session.messages[-1].role == "system"
    assert "assistant turn" in session.messages[-1].text


def test_run_chat_app_returns_clean_error_without_tty(
    monkeypatch,
    capsys,
    tmp_path: Path,
) -> None:
    export_calls = []

    def fake_export_session(*_args, **_kwargs):
        export_calls.append("called")
        raise AssertionError("export_session should not run when chat never starts")

    monkeypatch.setattr("girlfriend_generator.app.export_session", fake_export_session)
    monkeypatch.setattr("girlfriend_generator.app.sys.stdin.isatty", lambda: False)
    monkeypatch.setattr("girlfriend_generator.app.sys.stdout.isatty", lambda: False)

    exit_code = run_chat_app(
        AppConfig(
            persona_path=Path("personas/wonyoung-idol.json"),
            session_dir=tmp_path,
        )
    )

    output = capsys.readouterr().out
    assert exit_code == 1
    assert "requires a TTY" in output
    assert export_calls == []


def test_run_chat_app_returns_back_signal_after_ending_screen(
    monkeypatch,
    tmp_path: Path,
) -> None:
    persona = _load_test_persona()
    ending_calls: list[str] = []

    class FakeSession:
        def __init__(self, persona):
            self.persona = persona
            self.messages = []
            self.affection_score = 0
            self.awaiting_user_reply = False
            self.ended = False
            self.mood = type("Mood", (), {"current": "neutral"})()
            self.proactive_due_at = None

        def bootstrap(self) -> None:
            return None

        def seconds_until_nudge(self, _now=None):
            return None

        def seconds_until_initiative(self, _now=None):
            return None

        def nudge_due(self, _now=None) -> bool:
            return False

        def initiative_due(self, _now=None) -> bool:
            return False

    class DummyKeyboard:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def poll(self, _timeout):
            return None

    class DummyLive:
        def __init__(self, *_args, **_kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def update(self, *_args, **_kwargs):
            return None

        def stop(self):
            return None

    class DummyVoice:
        name = "off"

        def speak(self, _text):
            return None

    class DummyMusic:
        def update_mood(self, _mood):
            return None

        def stop(self):
            return None

    monkeypatch.setattr("girlfriend_generator.app._supports_interactive_chat", lambda: True)
    monkeypatch.setattr("girlfriend_generator.app.ConversationSession", FakeSession)
    monkeypatch.setattr("girlfriend_generator.app.build_provider", lambda _config: object())
    monkeypatch.setattr("girlfriend_generator.app.build_voice_output", lambda _enabled: DummyVoice())
    monkeypatch.setattr("girlfriend_generator.app.build_voice_input", lambda _cmd: DummyVoice())
    monkeypatch.setattr("girlfriend_generator.app.build_music_player", lambda: DummyMusic())
    monkeypatch.setattr("girlfriend_generator.app.load_scenes", lambda: [])
    monkeypatch.setattr("girlfriend_generator.app.RawKeyboard", DummyKeyboard)
    monkeypatch.setattr("girlfriend_generator.app.Live", DummyLive)
    monkeypatch.setattr("girlfriend_generator.app._render_screen", lambda **_kwargs: "screen")
    monkeypatch.setattr(
        "girlfriend_generator.app._show_ending",
        lambda *_args, **_kwargs: ending_calls.append("shown"),
    )

    exit_code = run_chat_app(
        AppConfig(
            persona_path=tmp_path / "unused.json",
            persona_override=persona,
            session_dir=tmp_path,
            export_on_exit=False,
        )
    )

    assert exit_code == 2
    assert ending_calls == ["shown"]


def test_show_ending_uses_configured_language(monkeypatch) -> None:
    persona = _load_test_persona()
    session = ConversationSession(persona=persona)
    session.bootstrap()
    session.affection_score = 0
    captured = {}

    class _DummyLive:
        def stop(self):
            return None

    class _DummyProvider:
        def generate_reply(self, *args, **kwargs):
            captured["kwargs"] = kwargs
            return ProviderReply(
                text='{"persona_final_words":"bye","ending_narrative":"end","report_title":"END","highlights":[],"what_went_wrong":"x","rating":"F"}',
                typing_seconds=0.1,
                trace_note="",
            )

    monkeypatch.setattr("girlfriend_generator.i18n.get_language", lambda: "ja")
    monkeypatch.setattr("girlfriend_generator.wide_input.wide_input", lambda _prompt="": "")

    _show_ending(_DummyLive(), Console(record=True, width=120), persona, session, "game_over", _DummyProvider())

    assert captured["kwargs"]["language"] == "ja"


def test_show_ending_renders_strength_and_weakness(monkeypatch) -> None:
    persona = _load_test_persona()
    session = ConversationSession(persona=persona)
    session.bootstrap()

    class _DummyLive:
        def stop(self):
            return None

    class _DummyProvider:
        def generate_reply(self, *args, **kwargs):
            return ProviderReply(
                text='{"persona_final_words":"bye","ending_narrative":"end","report_title":"END","highlights":[],"user_strength":"기억을 살린 질문","user_weakness":"너무 짧은 단답","what_went_wrong":"톤이 아쉬웠다","rating":"B"}',
                typing_seconds=0.1,
                trace_note="",
            )

    monkeypatch.setattr("girlfriend_generator.i18n.get_language", lambda: "ko")
    monkeypatch.setattr("girlfriend_generator.wide_input.wide_input", lambda _prompt="": "")
    console = Console(record=True, width=120)

    _show_ending(_DummyLive(), console, persona, session, "success", _DummyProvider())

    rendered = console.export_text()
    assert "Strength" in rendered
    assert "Weakness" in rendered
    assert "기억을 살린 질문" in rendered
    assert "너무 짧은 단답" in rendered


def test_show_ending_renders_charm_fields(monkeypatch) -> None:
    persona = _load_test_persona()
    session = ConversationSession(persona=persona)
    session.bootstrap()

    class _DummyLive:
        def stop(self):
            return None

    class _DummyProvider:
        def generate_reply(self, *args, **kwargs):
            return ProviderReply(
                text='{"persona_final_words":"bye","ending_narrative":"end","report_title":"END","highlights":[],"user_strength":"기억을 살린 질문","user_weakness":"너무 짧은 단답","user_charm_point":"자연스러운 장난기","user_charm_type":"playful","user_charm_feedback":"가볍고 부담 없는 농담이 호감을 만든다","what_went_wrong":"톤이 아쉬웠다","rating":"B"}',
                typing_seconds=0.1,
                trace_note="",
            )

    monkeypatch.setattr("girlfriend_generator.i18n.get_language", lambda: "ko")
    monkeypatch.setattr("girlfriend_generator.wide_input.wide_input", lambda _prompt="": "")
    console = Console(record=True, width=120)

    _show_ending(_DummyLive(), console, persona, session, "success", _DummyProvider())

    rendered = console.export_text()
    assert "Charm Point" in rendered
    assert "Charm Type" in rendered
    assert "자연스러운 장난기" in rendered
    assert "playful" in rendered
