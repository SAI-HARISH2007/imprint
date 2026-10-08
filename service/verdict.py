"""The four verdicts. Pure functions, no model and no network, so they are easy to test.

Thresholds come from the phase 1 numbers (256-bit pHash):
  ordinary sharing stays within distance 12, a pasted-over-10% edit starts at 30,
  unrelated images start at 102. They are provisional until the full benchmark.
"""
from dataclasses import dataclass

from core import distance

T_MATCH = 16   # watermark found: at or below this, the image is consistent with the registered one
T_NEAR = 24    # watermark lost: at or below this, call it a likely copy
T_DUP = 10     # registering: at or below this, the image looks like an earlier registration


@dataclass
class Record:
    watermark_id: str
    fingerprint: str
    signer: str
    timestamp: int


def find_near_duplicate(fp: str, records: list[Record], threshold: int = T_DUP):
    """Closest earlier record within threshold, or None. Used at registration to stop squatting."""
    best = None
    for r in records:
        d = distance(fp, r.fingerprint)
        if d <= threshold and (best is None or d < best[1]):
            best = (r, d)
    return best


def decide(wm_present: bool, wm_id: str | None, fp: str,
           record: Record | None, records: list[Record]) -> dict:
    """record: the registry entry for wm_id, if there is one. records: all entries, for the fallback."""
    if wm_present and record is not None:
        d = distance(fp, record.fingerprint)
        if d <= T_MATCH:
            return {"verdict": "verified", "distance": d, "record": record,
                    "message": "Registered, and the content is consistent with the registered version."}
        return {"verdict": "altered", "distance": d, "record": record,
                "message": "This descends from a registered image, but its content has changed "
                           "(edited or cropped)."}

    best = None
    for r in records:
        d = distance(fp, r.fingerprint)
        if best is None or d < best[1]:
            best = (r, d)
    if best is not None and best[1] <= T_NEAR:
        return {"verdict": "likely_match", "distance": best[1], "record": best[0],
                "message": "The hidden mark was lost, but this looks like a registered image. "
                           "Lower confidence."}

    note = ""
    if wm_present and record is None:
        note = " A mark was found but its ID is not in this registry."
    return {"verdict": "not_found", "distance": None, "record": None,
            "message": "No registration found. That does not mean the image is fake." + note}
