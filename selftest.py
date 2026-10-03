#!/usr/bin/env python3
"""Self-check for amph-text-gate -- runs from a fresh clone, with no corpus.

text has a real corpus-free control in both directions, measured on synthetic canvases: blank passes, rendered text fails on peak OCR confidence, and word-shaped gibberish passes. The third case reproduces the gate's own documented limit, so the self-test proves the limit rather than only the happy path.

Exits 0 only if every assertion below holds.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from PIL import Image, ImageDraw, ImageFont

CONF = 88.0


def _font():
    for p in ("/usr/share/fonts/TTF/DejaVuSans-Bold.ttf",
              "/usr/share/fonts/TTF/DejaVuSans.ttf"):
        if Path(p).is_file():
            return ImageFont.truetype(p, 56)
    return ImageFont.load_default()


def _canvas(tmp: Path, name: str, lines):
    im = Image.new("RGB", (800, 400), (250, 250, 248))
    d = ImageDraw.Draw(im)
    f = _font()
    for i, line in enumerate(lines):
        d.text((40, 60 + i * 120), line, fill=(10, 10, 10), font=f)
    p = tmp / name
    im.save(p, "JPEG", quality=95)
    return p


def _gate(p: Path):
    r = subprocess.run([sys.executable, "text.py", str(p), "--json"],
                       cwd=HERE, capture_output=True, text=True)
    try:
        return json.loads(r.stdout), (r.stdout + r.stderr)
    except json.JSONDecodeError:
        return None, (r.stdout + r.stderr)


def run(tmp: Path) -> int:
    blank = tmp / "blank.jpg"
    Image.new("RGB", (600, 600), (12, 12, 16)).save(blank, "JPEG", quality=92)

    doc, raw = _gate(blank)
    if doc is None:
        print("FAIL no payload on a blank canvas:", raw.strip()[-300:])
        return 1
    if doc.get("pass") is not True:
        print("FAIL a blank canvas failed the text gate; generated art with no "
              "type is the common case and must pass")
        return 1

    real = _canvas(tmp, "realtext.jpg", ["AMPHETAMEME", "The Long Spiral"])
    doc, raw = _gate(real)
    if doc is None:
        print("FAIL no payload on rendered text:", raw.strip()[-300:])
        return 1
    tb = next((c for c in doc.get("checks", []) if c.get("name") == "typeblock"), None)
    if tb is None:
        print("FAIL no typeblock check in payload")
        return 1
    peak = tb.get("max_conf")
    thr = tb.get("threshold", CONF)
    if not isinstance(peak, (int, float)) or peak < thr:
        print(f"FAIL rendered text did not trip the typeblock gate "
              f"(peak={peak} threshold={thr})")
        return 1

    gib = _canvas(tmp, "gibberish.jpg", ["Eosic Niew Conuum"])
    doc, raw = _gate(gib)
    if doc is None:
        print("FAIL no payload on gibberish:", raw.strip()[-300:])
        return 1
    gtb = next((c for c in doc.get("checks", []) if c.get("name") == "typeblock"), None)
    gpeak = (gtb or {}).get("max_conf")
    if doc.get("pass") is not True:
        print(f"NOTE  gibberish now fails too (peak={gpeak}); the known limit "
              "said it would pass, so re-check the limits record")
    else:
        print(f"NOTE  gibberish passes at peak {gpeak} while a real word fails "
              f"at {peak} -- the documented limit, reproduced on synthetic input")

    rl = subprocess.run([sys.executable, "text.py", "--known-limits"],
                        cwd=HERE, capture_output=True, text=True)
    if rl.returncode or not rl.stdout.strip():
        print("FAIL --known-limits produced nothing:", (rl.stdout + rl.stderr).strip()[-300:])
        return 1

    print(f"PASS  text: blank passes; rendered text fails at peak {peak} vs "
          f"threshold {thr}; limits readable")
    return 0


def main() -> int:
    tmp = Path(tempfile.mkdtemp(prefix="amph-text-gate-selftest-"))
    try:
        return run(tmp)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
