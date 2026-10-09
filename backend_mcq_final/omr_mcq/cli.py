"""Command-line entry point.

    python -m omr_mcq sheet.jpg --layout neet
    python -m omr_mcq sheet.jpg --layout neet --key key.json --annotate out.png
    python -m omr_mcq sheet.jpg --layout neet --json result.json

Exists so the reader can be checked against a new sheet without writing any
code, which is the first thing anyone does with a form they have not seen.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import layout as layout_mod
from .marking import MarkingScheme
from .reader import (SheetUnreadable, annotate, detect_layout, diagnose,
                     read_sheet)


def _load_key(path: str | None) -> dict | None:
    """Read an answer key: {"1": "C", "2": "A"} or {"1": 3, ...}.

    Numeric values are accepted because these sheets print their options as
    1/2/3/4; they are mapped onto the layout's own labels so a key written
    either way scores the same.
    """
    if not path:
        return None
    raw = json.loads(Path(path).read_text())
    return {int(k): v for k, v in raw.items()}


def _normalise_key(key: dict | None, labels: tuple[str, ...]) -> dict | None:
    if not key:
        return None
    out = {}
    for q, value in key.items():
        if isinstance(value, int) and 1 <= value <= len(labels):
            out[q] = labels[value - 1]
        else:
            out[q] = str(value)
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="omr_mcq", description="Read an OMR answer sheet.")
    parser.add_argument("image", help="photo or scan of the sheet")
    parser.add_argument("--layout", default="auto",
                        help="sheet layout, or 'auto' to detect: "
                             f"{', '.join(sorted(layout_mod.LAYOUTS))}")
    parser.add_argument("--key", help="answer key JSON, {question: option}")
    parser.add_argument("--annotate", metavar="PATH",
                        help="write the marked-up review image here")
    parser.add_argument("--diagnose", metavar="PATH",
                        help="write the localisation diagnostic here")
    parser.add_argument("--json", metavar="PATH", dest="json_out",
                        help="write the full result as JSON here")
    parser.add_argument("--quiet", action="store_true",
                        help="print nothing but errors")
    args = parser.parse_args(argv)

    auto = args.layout.strip().lower() == "auto"
    sheet_layout = None
    if not auto:
        try:
            sheet_layout = layout_mod.get(args.layout)
        except KeyError as exc:
            parser.error(str(exc))

    try:
        if auto:
            # Detect first, then re-read with the key: the answer key's option
            # labels only make sense once the layout is known.
            sheet_layout, _probe = detect_layout(args.image)
        key = _normalise_key(_load_key(args.key), sheet_layout.options)
        result = read_sheet(args.image, sheet_layout, answer_key=key,
                            scheme=MarkingScheme())
    except SheetUnreadable as exc:
        print(f"could not read sheet ({exc.reason}): {exc.hint}", file=sys.stderr)
        return 2

    if args.annotate:
        _write_image(args.annotate, annotate(result))
    if args.diagnose:
        _write_image(args.diagnose, diagnose(result))
    if args.json_out:
        out = Path(args.json_out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(result.as_dict(), indent=2))

    if not args.quiet:
        _report(result)
    return 0


def _write_image(path: str, image) -> None:
    """Save *image*, creating the directory and checking the write landed.

    cv2.imwrite returns False rather than raising when the directory does not
    exist or the extension is unknown, so a bare call reports success while
    writing nothing -- which is how a debug image silently goes missing right
    when someone needs it.
    """
    import cv2

    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    if not cv2.imwrite(str(target), image):
        raise OSError(f"could not write {target} "
                      f"(unsupported extension {target.suffix!r}?)")


def _report(result) -> None:
    g = result.grid
    print(f"{result.layout.name}: {g['blocks']} blocks x {g['rows']} rows, "
          f"pitch {g['row_pitch']}/{g['col_pitch']}px, r={g['radius']}px, "
          f"skew {g['skew_deg']:+}deg, fit {g['fit_score']}")
    print(f"answered {result.answered} of {result.layout.total_questions}, "
          f"{len(result.needs_review)} need review")

    if result.score:
        s = result.score
        print(f"score {s.total} / {s.max_score}   "
              f"correct {s.correct}  wrong {s.wrong}  blank {s.unattempted}"
              + (f"  invalid {s.invalid}" if s.invalid else "")
              + (f"  unscored {s.unscored}" if s.unscored else ""))
        for subject, value in s.subject_scores.items():
            print(f"  {subject:<16}{value}")

    if result.needs_review:
        print("needs review: " + ", ".join(
            f"Q{q}" for q in result.needs_review[:20])
            + (" ..." if len(result.needs_review) > 20 else ""))


if __name__ == "__main__":
    raise SystemExit(main())
