#!/usr/bin/env python3
"""Send text or Pi's JSON event stream to the resident voice-clone process."""

import argparse
import json
import socket
import subprocess
import sys
from pathlib import Path
from typing import Iterable

ROOT = Path(__file__).resolve().parent


def send(text: str, socket_path: Path) -> None:
    """Speak one word and wait until playback generation finishes."""
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
        client.connect(str(socket_path))
        client.sendall(text.encode())
        client.shutdown(socket.SHUT_WR)
        response = client.recv(4096).decode().strip()
    if response != "OK":
        raise RuntimeError(response or "empty response from speech server")


def speak_plain(text: str, socket_path: Path) -> None:
    send(text.strip(), socket_path)


def speak_pi_json(lines: Iterable[str], socket_path: Path) -> None:
    """Speak complete clauses from Pi text deltas for smooth, natural audio."""
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


def run_pi(prompt: list[str], socket_path: Path, model: str, thinking: str) -> int:
    """Run Pi in streaming JSON mode and speak its answer phrase by phrase."""
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
        speak_pi_json(process.stdout, socket_path)
        return process.wait()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("text", nargs="*", help="Literal text, or Pi prompt with --pi")
    parser.add_argument("--socket", type=Path, default=ROOT / "run/clone.sock")
    parser.add_argument(
        "--model",
        default="openai-codex/gpt-5.6-luna",
        help="Pi model (default: openai-codex/gpt-5.6-luna)",
    )
    parser.add_argument("--thinking", default="off", help="Pi thinking level")
    parser.add_argument(
        "--pi",
        action="store_true",
        help="Send text to Pi and speak its streamed answer",
    )
    parser.add_argument(
        "--pi-json",
        action="store_true",
        help="Parse piped Pi --mode json events instead of plain text",
    )
    args = parser.parse_args()

    if args.text:
        if args.pi:
            return run_pi(args.text, args.socket, args.model, args.thinking)
        speak_plain(" ".join(args.text), args.socket)
        return 0

    if sys.stdin.isatty():
        parser.error("provide text, use --pi with a prompt, or pipe stdin")

    if args.pi_json:
        speak_pi_json(sys.stdin, args.socket)
    else:
        speak_plain(sys.stdin.read(), args.socket)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, RuntimeError) as error:
        print(f"speak: {error}", file=sys.stderr)
        raise SystemExit(1)
