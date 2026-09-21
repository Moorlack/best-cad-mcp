"""Exercise the WMF-to-model-image pipeline without opening or modifying CAD."""

from __future__ import annotations

import argparse
import json
import shutil
import tempfile
from pathlib import Path

from src.cad_understanding import vision
from src.cad_understanding.result import error_result, ok_result


FIXTURE = Path(__file__).parent / "assets" / "visual-selftest.wmf"


def check_visual_pipeline():
    """Render a bundled AutoCAD WMF, verify pixels, then test image downscaling.

    All generated artifacts are temporary. This proves the local conversion
    pipeline, not live AutoCAD export, geometry accuracy, or client image display.
    """
    checks = []

    def fail(name, detail):
        checks.append({"name": name, "ok": False, "detail": detail})
        return error_result("Visual pipeline self-test failed.", data={"checks": checks},
                            warnings=["Repair the visual runtime before relying on image review."])

    pil = vision._pillow()
    if pil is None:
        return fail("pillow", "Pillow cannot be imported. Install this checkout with pip install -e .[visual].")
    checks.append({"name": "pillow", "ok": True, "detail": "Pillow imported."})
    if not FIXTURE.is_file():
        return fail("fixture", "Bundled WMF is missing; reinstall the complete package/source checkout.")
    try:
        with tempfile.TemporaryDirectory(prefix="cad-visual-selftest-") as temp:
            source = Path(temp) / "sample.wmf"
            shutil.copyfile(FIXTURE, source)
            prepared = vision.prepare_model_image(str(source), max_dim=512)
            if not prepared.get("ok") or not prepared.get("embeddable"):
                return fail("wmf_to_model_image", prepared.get("reason") or "WMF rendering failed.")
            output = Path(prepared["image_path"])
            with pil.open(output) as rendered:
                rendered.load()
                width, height = rendered.size
                if rendered.format not in {"PNG", "JPEG"} or not (0 < width <= 512 and 0 < height <= 512):
                    return fail("wmf_to_model_image", "Unexpected image format or dimensions.")
                # A nonempty file or successful process exit can still hide a blank render.
                with rendered.convert("RGB") as rgb:
                    if all(low == high for low, high in rgb.getextrema()):
                        return fail("wmf_to_model_image", "Rendered fixture is blank/uniform.")
            checks.append({"name": "wmf_to_model_image", "ok": True,
                           "detail": "Bundled WMF rendered to a nonuniform model-viewable image.",
                           "width": width, "height": height})

            # Exercise resizing deterministically even if the renderer produces a small image.
            large = Path(temp) / "resize.bmp"
            with pil.new("RGB", (1024, 512), "white") as image:
                image.save(large)
            resized = vision.prepare_model_image(str(large), max_dim=256)
            if not resized.get("embeddable") or not resized.get("downscaled"):
                return fail("transcode_and_resize", resized.get("reason") or "Image was not downscaled.")
            with pil.open(resized["image_path"]) as image:
                image.load()
                if image.size != (256, 128) or image.format != "PNG":
                    return fail("transcode_and_resize", "PNG resizing did not preserve aspect ratio.")
            checks.append({"name": "transcode_and_resize", "ok": True,
                           "detail": "BMP converted to PNG and resized from 1024x512 to 256x128."})
    except Exception as exc:
        return fail("runtime", f"{type(exc).__name__}: {exc}")
    return ok_result("Visual pipeline self-test passed; no DWG accessed.",
                     data={"checks": checks, "live_autocad_export_tested": False,
                           "client_image_display_tested": False, "temporary_artifacts_removed": True})


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    result = check_visual_pipeline()
    if args.json:
        print(json.dumps(result, ensure_ascii=True))
    else:
        print(result["message"])
        for check in result["data"]["checks"]:
            print(f"[{'OK' if check['ok'] else 'FAIL'}] {check['name']}: {check['detail']}")
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
