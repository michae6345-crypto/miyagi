"""
Make the Microsoft Store (MSIX) tile images in app/build/appx from the brand's tree PNGs.

    cd app && python scripts/make-store-tiles.py      # needs Pillow; re-run when the logo changes

electron-builder packs everything in build/appx into the package's assets and builds resources.pri from the
.scale-* and .targetsize-* names, so Windows picks the right size. The cut follows brand/BRAND.md by the size
the tree is drawn at: small under 48 px, icon from 48 to 140 px, full above that. Plated tiles sit on the
manifest's white background (appx.backgroundColor, like the app icon's white plate). The unplated taskbar and
Start icons use the -dark cut on a dark taskbar and the normal cut on a light one.
"""
from pathlib import Path

from PIL import Image

APP = Path(__file__).resolve().parent.parent
PNG = APP / "brand" / "logo" / "png"
OUT = APP / "build" / "appx"


def tree(px: float, dark: bool) -> Image.Image:
    name = "tree-small" if px < 48 else "tree-icon" if px <= 140 else "tree-full"
    im = Image.open(PNG / f"{name}{'-dark' if dark else ''}.png").convert("RGBA")
    return im.crop(im.getbbox())


def tile(w: int, h: int, fill: float, dark: bool = False) -> Image.Image:
    """The tree, its longer side `fill` of the tile's shorter side, centered on a transparent w x h canvas."""
    side = min(w, h) * fill
    t = tree(side, dark)
    s = side / max(t.size)
    t = t.resize((max(1, round(t.width * s)), max(1, round(t.height * s))), Image.LANCZOS)
    canvas = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    canvas.alpha_composite(t, ((w - t.width) // 2, (h - t.height) // 2))
    return canvas


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for old in OUT.glob("*.png"):
        old.unlink()
    files: dict[str, Image.Image] = {}
    for scale in (100, 200, 400):
        k = scale / 100
        files[f"StoreLogo.scale-{scale}.png"] = tile(round(50 * k), round(50 * k), 0.9)
        files[f"Square44x44Logo.scale-{scale}.png"] = tile(round(44 * k), round(44 * k), 0.8)
        files[f"Square150x150Logo.scale-{scale}.png"] = tile(round(150 * k), round(150 * k), 0.62)
        files[f"Wide310x150Logo.scale-{scale}.png"] = tile(round(310 * k), round(150 * k), 0.66)
    for scale in (100, 200):
        k = scale / 100
        files[f"SmallTile.scale-{scale}.png"] = tile(round(71 * k), round(71 * k), 0.72)
        files[f"LargeTile.scale-{scale}.png"] = tile(round(310 * k), round(310 * k), 0.6)
    for size in (16, 24, 32, 48, 256):
        files[f"Square44x44Logo.targetsize-{size}.png"] = tile(size, size, 0.94)
        files[f"Square44x44Logo.targetsize-{size}_altform-unplated.png"] = tile(size, size, 0.94, dark=True)
        files[f"Square44x44Logo.targetsize-{size}_altform-lightunplated.png"] = tile(size, size, 0.94)
    for name, im in files.items():
        im.save(OUT / name, optimize=True)
    print(f"{len(files)} images in {OUT}")


if __name__ == "__main__":
    main()
