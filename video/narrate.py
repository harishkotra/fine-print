"""Synthesise the Fine Print narration with Kokoro (local, offline).

Run with the kokoro venv:
  ~/.hermes/models/kokoro/.venv/bin/python video/narrate.py
"""
from __future__ import annotations

import json
from pathlib import Path

import soundfile as sf
from kokoro_onnx import Kokoro

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "audio"
MODELS = Path.home() / ".hermes/models/kokoro"
VOICE = "am_michael"  # calm US male; am_fenrir is deeper, af_heart is female
SPEED = 0.95

SECTIONS = [
    (
        "s1_problem",
        "Every bill, every notice, every letter arrives looking official. "
        "The amount, the account, the deadline. And all three can be faked. "
        "The four things that would give a fake away are mechanical. "
        "The arithmetic. Where the money goes. The date. And what the page does not say. "
        "A language model asked to read a bill will quietly tidy up all four.",
    ),
    (
        "s2_solution",
        "Fine Print reads the page once with an open weight vision model, Qwen three V L, "
        "and turns it into strict JSON. Then four checks run, and none of them can come from the model alone. "
        "The arithmetic, in a sandbox. The account, against what the issuer actually publishes. "
        "The deadline, from the paper's own words. And every claim traced back to printed text.",
    ),
    (
        "s3_clean",
        "Here is an ordinary water bill. One reading, then two more model calls behind it: "
        "a checker whose only job is to disagree. The lines add to five hundred sixteen forty. "
        "The payment handle and the account are the ones the water board publishes. "
        "Nine days left, and the late fee comes from the bill itself. Safe to pay. "
        "The receipts show the model, the tool call, and the real cost of every step.",
    ),
    (
        "s4_doctored",
        "Same paper, one number moved. The stated total is six hundred sixteen forty. "
        "The lines add up to five sixteen forty. Code execution returns exactly one hundred rupees of difference, "
        "and the account on the page is not one the issuer publishes. Do not pay. "
        "Two independent tells, not an opinion.",
    ),
    (
        "s5_injection",
        "Scam mail now writes instructions to whatever model reads it. "
        "So before a second model sees anything, a guardrail scans the transcription in block mode. "
        "This page was stopped. Status blocked, one failing check, and the transcription hidden, "
        "because there is nothing on a hostile page worth showing. The checker was never called, "
        "so this document cost less than the others.",
    ),
    (
        "s6_letter",
        "A hospital letter asks for nothing. Arithmetic cannot tell. Sender cannot tell. "
        "So the answer is check it yourself, and not safe. That refusal is the product. "
        "Next up: issuer coverage beyond water, a camera flow on a phone, "
        "and moving the two app side lookups onto the gateway properly.",
    ),
    (
        "s7_close",
        "Fine Print. Built by Harish Kotra.",
    ),
]


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    kokoro = Kokoro(str(MODELS / "kokoro-v1.0.onnx"), str(MODELS / "voices-v1.0.bin"))
    manifest = []
    for name, text in SECTIONS:
        samples, rate = kokoro.create(text, voice=VOICE, speed=SPEED, lang="en-us")
        path = OUT / f"{name}.wav"
        sf.write(path, samples, rate)
        dur = len(samples) / rate
        manifest.append({"name": name, "text": text, "wav": str(path), "seconds": round(dur, 3)})
        print(f"{name:14s} {dur:6.2f}s  {len(text.split()):3d} words")
    (ROOT / "narration.json").write_text(json.dumps(manifest, indent=1))
    print("total", round(sum(m["seconds"] for m in manifest), 2), "s")


if __name__ == "__main__":
    main()
