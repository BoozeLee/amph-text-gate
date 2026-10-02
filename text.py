"""TEXT gate -- OCR band + corner marks

engine/postgate.py

Extracted VERBATIM from `engine/postgate.py` by `tools/build_modules.py`. Do not edit
this file: the function bodies below are copied byte-for-byte, and
`build_modules.py --check` fails if they drift from the source. To change the
gate, change it upstream and re-run the builder.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).resolve().parent

import re
import subprocess

TEXT_MIN_CHARS = 4          # shorter runs are ornament noise, measured above


TYPEBLOCK_CONF = 88.0        # measured band floor 89.9, ceiling 62.7


CORNER_BAND = 0.12           # outer eighth of the frame


CORNER_MIN_CHARS = 3


CORNER_MAX_WIDTH_FRAC = 0.25  # wider than this is a border rule or a title


CONTROL_FONT = "/usr/share/fonts/liberation/LiberationSans-Bold.ttf"


def ocr_words(path: Path, psm: str = "11") -> list[dict]:
    """tesseract TSV -> word dicts. Empty list when the binary is absent, so a
    box without tesseract degrades instead of lying."""
    try:
        cp = subprocess.run(
            ["tesseract", str(path), "stdout", "--psm", psm, "tsv"],
            capture_output=True, text=True, timeout=120,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return []
    words = []
    for line in cp.stdout.splitlines()[1:]:
        f = line.split("\t")
        if len(f) < 12:
            continue
        txt = f[11].strip()
        if not txt or not re.search(r"[A-Za-z0-9]", txt):
            continue
        try:
            conf = float(f[10])
        except ValueError:
            continue
        if conf < 0:
            continue
        words.append({"text": txt, "conf": conf,
                      "box": [int(f[6]), int(f[7]), int(f[8]), int(f[9])]})
    return words


def check_typeblock(path: Path, words: list[dict] | None = None) -> dict:
    """Is there a designed type block? The gate cannot say whether the words in
    it are real; see KNOWN LIMITS 1 and 2."""
    if words is None:
        words = ocr_words(path)
    runs = [w for w in words if len(w["text"]) >= TEXT_MIN_CHARS]
    if not runs:
        return {"name": "typeblock", "pass": True, "max_conf": 0.0,
                "n_long": 0, "n_tokens": len(words),
                "detail": f"no run of {TEXT_MIN_CHARS}+ characters",
                "flagged": []}
    top = max(runs, key=lambda w: w["conf"])
    flagged = sorted([w for w in runs if w["conf"] >= TYPEBLOCK_CONF],
                     key=lambda w: -w["conf"])
    return {
        "name": "typeblock",
        "pass": not flagged,
        "max_conf": round(top["conf"], 2),
        "max_token": top["text"],
        "n_long": len(runs),
        "n_tokens": len(words),
        "threshold": TYPEBLOCK_CONF,
        "detail": (f"peak {top['conf']:.1f} on {top['text']!r}; "
                   f"{len(flagged)} run(s) at or above {TYPEBLOCK_CONF} "
                   f"means a type block is present -- decide if you want one, "
                   f"the gate cannot say the words are real"),
        "flagged": [{"text": w["text"], "conf": w["conf"], "box": w["box"]}
                    for w in flagged[:8]],
    }


def _in_corner_strip(box, w_img, h_img, band=CORNER_BAND):
    x, y, ww, hh = box
    cx, cy = x + ww / 2.0, y + hh / 2.0
    bx, by = w_img * band, h_img * band
    if not ((cx < bx or cx > w_img - bx) and (cy < by or cy > h_img - by)):
        return False
    return ww <= w_img * CORNER_MAX_WIDTH_FRAC


def _baseline_neighbours(target, words):
    """A signature is short and isolated; a title block has neighbours in a row.
    Count tokens sharing this token's baseline row within a couple of ems."""
    x, y, ww, hh = target["box"]
    cy = y + hh / 2.0
    n = 0
    for o in words:
        if o is target:
            continue
        ox, oy, ow, oh = o["box"]
        if abs((oy + oh / 2.0) - cy) > max(hh, oh) * 0.8:
            continue
        gap = (ox - (x + ww)) if ox > x else (x - (ox + ow))
        if -ww * 0.4 <= gap <= max(ww, ow) * 2.5:
            n += 1
    return n


def check_corner(path: Path, words: list[dict] | None = None) -> dict:
    """Isolated marks in an outer strip. A review list, not a verdict."""
    if words is None:
        words = ocr_words(path)
    with Image.open(path) as im:
        w_img, h_img = im.size
    raw = [w for w in words
           if len(w["text"]) >= CORNER_MIN_CHARS
           and _in_corner_strip(w["box"], w_img, h_img)]
    lonely = [w for w in raw if _baseline_neighbours(w, words) == 0]
    return {
        "name": "corner",
        "pass": not lonely,
        "band": CORNER_BAND,
        "in_band": len(raw),
        "isolated": len(lonely),
        "detail": (f"{len(raw)} mark(s) in the outer "
                   f"{int(CORNER_BAND * 100)}% strips; {len(lonely)} of them "
                   f"isolated on their baseline (a title block has neighbours, "
                   f"a signature does not)"),
        "hits": [{"text": h["text"], "conf": h["conf"], "box": h["box"]}
                 for h in sorted(lonely, key=lambda h: -h["conf"])[:8]],
    }


def stamp_typeblock(src: Path, dst: Path, word: str = "SYNDICATE",
                    frac: float = 0.05) -> Path:
    """Negative control: burn a real, plain-sans word into a real corpus image.

    frac 0.05 of frame height in Liberation Sans Bold is the measured sweet
    spot: the word reads back at conf 90.4-91.8. At 0.20 the glyphs are so wide
    that tesseract starts splitting them ('SYNICA]T' at 49.2)."""
    with Image.open(src) as im:
        canvas = im.convert("RGB").copy()
    w, h = canvas.size
    d = ImageDraw.Draw(canvas)
    size = max(20, int(h * frac))
    font = ImageFont.truetype(CONTROL_FONT, size)
    d.rectangle([int(w * 0.04), int(h * 0.04),
                 int(w * 0.04) + int(size * 0.8 * len(word)),
                 int(h * 0.04) + int(size * 1.6)], fill=(0, 0, 0))
    d.text((int(w * 0.05), int(h * 0.05)), word, fill=(255, 255, 255), font=font)
    canvas.save(dst, quality=95)
    return dst

# Moved here verbatim from postgate.py, which carried one shared list for all
# four gates. The TEXT gates' own honest limits, in its own words:
KNOWN_LIMITS = [
    "typeblock cannot tell a real word from word-shaped gibberish: a real word "
    "burned into a corpus image reads conf 90.4, and issue 26's fabrications "
    "'Eosic'/'Niew'/'Conuum' read 89-93.",
    "An ornate display face can hide a real word below the threshold: issue 30's "
    "'AMPHETAMEME' reads 67.9, below the gibberish on issues 26 and 44.",
    "corner needs OCR to see the mark, so a forgery clean enough to defeat "
    "tesseract is invisible to it.",
]



CHECKS = (check_typeblock, check_corner)


def run(path, words=None) -> dict:
    path = Path(path)
    if words is None:
        words = ocr_words(path)
    checks = [check_typeblock(path, words), check_corner(path, words)]
    return {"image": str(path), "pass": all(c["pass"] for c in checks),
            "checks": checks, "known_limits": KNOWN_LIMITS}


def selftest(corpus_dir=None) -> int:
    """A real word burned into a plate must fire typeblock.

    Single-host controls do not work here, and upstream says so: "measured
    across 10 quiet images, 6 fired and 4 read between 0.0 and 63.0". A stamp
    on one arbitrary plate therefore proves nothing -- this first version used
    art[0] and read 'SYNI?ICATE' at 57.5, a clean FAIL caused entirely by
    picking a host tesseract cannot see.

    So this scans several quiet hosts and requires that AT LEAST ONE fires.
    Requiring more would be asserting something upstream measured to be false.

    THIS NEEDS REAL PLATES and will not run in a fresh clone. That is a property
    of OCR, not an oversight, and it was measured rather than assumed: replacing
    the corpus with ten synthesised cream plates fired 0 of 10, because a clean
    synthetic plate is not a host tesseract reads the way it reads real art.
    Tuning the synthetic plate until a stamp landed would have fabricated the
    control, so the requirement stands and the message says what to do instead.

    Point it at a folder with --corpus DIR, or symlink work/art beside this file.
    """
    import tempfile
    fails = []
    corpus_dir = Path(corpus_dir or (HERE / "work" / "art"))
    corpus = [p for p in sorted(corpus_dir.glob("*"))
              if p.suffix.lower() in (".jpg", ".jpeg", ".png")]
    if not corpus:
        print(f"  FAIL no plates in {corpus_dir}")
        print("       this control needs real images. Either")
        print(f"         ln -s /path/to/your/plates {HERE / 'work' / 'art'}")
        print("       or pass --corpus DIR")
        print("       a synthesised stand-in was tried and fired 0 of 10; see the docstring.")
        return 1

    quiet = [p for p in corpus if check_typeblock(p)["pass"]]
    if not quiet:
        print("  FAIL every plate already trips typeblock; no quiet host to stamp")
        return 1

    tried, fired = [], None
    clean_detail = ""
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        for p in quiet[:10]:
            tried.append(p.name)
            plate = stamp_typeblock(p, tmp / f"stamped-{p.stem}.jpg")
            got = check_typeblock(plate)
            if not got["pass"]:
                fired = (p, got)
                break

        # negative direction: an unstamped quiet plate must NOT fire
        clean = check_typeblock(quiet[0])
        clean_detail = clean["detail"][:80]
        if not clean["pass"]:
            fails.append(f"an unstamped quiet plate FAILED: {clean_detail}")

    print(f"  plates in         : {len(corpus)} from {corpus_dir}")
    print(f"  quiet hosts       : {len(quiet)}/{len(corpus)}")
    print(f"  hosts tried       : {len(tried)} {tried[:4]}{'...' if len(tried) > 4 else ''}")
    print(f"  unstamped control : pass={clean['pass']}  (must be True)")
    if fired is None:
        fails.append(f"no stamped host fired typeblock in {len(tried)} attempts")
    else:
        p, got = fired
        print(f"  fired on          : {p.name}")
        print(f"                       {got['detail'][:110]}")
    for f in fails:
        print(f"  FAIL {f}")
    print(f"PASS  text: typeblock fires on a stamped real word "
          f"(host {len(tried)}/{len(quiet)})" if fired and not fails else
          f"FAIL  text: {len(fails)} control(s) wrong")
    return 1 if fails else 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    ap.add_argument("image", nargs="?")
    ap.add_argument("--json", action="store_true", help="machine payload")
    ap.add_argument("--psm", default="11")
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--corpus", default=None, metavar="DIR",
                    help="folder of plates for --selftest (default work/art)")
    ap.add_argument("--known-limits", action="store_true")
    a = ap.parse_args(argv)
    if a.known_limits:
        print(json.dumps(KNOWN_LIMITS, indent=1))
        return 0
    if a.selftest:
        return selftest(a.corpus)
    if not a.image:
        ap.print_help()
        return 2
    p = Path(a.image)
    r = run(p, ocr_words(p, a.psm))
    print(json.dumps(r, indent=1) if a.json else
          f"{r['image']}  ->  {'PASS' if r['pass'] else 'REVIEW'}\n  " +
          "\n  ".join(f"[{'ok  ' if c['pass'] else 'WARN'}] {c['name']:11} "
                       f"{c['detail']}" for c in r["checks"]))
    return 0 if r["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
