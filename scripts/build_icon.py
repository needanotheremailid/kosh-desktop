"""Rebuild the original Kosh monogram using Pillow, a development-only tool."""
from pathlib import Path
from PIL import Image, ImageDraw

root = Path(__file__).resolve().parents[1]
out = root / "assets"
out.mkdir(exist_ok=True)
image = Image.new("RGBA", (512, 512), (0, 0, 0, 0))
draw = ImageDraw.Draw(image)
draw.rounded_rectangle((20, 20, 492, 492), radius=92, fill="#173DDF")
draw.rectangle((133, 118, 176, 388), fill="white")
draw.polygon(((176, 243), (313, 118), (375, 118), (231, 256), (381, 388), (317, 388), (176, 267)), fill="white")
draw.line((117, 427, 395, 427), fill="white", width=9)
image.save(out / "App.ico", sizes=[(16,16),(24,24),(32,32),(48,48),(64,64),(128,128),(256,256)])
image.save(out / "Kosh.png")
