#!/usr/bin/env python3
"""Low-latency, interactive Qwen3-TTS voice-clone streaming."""

from __future__ import annotations

import argparse
import socket
import subprocess
import sys
import time
import wave
from pathlib import Path

import numpy as np
import torch
from qwen_tts import Qwen3TTSModel

DEFAULT_TRANSCRIPT = (
    "And that's influenced by pop culture. I'll give an example. When the movie "
    "Ghost came out, polls showed that more people believed in ghosts after that "
    "movie than before the movie."
)


class AudioSink:
    """Persistent ffplay sink plus optional per-utterance WAV recording."""

    def __init__(self, sample_rate: int = 24_000, play: bool = True) -> None:
        self.sample_rate = sample_rate
        self.play = play
        self.process: subprocess.Popen[bytes] | None = None
        if play:
            self.process = subprocess.Popen(
                [
                    "ffplay", "-nodisp", "-autoexit", "-loglevel", "error",
                    "-fflags", "nobuffer", "-flags", "low_delay",
                    "-f", "f32le", "-sample_rate", str(sample_rate), "-ch_layout", "mono", "-",
                ],
                stdin=subprocess.PIPE,
            )

    def write(self, chunk: np.ndarray) -> None:
        if self.process and self.process.stdin:
            self.process.stdin.write(np.asarray(chunk, dtype="<f4").tobytes())
            self.process.stdin.flush()

    def close(self) -> None:
        if self.process and self.process.stdin:
            self.process.stdin.close()
        if self.process:
            self.process.wait(timeout=5)


def save_wav(path: Path, chunks: list[np.ndarray], sample_rate: int) -> None:
    audio = np.concatenate(chunks) if chunks else np.empty(0, dtype=np.float32)
    pcm = (np.clip(audio, -1, 1) * 32767).astype("<i2")
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(sample_rate)
        output.writeframes(pcm.tobytes())


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("text", nargs="*", help="Text to speak; omit for interactive stdin")
    parser.add_argument("--reference", default="reference.wav")
    parser.add_argument("--transcript", default=DEFAULT_TRANSCRIPT)
    parser.add_argument("--language", default="English")
    parser.add_argument("--model", default="Qwen/Qwen3-TTS-12Hz-0.6B-Base")
    parser.add_argument("--output", type=Path, help="Save single utterance as WAV")
    parser.add_argument("--socket", type=Path, help="Stay resident and accept text over Unix socket")
    parser.add_argument("--no-play", action="store_true", help="Generate without playback")
    parser.add_argument("--no-compile", action="store_true", help="Faster startup, slower generation")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if not torch.cuda.is_available():
        raise SystemExit("CUDA unavailable. Install CUDA PyTorch and verify NVIDIA driver.")

    torch.set_float32_matmul_precision("high")
    torch.backends.cuda.matmul.allow_tf32 = True
    print(f"GPU: {torch.cuda.get_device_name(0)}", flush=True)
    print(f"Loading {args.model}…", flush=True)
    started = time.perf_counter()
    model = Qwen3TTSModel.from_pretrained(
        args.model,
        device_map="cuda:0",
        dtype=torch.bfloat16,
        attn_implementation="sdpa",
        low_cpu_mem_usage=True,
    )
    print(f"Model ready: {time.perf_counter() - started:.1f}s", flush=True)

    print("Creating clone prompt…", flush=True)
    prompt = model.create_voice_clone_prompt(
        ref_audio=args.reference,
        ref_text=args.transcript,
    )

    if not args.no_compile:
        print("Enabling CUDA streaming optimizations…", flush=True)
        model.enable_streaming_optimizations(
            decode_window_frames=80,
            use_compile=True,
            use_cuda_graphs=False,
            compile_mode="reduce-overhead",
            compile_codebook_predictor=False,
        )

    sink = AudioSink(play=not args.no_play)

    def speak(text: str, output: Path | None = None) -> None:
        chunks: list[np.ndarray] = []
        started = time.perf_counter()
        first = True
        sample_rate = 24_000
        for chunk, sample_rate in model.stream_generate_voice_clone(
            text=text,
            language=args.language,
            voice_clone_prompt=prompt,
            emit_every_frames=12,
            decode_window_frames=80,
            overlap_samples=512,
            first_chunk_emit_every=5,
            first_chunk_decode_window=48,
            first_chunk_frames=48,
            repetition_penalty=1.0,
        ):
            if first:
                print(f"First audio: {(time.perf_counter() - started) * 1000:.0f}ms", flush=True)
                first = False
            sink.write(chunk)
            chunks.append(np.asarray(chunk, dtype=np.float32))
        elapsed = time.perf_counter() - started
        duration = sum(map(len, chunks)) / sample_rate
        print(f"Done: {elapsed:.2f}s | audio {duration:.2f}s | RTF {elapsed / duration:.2f}", flush=True)
        if output:
            save_wav(output, chunks, sample_rate)
            print(f"Saved: {output}", flush=True)

    try:
        one_shot = " ".join(args.text).strip()
        if one_shot:
            speak(one_shot, args.output)
        elif args.socket:
            args.socket.parent.mkdir(parents=True, exist_ok=True)
            args.socket.unlink(missing_ok=True)
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as server:
                server.bind(str(args.socket))
                server.listen()
                print(f"Ready: {args.socket}", flush=True)
                while True:
                    connection, _ = server.accept()
                    with connection:
                        text = connection.recv(1_048_576).decode().strip()
                        if not text:
                            connection.sendall(b"ERROR: empty text\n")
                            continue
                        try:
                            speak(text)
                            connection.sendall(b"OK\n")
                        except Exception as error:
                            connection.sendall(f"ERROR: {error}\n".encode())
        else:
            print("Ready. Enter text; Ctrl-D exits.", flush=True)
            for line in sys.stdin:
                text = line.strip()
                if text:
                    speak(text)
                    print("Ready.", flush=True)
    finally:
        if args.socket:
            args.socket.unlink(missing_ok=True)
        sink.close()


if __name__ == "__main__":
    main()
