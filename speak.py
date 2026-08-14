#!/usr/bin/env python3
"""Speak plain text, Markdown, or Pi responses through the resident clone service."""

import argparse
import sys
from pathlib import Path

import speak_markdown
import speak_pi
import speak_text
from speak_common import DEFAULT_SOCKET


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("text", nargs="*", help="Text, Pi prompt, or Markdown source")
    parser.add_argument("--socket", type=Path, default=DEFAULT_SOCKET)
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--markdown", action="store_true", help="Speak Markdown from URL, file, or stdin")
    modes.add_argument("--pi", action="store_true", help="Run Pi and speak its streamed answer")
    modes.add_argument("--pi-json", action="store_true", help="Speak piped Pi JSON events")
    parser.add_argument(
        "--model",
        default="openai-codex/gpt-5.6-luna",
        help="Pi model (default: openai-codex/gpt-5.6-luna)",
    )
    parser.add_argument("--thinking", default="off", help="Pi thinking level")
    args = parser.parse_args()

    if args.markdown:
        if len(args.text) > 1:
            parser.error("--markdown accepts one URL/file, or stdin")
        source = args.text[0] if args.text else None
        if source is None and sys.stdin.isatty():
            parser.error("--markdown requires a URL, file, or piped stdin")
        stdin_text = sys.stdin.read() if source is None else ""
        markdown = speak_markdown.load(source, stdin_text)
        speak_markdown.speak(markdown, args.socket)
        return 0

    if args.pi:
        if not args.text:
            parser.error("--pi requires a prompt")
        return speak_pi.run(args.text, args.socket, args.model, args.thinking)

    if args.pi_json:
        if args.text or sys.stdin.isatty():
            parser.error("--pi-json requires piped JSON events")
        speak_pi.speak_json(sys.stdin, args.socket)
        return 0

    if args.text:
        speak_text.speak(" ".join(args.text), args.socket)
        return 0
    if sys.stdin.isatty():
        parser.error("provide text or pipe stdin")
    speak_text.speak(sys.stdin.read(), args.socket)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, RuntimeError) as error:
        print(f"speak: {error}", file=sys.stderr)
        raise SystemExit(1)
