from __future__ import annotations

import json
import shutil
from pathlib import Path
from random import choice

MEME_DIR = Path(__file__).resolve().parent
MEME_IMAGE_DIR = MEME_DIR / "images"
MEME_METADATA_PATH = MEME_DIR / "memes.json"
ALLOWED_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".webp"}


def ensure_dirs() -> None:
    MEME_DIR.mkdir(parents=True, exist_ok=True)
    MEME_IMAGE_DIR.mkdir(parents=True, exist_ok=True)


def load_memes() -> dict[str, dict[str, str]]:
    if not MEME_METADATA_PATH.exists():
        return {}
    try:
        data = json.loads(MEME_METADATA_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def write_memes(memes: dict[str, dict[str, str]]) -> None:
    ensure_dirs()
    MEME_METADATA_PATH.write_text(
        json.dumps(memes, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def normalize_name(name: str) -> str:
    normalized = "".join(ch.lower() if ch.isalnum() else "_" for ch in name.strip())
    normalized = "_".join(part for part in normalized.split("_") if part)
    return normalized or "meme"


def make_unique_filename(name: str, suffix: str) -> str:
    base = normalize_name(name)
    candidate = f"{base}{suffix}"
    counter = 1
    while (MEME_IMAGE_DIR / candidate).exists():
        candidate = f"{base}_{counter}{suffix}"
        counter += 1
    return candidate


def save_meme_image(
    image_path: str,
    name: str | None = None,
    description: str = "",
    trigger: str = "",
    category: str | None = None,
) -> dict[str, str]:
    ensure_dirs()
    source = Path(image_path)
    if not source.exists():
        raise FileNotFoundError(f"Image file not found: {image_path}")

    suffix = source.suffix.lower()
    if suffix not in ALLOWED_EXTENSIONS:
        raise ValueError(f"Unsupported image extension: {suffix}")

    dest_name = name or source.stem
    filename = make_unique_filename(dest_name, suffix)
    destination = MEME_IMAGE_DIR / filename
    shutil.copy2(source, destination)

    meme_name = normalize_name(dest_name)
    meme_entry: dict[str, str] = {
        "name": meme_name,
        "path": str(destination.resolve()),
        "description": description or f"Meme image file {filename}",
        "trigger": trigger,
    }
    if category:
        meme_entry["category"] = category

    memes = load_memes()
    memes[meme_name] = meme_entry
    write_memes(memes)
    return meme_entry


def get_meme_for_text(text: str, category: str | None = None) -> dict[str, str]:
    memes = load_memes()
    if not memes:
        return {
            "name": "default",
            "path": "",
            "description": "No meme data configured.",
        }

    lowered = text.lower()
    if category:
        for meme in memes.values():
            if meme.get("category") == category or meme.get("name") == category:
                return meme

    for meme in memes.values():
        trigger = (meme.get("trigger") or "").lower()
        if trigger and trigger in lowered:
            return meme

    return choice(list(memes.values()))

