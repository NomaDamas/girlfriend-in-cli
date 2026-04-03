import subprocess

from girlfriend_generator import voice


def test_build_voice_output_prefers_local_noop_off_darwin(monkeypatch) -> None:
    monkeypatch.setattr(voice.platform, "system", lambda: "Linux")

    adapter = voice.build_voice_output(enabled=True)

    assert isinstance(adapter, voice.NullVoiceOutput)
    assert adapter.name == "off"


def test_build_voice_output_uses_say_on_darwin(monkeypatch) -> None:
    monkeypatch.setattr(voice.platform, "system", lambda: "Darwin")
    monkeypatch.setattr(voice.shutil, "which", lambda command: "/usr/bin/say")

    adapter = voice.build_voice_output(enabled=True)

    assert isinstance(adapter, voice.SayVoiceOutput)
    assert adapter.name == "macos-say"


def test_build_voice_output_falls_back_when_say_is_unavailable(monkeypatch) -> None:
    monkeypatch.setattr(voice.platform, "system", lambda: "Darwin")
    monkeypatch.setattr(voice.shutil, "which", lambda command: None)

    adapter = voice.build_voice_output(enabled=True)

    assert isinstance(adapter, voice.NullVoiceOutput)
    assert adapter.name == "off"


def test_command_voice_input_returns_trimmed_transcript(monkeypatch) -> None:
    def fake_run(command, check, capture_output, text):
        assert command == ["printf", "  안녕  "]
        assert check is True
        assert capture_output is True
        assert text is True
        return subprocess.CompletedProcess(command, 0, stdout="  안녕  \n")

    monkeypatch.setattr(voice.subprocess, "run", fake_run)

    adapter = voice.CommandVoiceInput("printf '  안녕  '")

    assert adapter.listen() == "안녕"


def test_command_voice_input_rejects_empty_transcript(monkeypatch) -> None:
    def fake_run(command, check, capture_output, text):
        return subprocess.CompletedProcess(command, 0, stdout=" \n")

    monkeypatch.setattr(voice.subprocess, "run", fake_run)
    adapter = voice.CommandVoiceInput("printf ''")

    try:
        adapter.listen()
    except RuntimeError as exc:
        assert "empty transcript" in str(exc)
    else:  # pragma: no cover - defensive
        raise AssertionError("Expected an empty-transcript RuntimeError")
