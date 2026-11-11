"""Synthesise the extra narration lines and merge them into narration.json.

  ~/.hermes/models/kokoro/.venv/bin/python video/add_audio.py
"""
from __future__ import annotations

import json
from pathlib import Path

import soundfile as sf
from kokoro_onnx import Kokoro

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "audio"
MODELS = Path.home() / ".hermes/models/kokoro"
VOICE = "am_michael"
SPEED = 0.95

TIMELINE = [
    "s1_problem",
    "s2_solution",
    "s3_clean",
    "s4_doctored",
    "s4b_receipts",
    "s5_injection",
    "s6_letter",
    "s6b_next",
    "s7_close",
]

NEW = [
    (
        "s4b_receipts",
        "Every run leaves a receipt. Which model read the page, which model checked it, "
        "the request id, and the cost the gateway actually billed. "
        "These four documents cost three tenths of a cent in total. Measured, not estimated.",
    ),
    (
        "s6b_next",
        "Next: issuer coverage beyond one water board, a camera flow on a phone, "
        "and the two app side lookups moved onto the gateway properly. "
        "The code is public, and both upstream issues are already filed.",
    ),
    (
        "s7_close",
        "Fine Print. Two open weight models, four checks, one honest answer. Built by Harish Kotra.",
    ),
]


def main() -> None:
    kokoro = Kokoro(str(MODELS / "kokoro-v1.0.onnx"), str(MODELS / "voices-v1.0.bin"))
    manifest = {m["name"]: m for m in json.loads((ROOT / "narration.json").read_text())}
    for name, text in NEW:
        samples, rate = kokoro.create(text, voice=VOICE, speed=SPEED, lang="en-us")
        path = OUT / f"{name}.wav"
        sf.write(path, samples, rate)
        dur = round(len(samples) / rate, 3)
        manifest[name] = {"name": name, "text": text, "wav": str(path), "seconds": dur}
        print(f"{name:14s} {dur:6.2f}s")
    ordered = [manifest[n] for n in TIMELINE]
    (ROOT / "narration.json").write_text(json.dumps(ordered, indent=1))
    print("total", round(sum(m["seconds"] for m in ordered), 2), "s")


if __name__ == "__main__":
    main()
