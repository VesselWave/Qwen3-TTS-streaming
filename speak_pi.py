"""Pi response-to-speech mode."""

import json
import subprocess
from pathlib import Path
from typing import Iterable

from speak_common import send


def speak_json(lines: Iterable[str], socket_path: Path) -> None:
    """Speak complete clauses from Pi text deltas."""
    pending = ""
    phrase: list[str] = []

    def add_word(word: str) -> None:
        phrase.append(word)
        sentence_end = word.endswith((".", "!", "?"))
        clause_end = word.endswith((";", ":", ","))
        if (
            len(phrase) >= 24
            or (sentence_end and len(phrase) >= 6)
            or (clause_end and len(phrase) >= 12)
        ):
            send(" ".join(phrase), socket_path)
            phrase.clear()

    for line in lines:
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if event.get("type") != "message_update":
            continue
        update = event.get("assistantMessageEvent", {})
        update_type = update.get("type")
        if update_type == "text_delta":
            pending += update.get("delta", "")
            parts = pending.split()
            if pending and not pending[-1].isspace():
                pending = parts.pop() if parts else pending
            else:
                pending = ""
            for word in parts:
                add_word(word)
        elif update_type == "text_end":
            if pending:
                add_word(pending)
                pending = ""
            if phrase:
                send(" ".join(phrase), socket_path)
                phrase.clear()

    if pending:
        add_word(pending)
    if phrase:
        send(" ".join(phrase), socket_path)


def run(prompt: list[str], socket_path: Path, model: str, thinking: str) -> int:
    """Run Pi in streaming JSON mode and speak its answer."""
    command = [
        "pi",
        "-p",
        "--mode",
        "json",
        "--model",
        model,
        "--thinking",
        thinking,
        "--no-session",
        *prompt,
    ]
    with subprocess.Popen(
        command,
        stdout=subprocess.PIPE,
        text=True,
        bufsize=1,
    ) as process:
        assert process.stdout is not None
        speak_json(process.stdout, socket_path)
        return process.wait()
