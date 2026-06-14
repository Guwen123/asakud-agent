from __future__ import annotations

import base64
import html
import json
import mimetypes
import random
import re
import shutil
import uuid
from pathlib import Path
from typing import Any

import httpx
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.runnables import Runnable, RunnableLambda

from ..config_loader import load_config, project_path
from ..models.factory import build_chat_model, build_multimodal_model
from ..prompts import MEME_PICKER_PROMPT, MEME_VISION_PROMPT

CQ_IMAGE_RE = re.compile(r"\[CQ:image,([^\]]+)\]")
MEME_ACTION_KEYWORDS = ["设置表情包", "添加表情包", "保存表情包"]
NAME_SPLITTERS = ["为", "叫", "成"]
ALLOWED_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".webp"}
DEFAULT_EMOTION = "图片表情"


def get_router_meme_node(config: dict | None = None) -> Runnable:
    cfg = config or load_config()
    multimodal_model = build_multimodal_model(
        cfg,
        overrides={"temperature": 0.0, "max_output_tokens": 300},
    )

    def _run(state: dict[str, Any]) -> dict[str, Any]:
        raw_input = str(state.get("user_input", "") or "")
        print(raw_input)
        image_refs = _extract_image_refs(raw_input)
        if not image_refs:
            return state

        image_ref = image_refs[0]
        cleaned_text = CQ_IMAGE_RE.sub("", raw_input).strip()
        emotion, emotion_debug = _analyze_image_emotion(
            multimodal_model=multimodal_model,
            image_ref=image_ref,
            user_text=cleaned_text,
        )

        explicit_name = _extract_explicit_meme_name(cleaned_text)
        auto_probability = float(cfg.get("meme", {}).get("auto_collect_probability", 0.35))
        should_save = bool(explicit_name) or random.random() < auto_probability
        saved_entry: dict[str, str] = {}
        if should_save:
            meme_name = explicit_name or f"auto_{uuid.uuid4().hex[:6]}"
            try:
                saved_entry = save_meme_reference(
                    image_ref=image_ref,
                    config=cfg,
                    name=meme_name,
                    emotion=emotion,
                )
            except Exception as exc:
                saved_entry = {"error": str(exc)}

        normalized_input = f"[meme_emotion:{emotion}]"
        if explicit_name:
            normalized_input += f" [meme_saved_as:{explicit_name}]"
        if cleaned_text:
            normalized_input = f"{normalized_input} {cleaned_text}"

        state["user_input"] = normalized_input
        messages = list(state.get("messages", []))
        if messages and isinstance(messages[-1], HumanMessage):
            messages[-1] = HumanMessage(content=normalized_input)
            state["messages"] = messages

        memory = dict(state.get("memory", {}) or {})
        memory["meme"] = {
            "emotion": emotion,
            "emotion_debug": emotion_debug,
            "image_ref": image_ref,
            "explicit_name": explicit_name,
            "saved": bool(saved_entry) and "error" not in saved_entry,
            "save_error": saved_entry.get("error", ""),
        }
        state["memory"] = memory
        return state

    return RunnableLambda(_run)


def get_print_meme_node(config: dict | None = None) -> Runnable:
    cfg = config or load_config()
    picker_model = build_chat_model(
        cfg,
        overrides={"temperature": 0.0, "max_output_tokens": 300},
    )

    def _run(state: dict[str, Any]) -> dict[str, Any]:
        message = str(state.get("assistant_output", "") or "")
        state["final_output"] = message
        state["final_meme_image_ref"] = ""
        if not message:
            return state

        probability = float(cfg.get("meme", {}).get("send_probability", 0.25))
        if random.random() >= probability:
            return state

        image_ref = get_meme_for_emotion(
            message=message,
            config=cfg,
            picker_model=picker_model,
        )
        if image_ref:
            state["final_meme_image_ref"] = image_ref
        return state

    return RunnableLambda(_run)


def get_meme_for_emotion(
    message: str,
    config: dict[str, Any],
    picker_model: Runnable,
) -> str:
    memes = load_memes(config)
    candidates = [
        {
            "name": str(item.get("name", "") or "").strip(),
            "emotion": str(item.get("emotion", "") or "").strip(),
            "image_ref": str(item.get("image_ref", "") or "").strip(),
        }
        for item in memes.values()
        if isinstance(item, dict) and str(item.get("image_ref", "") or "").strip()
    ]
    if not candidates:
        return ""

    response = picker_model.invoke(
        [
            SystemMessage(content=MEME_PICKER_PROMPT),
            HumanMessage(
                content=json.dumps(
                    {
                        "assistant_output": message,
                        "meme_config": candidates,
                    },
                    ensure_ascii=False,
                )
            ),
        ]
    )
    payload = _parse_json(_extract_text(response))
    image_ref = str(payload.get("image_ref", "") or "").strip()
    valid_refs = {item["image_ref"] for item in candidates}
    return image_ref if image_ref in valid_refs else ""


def save_meme_reference(
    image_ref: str,
    config: dict[str, Any],
    name: str | None = None,
    emotion: str = DEFAULT_EMOTION,
) -> dict[str, str]:
    if image_ref.startswith(("http://", "https://")):
        return _save_meme_url(
            image_url=image_ref,
            config=config,
            name=name,
            emotion=emotion,
        )
    return _save_meme_image(
        image_path=image_ref,
        config=config,
        name=name,
        emotion=emotion,
    )


def load_memes(config: dict[str, Any]) -> dict[str, dict[str, str]]:
    metadata_path, _image_dir = _resolve_meme_paths(config)
    if not metadata_path.exists():
        return {}
    try:
        data = json.loads(metadata_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def write_memes(config: dict[str, Any], memes: dict[str, dict[str, str]]) -> None:
    metadata_path, _image_dir = _resolve_meme_paths(config)
    metadata_path.parent.mkdir(parents=True, exist_ok=True)
    metadata_path.write_text(
        json.dumps(memes, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _save_meme_image(
    image_path: str,
    config: dict[str, Any],
    name: str | None = None,
    emotion: str = DEFAULT_EMOTION,
) -> dict[str, str]:
    _metadata_path, image_dir = _resolve_meme_paths(config)
    image_dir.mkdir(parents=True, exist_ok=True)

    source = Path(image_path)
    if not source.exists():
        raise FileNotFoundError(f"Image file not found: {image_path}")

    suffix = source.suffix.lower()
    if suffix not in ALLOWED_EXTENSIONS:
        raise ValueError(f"Unsupported image extension: {suffix}")

    base_name = name or source.stem
    filename = _make_unique_filename(image_dir, base_name, suffix)
    destination = image_dir / filename
    shutil.copy2(source, destination)

    meme_name = _normalize_name(base_name)
    meme_entry = {
        "name": meme_name,
        "emotion": str(emotion or DEFAULT_EMOTION).strip() or DEFAULT_EMOTION,
        "image_ref": str(destination.resolve()).replace("\\", "/"),
    }

    memes = load_memes(config)
    memes[meme_name] = meme_entry
    write_memes(config, memes)
    return meme_entry


def _save_meme_url(
    image_url: str,
    config: dict[str, Any],
    name: str | None = None,
    emotion: str = DEFAULT_EMOTION,
) -> dict[str, str]:
    _metadata_path, image_dir = _resolve_meme_paths(config)
    image_dir.mkdir(parents=True, exist_ok=True)

    suffix = _guess_suffix(image_url)
    temp_name = f"download_{uuid.uuid4().hex[:8]}{suffix}"
    temp_path = image_dir / temp_name
    with httpx.Client(timeout=30.0, follow_redirects=True) as client:
        response = client.get(image_url)
        response.raise_for_status()
        temp_path.write_bytes(response.content)
    try:
        return _save_meme_image(
            image_path=str(temp_path),
            config=config,
            name=name,
            emotion=emotion,
        )
    finally:
        if temp_path.exists():
            temp_path.unlink()


def _analyze_image_emotion(
    multimodal_model: Runnable,
    image_ref: str,
    user_text: str,
) -> tuple[str, dict[str, str]]:
    image_url = _to_model_image_url(image_ref)
    if not image_url:
        return DEFAULT_EMOTION, {"source": "default", "reason": "image_url_unavailable"}

    try:
        prompt_text = user_text or "Please identify the meme emotion in one short Chinese phrase."
        response = multimodal_model.invoke(
            [
                SystemMessage(content=MEME_VISION_PROMPT),
                HumanMessage(
                    content=[
                        {"type": "text", "text": f"User text: {prompt_text}"},
                        {"type": "image_url", "image_url": {"url": image_url}},
                    ]
                ),
            ]
        )
        payload = _parse_json(_extract_text(response))
        emotion = str(payload.get("emotion", "") or "").strip()
        if emotion:
            return emotion, {"source": "multimodal", "reason": "model_json"}
    except Exception as exc:
        return DEFAULT_EMOTION, {"source": "default", "reason": f"multimodal_error:{type(exc).__name__}"}

    return DEFAULT_EMOTION, {"source": "default", "reason": "empty_multimodal_result"}


def _extract_explicit_meme_name(text: str) -> str:
    stripped = text.strip()
    if not stripped or not any(keyword in stripped for keyword in MEME_ACTION_KEYWORDS):
        return ""
    for splitter in NAME_SPLITTERS:
        if splitter not in stripped:
            continue
        value = stripped.split(splitter, 1)[1].strip()
        value = re.split(r"[\s,，。！?？；;]+", value, maxsplit=1)[0].strip()
        if value:
            return value
    return ""


def _extract_image_refs(text: str) -> list[str]:
    refs: list[str] = []
    for match in CQ_IMAGE_RE.finditer(text):
        attrs = _parse_cq_attrs(match.group(1))
        image_ref = attrs.get("url") or attrs.get("file") or ""
        if image_ref:
            refs.append(html.unescape(image_ref).strip())
    return refs


def _parse_cq_attrs(raw_attrs: str) -> dict[str, str]:
    attrs: dict[str, str] = {}
    for part in raw_attrs.split(","):
        if "=" not in part:
            continue
        key, value = part.split("=", 1)
        key = key.strip().lower()
        value = value.strip()
        if key:
            attrs[key] = value
    return attrs


def _resolve_meme_paths(config: dict[str, Any]) -> tuple[Path, Path]:
    paths_config = config.get("paths", {})
    meme_config = config.get("meme", {})
    meme_dir = project_path(paths_config.get("meme_dir", "meme"))

    metadata_value = meme_config.get("metadata_path")
    image_dir_value = meme_config.get("image_dir")

    metadata_path = project_path(metadata_value) if metadata_value else meme_dir / "memes.json"
    image_dir = project_path(image_dir_value) if image_dir_value else meme_dir / "data"
    return metadata_path, image_dir


def _to_model_image_url(image_ref: str) -> str:
    if image_ref.startswith(("http://", "https://", "data:")):
        return image_ref

    path = Path(image_ref)
    if not path.exists():
        return ""

    suffix = path.suffix.lower()
    if suffix not in ALLOWED_EXTENSIONS:
        return ""

    mime_type = mimetypes.guess_type(path.name)[0] or "image/png"
    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:{mime_type};base64,{encoded}"


def _normalize_name(name: str) -> str:
    normalized = "".join(ch.lower() if ch.isalnum() else "_" for ch in name.strip())
    normalized = "_".join(part for part in normalized.split("_") if part)
    return normalized or "meme"


def _make_unique_filename(image_dir: Path, name: str, suffix: str) -> str:
    base = _normalize_name(name)
    candidate = f"{base}{suffix}"
    counter = 1
    while (image_dir / candidate).exists():
        candidate = f"{base}_{counter}{suffix}"
        counter += 1
    return candidate


def _guess_suffix(value: str) -> str:
    lowered = value.lower()
    for suffix in ALLOWED_EXTENSIONS:
        if suffix in lowered:
            return suffix
    return ".jpg"


def _extract_text(response: Any) -> str:
    content = getattr(response, "content", "")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
                continue
            if isinstance(item, dict):
                text = item.get("text")
                if isinstance(text, str) and text.strip():
                    parts.append(text)
                    continue
                if item.get("type") == "text":
                    parts.append(str(item))
        return "\n".join(part for part in parts if part).strip()
    return str(content)


def _parse_json(text: str) -> dict[str, Any]:
    raw = text.strip()
    try:
        data = json.loads(raw)
        return data if isinstance(data, dict) else {}
    except json.JSONDecodeError:
        start = raw.find("{")
        end = raw.rfind("}")
        if start == -1 or end == -1 or end <= start:
            return {}
        try:
            data = json.loads(raw[start : end + 1])
            return data if isinstance(data, dict) else {}
        except json.JSONDecodeError:
            return {}
