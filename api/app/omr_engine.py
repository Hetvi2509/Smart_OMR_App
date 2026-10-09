"""Import the existing OMR engine from backend_mcq_final.

The engine stays where it is and is used as a library, not copied: a second
copy of the vision code would drift from the one its own test suite and
benchmark cover.  This module only puts it on sys.path and re-exports the
handful of names the API needs.
"""
from __future__ import annotations

import sys
from pathlib import Path

# <repo>/api/app/omr_engine.py -> <repo>/backend_mcq_final
ENGINE_ROOT = Path(__file__).resolve().parents[2] / "backend_mcq_final"

if not (ENGINE_ROOT / "omr_mcq").is_dir():
    raise RuntimeError(
        f"OMR engine not found at {ENGINE_ROOT}. The API expects the "
        f"backend_mcq_final package to sit beside the api/ directory.")

if str(ENGINE_ROOT) not in sys.path:
    sys.path.insert(0, str(ENGINE_ROOT))

from omr_mcq import (                                          # noqa: E402
    MarkingScheme,
    SheetUnreadable,
    annotate,
    layout as layout_mod,
    read_sheet,
)
from omr_mcq.marking import apply_scheme                       # noqa: E402

# Layout names the API accepts, for validation and for the mobile picker.
LAYOUT_NAMES = tuple(sorted(layout_mod.LAYOUTS))


def get_layout(name: str):
    """Look up a layout, raising ValueError (not KeyError) for a bad name."""
    try:
        return layout_mod.get(name)
    except KeyError as exc:
        raise ValueError(str(exc)) from None


def layout_info() -> list[dict]:
    """Describe the built-in layouts for the app's test-creation screen."""
    out = []
    for name in LAYOUT_NAMES:
        lay = layout_mod.get(name)
        out.append({
            "key": name,
            "name": lay.name,
            "blocks": lay.blocks,
            "rows_per_block": lay.rows_per_block,
            "total_questions": lay.total_questions,
            "options": list(lay.options),
            "subjects": list(lay.subjects),
        })
    return out


__all__ = ["MarkingScheme", "SheetUnreadable", "annotate", "apply_scheme",
           "get_layout", "layout_info", "read_sheet", "LAYOUT_NAMES"]
