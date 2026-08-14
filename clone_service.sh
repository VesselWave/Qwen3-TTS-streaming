#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"
mkdir -p run

case "${1:-}" in
  start)
    if [[ -f run/clone.pid ]] && kill -0 "$(<run/clone.pid)" 2>/dev/null; then
      echo "Already running: PID $(<run/clone.pid)"
      exit 0
    fi
    rm -f run/clone.sock
    nohup .venv/bin/python stream_clone.py --socket run/clone.sock \
      >run/clone.log 2>&1 &
    echo $! >run/clone.pid
    for _ in {1..300}; do
      [[ -S run/clone.sock ]] && { echo "Ready: PID $(<run/clone.pid)"; exit 0; }
      kill -0 "$(<run/clone.pid)" 2>/dev/null || {
        echo "Startup failed:" >&2
        tail -50 run/clone.log >&2
        exit 1
      }
      sleep 1
    done
    echo "Startup timed out; inspect run/clone.log" >&2
    exit 1
    ;;
  stop)
    if [[ -f run/clone.pid ]] && kill -0 "$(<run/clone.pid)" 2>/dev/null; then
      kill "$(<run/clone.pid)"
      echo "Stopped"
    else
      echo "Not running"
    fi
    rm -f run/clone.pid run/clone.sock
    ;;
  status)
    if [[ -f run/clone.pid ]] && kill -0 "$(<run/clone.pid)" 2>/dev/null; then
      echo "Running: PID $(<run/clone.pid)"
    else
      echo "Not running"
      exit 1
    fi
    ;;
  *)
    echo "Usage: $0 {start|stop|status}" >&2
    exit 2
    ;;
esac
