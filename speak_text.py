"""Plain text-to-speech mode."""

from pathlib import Path

from speak_common import send


def speak(text: str, socket_path: Path) -> None:
    send(text, socket_path)
