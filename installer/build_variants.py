"""Build the Revit installer from the shared AutoCAD/Revit installer.

Both products use one payload; only the batch header selects the product. The Revit file is
published in Moorlack/aec-model-bridge (installer/SetupMCP Revit.cmd) and must equal
revit_variant(<this repo's installer>).

    python installer/build_variants.py <path to aec-model-bridge checkout>
"""

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SHARED = HERE / "SetupMCP AutoCAD.cmd"

AUTOCAD_HEADER = ('set "AECMB_PRODUCT=AutoCAD"\n', 'set "AECMB_TITLE=AutoCAD MCP setup"\n')
REVIT_HEADER = ('set "AECMB_PRODUCT=Revit"\n', 'set "AECMB_TITLE=AEC Model Bridge Revit setup"\n')


def revit_variant(text: str) -> str:
    for old, new in zip(AUTOCAD_HEADER, REVIT_HEADER):
        if text.count(old) != 1:
            raise ValueError(f"shared installer header line not found exactly once: {old!r}")
        text = text.replace(old, new)
    return text


def main(argv):
    if len(argv) != 2:
        print(__doc__)
        return 2
    target = Path(argv[1]) / "installer" / "SetupMCP Revit.cmd"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(revit_variant(SHARED.read_bytes().decode("utf-8")).encode("utf-8"))
    print(f"written {target}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
