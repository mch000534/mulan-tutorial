#!/usr/bin/env python3
"""Convert generated PNG assets to JPEG and drop the PNGs.

The ComfyUI pipeline writes PNG, which costs roughly 8x the disk of a
well-encoded JPEG at the same quality. This script converts in place and
removes the source file only after the JPEG is written and verified.

Run:
  python3 scripts/to_jpg.py                 # convert everything under assets/
  python3 scripts/to_jpg.py --keep-png      # keep the PNGs
  python3 scripts/to_jpg.py --quality 92    # higher quality, bigger files
"""

import argparse
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent


def parse_args():
    parser = argparse.ArgumentParser(description="Convert PNG assets to JPEG.")
    parser.add_argument("--roots", nargs="*", default=["assets"], help="directories to walk")
    parser.add_argument("--quality", type=int, default=90, help="JPEG quality (default 90)")
    parser.add_argument("--keep-png", action="store_true", help="do not delete the source PNG")
    parser.add_argument("--force", action="store_true", help="re-convert even if the JPEG exists")
    return parser.parse_args()


def convert(path: Path, quality: int) -> int:
    target = path.with_suffix(".jpg")
    if target.exists() and not ARGS.force:
        print(f"  skip {path.relative_to(ROOT)} (jpg exists)")
        return 0

    with Image.open(path) as image:
        if image.mode in ("RGBA", "LA", "P"):
            image = image.convert("RGBA")
            background = Image.new("RGB", image.size, (255, 255, 255))
            background.paste(image, mask=image.split()[-1])
            image = background
        else:
            image = image.convert("RGB")
        image.save(target, "JPEG", quality=quality, subsampling=0, optimize=True, progressive=True)

    with Image.open(target) as check:
        if check.size != image.size:
            raise RuntimeError(f"size mismatch for {target}")

    return target.stat().st_size


def main():
    global ARGS
    ARGS = parse_args()

    pngs = []
    for root in ARGS.roots:
        base = Path(root)
        if not base.is_absolute():
            base = ROOT / base
        if not base.exists():
            continue
        pngs.extend(sorted(base.rglob("*.png")))

    if not pngs:
        print("no PNG files found")
        return

    before = sum(p.stat().st_size for p in pngs)
    after = 0
    for index, png in enumerate(pngs, 1):
        print(f"[{index}/{len(pngs)}] {png.relative_to(ROOT)}", flush=True)
        try:
            after += convert(png, ARGS.quality)
        except Exception as error:
            print(f"  FAILED: {error}")
            after += png.stat().st_size
            continue
        if not ARGS.keep_png:
            png.unlink()

    print()
    print(f"files:  {len(pngs)}")
    print(f"before: {before / 1024 / 1024:.1f} MB")
    print(f"after:  {after / 1024 / 1024:.1f} MB")
    if before:
        print(f"saved:  {(1 - after / before) * 100:.1f}%")


if __name__ == "__main__":
    main()
