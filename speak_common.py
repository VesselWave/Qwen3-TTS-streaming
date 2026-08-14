"""Shared transport for speech modes."""

import socket
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DEFAULT_SOCKET = ROOT / "run/clone.sock"


def send(text: str, socket_path: Path = DEFAULT_SOCKET) -> None:
    """Send one utterance to the resident voice-clone process."""
    text = text.strip()
    if not text:
        return
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
        client.connect(str(socket_path))
        client.sendall(text.encode())
        client.shutdown(socket.SHUT_WR)
        response = client.recv(4096).decode().strip()
    if response != "OK":
        raise RuntimeError(response or "empty response from speech server")
