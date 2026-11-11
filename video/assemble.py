"""Assemble the Fine Print demo: cards + screen clips + narration, one MP4.

  .venv/bin/python video/assemble.py
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent
CARDS = ROOT / "cards"
AUDIO = ROOT / "audio"
CLIPS = Path("/tmp/fpvid")
BUILD = Path("/tmp/fpbuild")
OUT = ROOT / "fine-print-demo.mp4"

FPS = 30
SIZE = "1280:720"
TITLE_S = 3.0
TAIL_S = 4.0


def ff(args: list[str]) -> None:
    proc = subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", *args], capture_output=True, text=True)
    if proc.returncode != 0:
        raise SystemExit(f"ffmpeg failed: {' '.join(args[:6])}\n{proc.stderr[-1500:]}")


def silence(path: Path, seconds: float) -> None:
    ff([
        "-f", "lavfi", "-i", f"anullsrc=r=48000:cl=stereo",
        "-t", f"{seconds:.3f}", "-c:a", "aac", "-b:a", "192k", str(path),
    ])


def card_clip(png: Path, seconds: float, out: Path) -> None:
    ff([
        "-loop", "1", "-i", str(png),
        "-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo",
        "-t", f"{seconds:.3f}",
        "-vf", f"scale={SIZE},setsar=1,fps={FPS},format=yuv420p",
        "-c:v", "libx264", "-preset", "medium", "-crf", "19",
        "-c:a", "aac", "-b:a", "192k", "-shortest", str(out),
    ])


def voiced_card(png: Path, wav: Path, seconds: float, out: Path) -> None:
    ff([
        "-loop", "1", "-i", str(png), "-i", str(wav),
        "-filter_complex",
        f"[0:v]scale={SIZE},setsar=1,fps={FPS},trim=duration={seconds:.3f},setpts=PTS-STARTPTS,format=yuv420p[v];"
        f"[1:a]loudnorm=I=-16:TP=-1.5:LRA=11,aresample=48000,aformat=channel_layouts=stereo[a]",
        "-map", "[v]", "-map", "[a]", "-t", f"{seconds:.3f}",
        "-c:v", "libx264", "-preset", "medium", "-crf", "19",
        "-c:a", "aac", "-b:a", "192k", "-ar", "48000", str(out),
    ])


CARD_SOURCES = {"s4b_receipts": CARDS / "receipts.png", "s6b_next": CARDS / "next.png"}


def probe_duration(path: Path) -> float:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=nw=1:nk=1", str(path)],
        capture_output=True, text=True,
    ).stdout.strip()
    try:
        return float(out)
    except ValueError:
        return 0.0


def beat_clip(webm: Path, wav: Path, seconds: float, out: Path) -> None:
    """Keep the tail of the clip (the finished result) and cut it to the line."""
    dur = probe_duration(webm)
    start = max(0.0, dur - seconds)
    ff([
        "-i", str(webm), "-i", str(wav),
        "-filter_complex",
        f"[0:v]scale={SIZE},setsar=1,fps={FPS},trim=start={start:.3f}:duration={seconds:.3f},"
        f"tpad=stop_mode=clone:stop_duration=12,setpts=PTS-STARTPTS,format=yuv420p[v];"
        f"[1:a]loudnorm=I=-16:TP=-1.5:LRA=11,aresample=48000,aformat=channel_layouts=stereo[a]",
        "-map", "[v]", "-map", "[a]",
        "-t", f"{seconds:.3f}",
        "-c:v", "libx264", "-preset", "medium", "-crf", "19",
        "-c:a", "aac", "-b:a", "192k", "-ar", "48000", str(out),
    ])


def main() -> None:
    beats = json.loads((ROOT / "narration.json").read_text())
    BUILD.mkdir(exist_ok=True)
    parts: list[Path] = []

    title = BUILD / "00_title.mp4"
    card_clip(CARDS / "title.png", TITLE_S, title)
    parts.append(title)

    for i, b in enumerate(beats, start=1):
        wav = AUDIO / f"{b['name']}.wav"
        secs = float(b["seconds"]) + 0.35
        out = BUILD / f"{i:02d}_{b['name']}.mp4"
        if b["name"] in CARD_SOURCES:
            voiced_card(CARD_SOURCES[b["name"]], wav, secs, out)
        else:
            webm = CLIPS / f"{b['name']}.webm"
            if not webm.exists():
                raise SystemExit(f"missing clip {webm}")
            beat_clip(webm, wav, secs, out)
        parts.append(out)
        print(f"{b['name']:14s} {secs:5.2f}s -> {out.name}")

    tail = BUILD / "99_end.mp4"
    card_clip(CARDS / "end.png", TAIL_S, tail)
    parts.append(tail)

    listing = BUILD / "concat.txt"
    listing.write_text("".join(f"file '{p}'\n" for p in parts))
    ff(["-f", "concat", "-safe", "0", "-i", str(listing), "-c", "copy", "-movflags", "+faststart", str(OUT)])

    dur = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration,size", "-of", "default=nw=1", str(OUT)],
        capture_output=True, text=True,
    ).stdout.strip()
    print(dur.replace("\n", "  "))
    print(OUT)


if __name__ == "__main__":
    main()
