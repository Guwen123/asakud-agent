from __future__ import annotations

import datetime as dt
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from langchain_core.tools import tool

from .meme_tool import add_meme_image, choose_meme


@tool
def echo(message: str = "") -> dict[str, str]:
    """返回输入内容，用于测试 Agent 的工具调用链路。"""
    return {"message": message}


@tool
def time_now(timezone: str = "UTC") -> dict[str, str]:
    """返回指定时区的当前时间。"""
    try:
        tzinfo = ZoneInfo(timezone)
    except ZoneInfoNotFoundError:
        tzinfo = dt.timezone.utc
        timezone = "UTC"
    now = dt.datetime.now(tzinfo)
    return {"timezone": timezone, "now": now.isoformat()}


BUILTIN_TOOLS = [echo, time_now, choose_meme, add_meme_image]

