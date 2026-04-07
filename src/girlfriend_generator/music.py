from __future__ import annotations

import os
import random
import subprocess
from pathlib import Path
from typing import Literal

MoodType = Literal["neutral", "happy", "playful", "sulky", "excited", "worried", "flirty"]

_AUDIO_EXTENSIONS = {".mp3", ".m4a", ".wav", ".aac", ".ogg", ".flac"}


class MusicPlayer:
    """Mood-based background music player using macOS afplay."""

    def __init__(self, music_dir: Path | None = None) -> None:
        self.music_dir = music_dir
        self.enabled = False
        self.current_mood: MoodType = "neutral"
        self._process: subprocess.Popen[bytes] | None = None
        self._current_file: Path | None = None
        self._available = _afplay_available()

    @property
    def name(self) -> str:
        if not self._available:
            return "unavailable"
        return "on" if self.enabled else "off"

    def toggle(self) -> bool:
        if not self._available:
            return False
        self.enabled = not self.enabled
        if not self.enabled:
            self.stop()
        return self.enabled

    def update_mood(self, mood: MoodType) -> None:
        if not self.enabled or not self._available or not self.music_dir:
            return
        if mood == self.current_mood and self._is_playing():
            return
        self.current_mood = mood
        self._play_for_mood(mood)

    def stop(self) -> None:
        if self._process is not None:
            try:
                self._process.terminate()
                self._process.wait(timeout=2)
            except Exception:
                try:
                    self._process.kill()
                except Exception:
                    pass
            self._process = None
            self._current_file = None

    def _is_playing(self) -> bool:
        if self._process is None:
            return False
        return self._process.poll() is None

    def _play_for_mood(self, mood: MoodType) -> None:
        if not self.music_dir:
            return
        mood_dir = self.music_dir / mood
        if not mood_dir.is_dir():
            # Fall back to neutral
            mood_dir = self.music_dir / "neutral"
            if not mood_dir.is_dir():
                return

        tracks = [
            f for f in mood_dir.iterdir()
            if f.suffix.lower() in _AUDIO_EXTENSIONS
        ]
        if not tracks:
            return

        track = random.choice(tracks)
        if track == self._current_file and self._is_playing():
            return

        self.stop()
        try:
            self._process = subprocess.Popen(
                ["afplay", str(track)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            self._current_file = track
        except FileNotFoundError:
            self._available = False


def _afplay_available() -> bool:
    try:
        result = subprocess.run(
            ["which", "afplay"],
            capture_output=True,
            timeout=3,
        )
        return result.returncode == 0
    except Exception:
        return False


def build_music_player(music_dir: Path | None = None) -> MusicPlayer:
    if music_dir is None:
        # Try to find music/ in project root
        from .paths import project_root
        root = project_root()
        if root is not None:
            candidate = root / "music"
            if candidate.is_dir():
                music_dir = candidate
    return MusicPlayer(music_dir=music_dir)
