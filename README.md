# amph-text-gate

**F6 TEXT** -- OCR band + corner marks

The OCR band and the corner marks. Both are here because both are ways a cover fails while still looking finished.

## Licence -- read this first

**Noncommercial.** `amph-text-gate` is licensed under the
[PolyForm Noncommercial License 1.0.0](https://polyformproject.org/licenses/noncommercial/1.0.0).
You may use, copy, modify and distribute it for any noncommercial purpose, and
for any commercial purpose only with a separate written grant from the copyright holder. Full text is in
`LICENSE`.

The calibration numbers this module ships were measured on a specific corpus,
not derived from first principles. Read `## Known limits` before trusting a
threshold -- that section is the reason the module is worth having.

## Run it

```bash
pip install -e .
python3 text.py --selftest
```

## Where this came from

`text.py` is extracted VERBATIM from `engine/postgate.py`
(sha8 `66296cf3`) by AST line range: the constants `TEXT_MIN_CHARS, TYPEBLOCK_CONF,
CORNER_BAND, CORNER_MIN_CHARS, CORNER_MAX_WIDTH_FRAC, CONTROL_FONT`
and the functions `ocr_words, check_typeblock, _in_corner_strip,
_baseline_neighbours, check_corner, stamp_typeblock`. The bodies are byte-for-byte;
only the header, the limits list and the CLI are new.

Every file here is emitted by `amph-comic/tools/build_modules.py`, which copies
from `amph-public/engine/`. Nothing in this repo is hand-maintained. Regenerate
and verify with:

```bash
python3 tools/build_modules.py --check --out <this repo's parent>
```

## Known limits

This module ships its own limits rather than hiding them -- see `text.py.py
--known-limits`, or `known-limits.json` in the F8 repo, which harvests all four.
