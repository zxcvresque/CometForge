"""Convert the approved transparent PNG to native macOS/Windows icons."""
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]


def main():
    assets = ROOT / "packaging" / "assets"
    assets.mkdir(parents=True, exist_ok=True)
    image = Image.open(ROOT / "static" / "cometforge-logo.png").convert("RGBA")
    image = image.resize((1024, 1024), Image.Resampling.LANCZOS)
    image.save(assets / "CometForge.icns", format="ICNS")
    image.save(assets / "CometForge.ico", format="ICO", bitmap_format="bmp", sizes=[
        (16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])


if __name__ == "__main__":
    main()
