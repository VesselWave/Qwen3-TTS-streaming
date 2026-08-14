"""Markdown-to-speech mode with safe, bounded utterances."""

import re
from pathlib import Path
from urllib.request import Request, urlopen

from speak_common import send

MAX_CHARS = 280


def load(source: str | None, stdin_text: str) -> str:
    """Load Markdown from a URL, file, or stdin."""
    if source is None or source == "-":
        return stdin_text
    if source.startswith(("https://", "http://")):
        request = Request(source, headers={"User-Agent": "speak/1.0"})
        with urlopen(request, timeout=30) as response:
            return response.read().decode(response.headers.get_content_charset() or "utf-8")
    return Path(source).read_text(encoding="utf-8")


def to_plain(markdown: str) -> str:
    """Remove Markdown syntax and content unsuitable for speech."""
    text = re.sub(r"```.*?```", "\n", markdown, flags=re.DOTALL)
    text = re.sub(r"<!--.*?-->", " ", text, flags=re.DOTALL)
    text = re.sub(r"!\[([^]]*)\]\([^)]*\)", r"\1", text)
    text = re.sub(r"\[([^]]+)\]\([^)]*\)", r"\1", text)
    text = re.sub(r"<https?://[^>]+>", " ", text)
    text = re.sub(r"https?://\S+", " ", text)
    text = re.sub(r"^\s{0,3}(?:#{1,6}|>|[-+*]|\d+[.)])\s*", "", text, flags=re.MULTILINE)
    text = re.sub(r"[`*_~]", "", text)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def chunks(text: str, max_chars: int = MAX_CHARS) -> list[str]:
    """Split prose into short, independently generated utterances."""
    units = re.split(r"(?<=[.!?])\s+|\n+", text)
    result: list[str] = []
    current = ""

    for unit in units:
        unit = unit.strip()
        while len(unit) > max_chars:
            split_at = unit.rfind(" ", 0, max_chars + 1)
            if split_at < 1:
                split_at = max_chars
            head, unit = unit[:split_at].strip(), unit[split_at:].strip()
            if current:
                result.append(current)
                current = ""
            if head:
                result.append(head)
        if not unit:
            continue
        candidate = f"{current} {unit}".strip()
        if current and len(candidate) > max_chars:
            result.append(current)
            current = unit
        else:
            current = candidate

    if current:
        result.append(current)
    return result


def speak(markdown: str, socket_path: Path) -> None:
    for chunk in chunks(to_plain(markdown)):
        send(chunk, socket_path)
