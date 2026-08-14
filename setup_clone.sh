#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

if ! command -v uv >/dev/null 2>&1; then
  echo "Installing uv locally…"
  curl -LsSf https://astral.sh/uv/install.sh | sh
  export PATH="$HOME/.local/bin:$PATH"
fi

command -v ffplay >/dev/null 2>&1 || {
  echo "Missing ffplay. Install ffmpeg first." >&2
  exit 1
}

uv venv --python 3.11 .venv
uv pip install --python .venv/bin/python \
  torch torchaudio --index-url https://download.pytorch.org/whl/cu128
uv pip install --python .venv/bin/python -e . "transformers==4.57.3"
mkdir -p "$HOME/.local/bin" "$HOME/.pi/agent/extensions"
ln -sfn "$PWD/speak.py" "$HOME/.local/bin/speak"
ln -sfn "$PWD/extensions/speak-stream.ts" "$HOME/.pi/agent/extensions/speak-stream.ts"

echo
echo "Ready. First run downloads model weights:"
echo '  .venv/bin/python stream_clone.py "Hello from your voice clone."'
echo "Interactive mode (best repeated-request latency):"
echo "  .venv/bin/python stream_clone.py"
