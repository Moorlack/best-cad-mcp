"""MLINE style element offsets read from DXF text (COM does not expose MLSTYLE offsets)."""

import math
from typing import Dict, List, Optional


def parse_mline_styles(dxf_text: str) -> Dict[str, List[float]]:
    """Map UPPER-CASE MLINESTYLE name -> element offsets (group 49) in file order."""
    lines = str(dxf_text or "").splitlines()
    styles: Dict[str, List[float]] = {}
    name: Optional[str] = None
    offsets: List[float] = []
    inside = False

    def close():
        if inside and name and offsets:
            styles[name.upper()] = list(offsets)

    for i in range(0, len(lines) - 1, 2):
        code, value = lines[i].strip(), lines[i + 1].strip()
        if code == "0":
            close()
            inside = value.upper() == "MLINESTYLE"
            name, offsets = None, []
        elif inside and code == "2" and name is None:
            name = value
        elif inside and code == "49":
            try:
                number = float(value)
            except ValueError:
                number = math.nan
            offsets.append(number)
    close()
    return {key: value for key, value in styles.items() if all(math.isfinite(v) for v in value)}


def face_offsets(offsets, justification) -> Optional[tuple]:
    """(upper, lower) outermost element offsets in style units for a justification.

    0 = top (the highest element sits on the vertices), 1 = zero, 2 = bottom.
    None when the style has fewer than two distinct elements or the input is unusable.
    """
    try:
        values = [float(v) for v in offsets]
    except (TypeError, ValueError):
        return None
    if len(values) < 2 or not all(math.isfinite(v) for v in values) or justification not in (0, 1, 2):
        return None
    hi, lo = max(values), min(values)
    if hi - lo <= 1e-9:
        return None
    shift = {0: -hi, 1: 0.0, 2: -lo}[justification]
    return hi + shift, lo + shift
