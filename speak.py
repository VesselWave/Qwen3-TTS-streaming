#!/usr/bin/env python3
"""Send text to resident voice-clone process."""

import argparse
import socket
from pathlib import Path

ROOT = Path(__file__).resolve().parent

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("text", nargs="+", help="Text to speak")
parser.add_argument("--socket", type=Path, default=ROOT / "run/clone.sock")
args = parser.parse_args()

with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
    client.connect(str(args.socket))
    client.sendall(" ".join(args.text).encode())
    client.shutdown(socket.SHUT_WR)
    response = client.recv(4096).decode().strip()

print(response)
raise SystemExit(0 if response == "OK" else 1)
