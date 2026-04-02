from __future__ import annotations

import platform
import shlex
import subprocess
from dataclasses import dataclass


class VoiceOutputAdapter:
    name = "off"

    def speak(self, text: str) -> None:
        return None


class NullVoiceOutput(VoiceOutputAdapter):
    name = "off"


class SayVoiceOutput(VoiceOutputAdapter):
    name = "macos-say"

    def speak(self, text: str) -> None:
        subprocess.Popen(
            ["say", text],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )


@dataclass(slots=True)
class VoiceInputAdapter:
    name: str = "off"

    def listen(self) -> str:
        raise RuntimeError("Voice input is not configured.")


class DisabledVoiceInput(VoiceInputAdapter):
    def __init__(self) -> None:
        super().__init__(name="off")

    def listen(self) -> str:
        raise RuntimeError("Voice input is disabled. Provide --voice-input-command.")


class CommandVoiceInput(VoiceInputAdapter):
    def __init__(self, command: str) -> None:
        super().__init__(name="external-command")
        self.command = shlex.split(command)

    def listen(self) -> str:
        result = subprocess.run(
            self.command,
            check=True,
            capture_output=True,
            text=True,
        )
        transcript = result.stdout.strip()
        if not transcript:
            raise RuntimeError("Voice input command returned an empty transcript.")
        return transcript


def build_voice_output(enabled: bool) -> VoiceOutputAdapter:
    if enabled and platform.system() == "Darwin":
        return SayVoiceOutput()
    return NullVoiceOutput()


def build_voice_input(command: str | None) -> VoiceInputAdapter:
    if command:
        return CommandVoiceInput(command)
    return DisabledVoiceInput()
