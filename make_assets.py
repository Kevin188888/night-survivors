"""Makes the game pictures. Run this on your computer:  python make_assets.py

It writes crisp 3x copies of raw_art/ into assets/, plus two recoloured gems.
raw_art/ is never changed. main.py only reads the finished files in assets/.
"""

from pathlib import Path

from PIL import Image

SCALE = 3
RAW = Path(__file__).parent / "raw_art"
OUT = Path(__file__).parent / "assets"

# The gems are copies of raw_art/gem.png in one flat colour each.
GEM_COLOURS = {
    "gem_blue.png": (64, 156, 255),   # an XP 1 gem
    "gem_pink.png": (255, 108, 200),  # an XP 2 gem
}


def crisp_copy(image: Image.Image, factor: int = SCALE) -> Image.Image:
    """Grow by whole pixels so the art stays sharp (no blurring)."""
    return image.resize((image.width * factor, image.height * factor), Image.Resampling.NEAREST)


def recolour(image: Image.Image, colour: tuple[int, int, int]) -> Image.Image:
    """Paint a new colour over the picture but keep its light and dark facets."""
    red, green, blue, alpha = image.split()
    brightest = max(red.getextrema()[1], green.getextrema()[1], blue.getextrema()[1]) or 255

    def shaded(channel: Image.Image, target: int) -> Image.Image:
        # 15% of the colour always stays, so the dark parts are not black holes.
        return channel.point(lambda value: int(target * (0.15 + 0.85 * value / brightest)))

    return Image.merge("RGBA", (shaded(red, colour[0]), shaded(green, colour[1]),
                                shaded(blue, colour[2]), alpha))


def main() -> None:
    OUT.mkdir(exist_ok=True)
    for source in sorted(RAW.glob("*.png")):
        image = Image.open(source).convert("RGBA")
        result = crisp_copy(image)
        result.save(OUT / source.name)
        print(f"{source.name}: {image.width}x{image.height} -> {result.width}x{result.height}")

    gem = Image.open(RAW / "gem.png").convert("RGBA")
    for name, colour in GEM_COLOURS.items():
        result = crisp_copy(recolour(gem, colour))
        result.save(OUT / name)
        print(f"gem.png -> {name}: {result.width}x{result.height}, colour {colour}")

    print(f"wrote {len(list(OUT.glob('*.png')))} files to {OUT}")


if __name__ == "__main__":
    main()
