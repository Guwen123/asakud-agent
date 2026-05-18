from __future__ import annotations

from langchain_core.tools import tool

from tools.meme import get_meme_for_text, save_meme_image


@tool
def choose_meme(message: str = "", category: str | None = None) -> dict[str, str]:
    """
    根据当前消息选择最合适的表情包。

    - message: 当前聊天内容或要回复的文本。
    - category: 可选表情包类别，例如 "happy"、"sad"、"warning"。
    """
    meme = get_meme_for_text(message, category=category)
    return meme


@tool
def add_meme_image(
    image_path: str,
    name: str | None = None,
    description: str = "",
    trigger: str = "",
    category: str | None = None,
) -> dict[str, str]:
    """
    将本地图片复制到 meme/meme 目录，并把其信息写入 memes.json。

    - image_path: 本地图片路径。
    - name: 可选名称，用于生成关键字和 metadata 名称。
    - description: 表情包说明。
    - trigger: 文本触发词。
    - category: 表情包类别。
    """
    return save_meme_image(
        image_path=image_path,
        name=name,
        description=description,
        trigger=trigger,
        category=category,
    )
