"""Generate the scenario card covers with Gemini: `cd backend && uv run --with pillow python ../scripts/generate_covers.py ../frontend/public/covers [theme ...]` (default: all themes).
Reads GEMINI_API_KEY from the environment. Writes <theme>.webp (at most 1600x900) and <theme>.png (the original; not committed).
The shared style prompt lives in nlab.api.pictures, one copy for this script and the app's painter."""

import base64
import io
import json
import os
import sys
import urllib.request
from pathlib import Path

from PIL import Image

from nlab.api.pictures import STYLE

MODEL = "gemini-3-pro-image"
SCENES = {
    "field": "open dry landscape at dawn, a dirt road leading towards distant hills, one parked white off-road vehicle",
    "camp": "a displacement camp on a wide plain: rows of weathered white tents, water tanks, a few people walking far away",
    "checkpoint": "a roadside checkpoint on a dusty road: a lowered barrier pole, a sandbag wall, a small guard hut, trucks waiting in a line",
    "detention": "the outside of a small concrete police station at dusk, a barred window, a bench by the door, one street lamp",
    "border": "a desolate no man's land between two long border fences under a wide sky, an empty road and a closed gate far away",
    "school": "a damaged rural schoolhouse seen from its own school yard, a blank chalkboard through a broken window, an empty swing; the foreground is the same yard's worn earth in soft shadow, one continuous scene, quiet morning",
    "hospital": "a small field hospital: canvas tents beside a low building, folded stretchers outside, soft evening light",
    "convoy": "a convoy of plain white trucks on a winding mountain road, a trail of dust behind them",
    "office": "inside a modest meeting room, seen from across a wooden table: two chairs facing each other, tea glasses, a plain map with no writing on the wall, light through blinds; the foreground is the near end of the same table and the floor in soft shadow, one continuous interior, nothing outdoors",
}


def generate(theme: str, key: str) -> bytes:
    body = {
        "contents": [{"parts": [{"text": STYLE + SCENES[theme]}]}],
        "generationConfig": {"responseModalities": ["IMAGE"], "imageConfig": {"aspectRatio": "16:9"}},
    }
    request = urllib.request.Request(
        f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL}:generateContent",
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json", "x-goog-api-key": key},
    )
    with urllib.request.urlopen(request, timeout=300) as response:
        answer = json.load(response)
    for part in answer["candidates"][0]["content"]["parts"]:
        if "inlineData" in part:
            return base64.b64decode(part["inlineData"]["data"])
    raise RuntimeError(f"{theme}: no image in the answer: {json.dumps(answer)[:300]}")


def main() -> None:
    out = Path(sys.argv[1])
    out.mkdir(parents=True, exist_ok=True)
    key = os.environ["GEMINI_API_KEY"]
    for theme in sys.argv[2:] or list(SCENES):
        raw = generate(theme, key)
        (out / f"{theme}.png").write_bytes(raw)
        image = Image.open(io.BytesIO(raw)).convert("RGB")
        image.thumbnail((1600, 900))
        image.save(out / f"{theme}.webp", "WEBP", quality=80, method=6)
        print(theme, image.size, (out / f"{theme}.webp").stat().st_size // 1024, "KB")


if __name__ == "__main__":
    main()
