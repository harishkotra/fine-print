"""Render the title and end cards for the demo video (1280x720)."""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent
W, H = 1280, 720
PAPER = (244, 241, 234)
INK = (23, 23, 26)
STAMP = (193, 53, 23)
RULE = (216, 211, 196)
MUTED = (110, 106, 98)

SERIF = "/System/Library/Fonts/Supplemental/Georgia.ttf"
SERIF_B = "/System/Library/Fonts/Supplemental/Georgia Bold.ttf"
SANS = "/System/Library/Fonts/Supplemental/Arial.ttf"
SANS_B = "/System/Library/Fonts/Supplemental/Arial Bold.ttf"
MONO = "/System/Library/Fonts/Supplemental/Courier New.ttf"


def font(path: str, size: int) -> ImageFont.FreeTypeFont:
    try:
        return ImageFont.truetype(path, size)
    except OSError:
        return ImageFont.truetype(SERIF, size)


def centre(d: ImageDraw.ImageDraw, y: int, text: str, f: ImageFont.FreeTypeFont, fill) -> int:
    w = d.textlength(text, font=f)
    d.text(((W - w) / 2, y), text, font=f, fill=fill)
    return int(y + f.size)


def card(title: str, subtitle: str, footer: str, stamp: str | None, out: Path) -> None:
    img = Image.new("RGB", (W, H), PAPER)
    d = ImageDraw.Draw(img)
    for x in range(70, W - 70, 14):
        d.line([(x, 96), (x + 6, 96)], fill=RULE, width=2)
    y = centre(d, 178, title, font(SERIF_B, 88), INK)
    centre(d, y + 20, subtitle, font(SERIF, 34), MUTED)
    if stamp:
        f = font(SANS_B, 30)
        tw = d.textlength(stamp, font=f)
        bx, by = (W - tw) / 2 - 34, y + 110
        d.rectangle([bx, by, bx + tw + 68, by + 62], outline=STAMP, width=4)
        d.text((bx + 34, by + 14), stamp, font=f, fill=STAMP)
    d.line([(70, H - 118), (W - 70, H - 118)], fill=RULE, width=2)
    centre(d, H - 96, footer, font(SANS, 24), MUTED)
    img.save(out)


def table_card(
    title: str,
    subtitle: str,
    rows: list[tuple[str, str, str]],
    footer: str,
    out: Path,
) -> None:
    img = Image.new("RGB", (W, H), PAPER)
    d = ImageDraw.Draw(img)
    for x in range(70, W - 70, 14):
        d.line([(x, 86), (x + 6, 86)], fill=RULE, width=2)
    y = centre(d, 150, title, font(SERIF_B, 62), INK)
    centre(d, y + 12, subtitle, font(SERIF, 30), MUTED)
    top = y + 96
    d.line([(70, top), (W - 70, top)], fill=INK, width=3)
    f_lab, f_ver, f_num = font(SANS, 27), font(SANS_B, 27), font(MONO, 26)
    row_h = 62
    for i, (label, verdict, cost) in enumerate(rows):
        ry = top + 16 + i * row_h
        d.text((74, ry), label, font=f_lab, fill=INK)
        vw = d.textlength(verdict, font=f_ver)
        d.text((W - 74 - 190 - vw, ry), verdict, font=f_ver, fill=STAMP if verdict != "SAFE TO PAY" else (46, 106, 74))
        cw = d.textlength(cost, font=f_num)
        d.text((W - 74 - cw, ry + 2), cost, font=f_num, fill=MUTED)
        d.line([(70, ry + 46), (W - 70, ry + 46)], fill=RULE, width=1)
    d.line([(70, H - 108), (W - 70, H - 108)], fill=RULE, width=2)
    centre(d, H - 86, footer, font(SANS, 24), MUTED)
    img.save(out)


def bullets_card(title: str, subtitle: str, bullets: list[str], footer: str, out: Path) -> None:
    img = Image.new("RGB", (W, H), PAPER)
    d = ImageDraw.Draw(img)
    for x in range(70, W - 70, 14):
        d.line([(x, 86), (x + 6, 86)], fill=RULE, width=2)
    y = centre(d, 140, title, font(SERIF_B, 64), INK)
    centre(d, y + 12, subtitle, font(SERIF, 30), MUTED)
    f = font(SERIF, 34)
    by = y + 96
    for i, b in enumerate(bullets):
        yy = by + i * 76
        d.text((96, yy), "—", font=f, fill=STAMP)
        d.text((136, yy), b, font=f, fill=INK)
    d.line([(70, H - 108), (W - 70, H - 108)], fill=RULE, width=2)
    centre(d, H - 86, footer, font(SANS, 24), MUTED)
    img.save(out)


def main() -> None:
    out = ROOT / "cards"
    out.mkdir(exist_ok=True)
    card(
        "Fine Print",
        "What this page is actually asking",
        "A bill, a notice, a letter. Four checks a model cannot fake.",
        "DEMO",
        out / "title.png",
    )
    card(
        "Four checks. Four verdicts.",
        "Safe to pay. Do not pay. Check it yourself. Nothing to pay.",
        "Built By Harish Kotra  ·  harishkotra.me  ·  Checkout my other builds  ·  dailybuild.xyz",
        None,
        out / "end.png",
    )
    print("cards written", sorted(p.name for p in out.iterdir()))


if __name__ == "__main__":
    main()
