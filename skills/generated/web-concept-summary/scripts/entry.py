from __future__ import annotations

import re


def run(context: dict) -> dict:
    user_input = str(context.get("user_input", "") or "").strip()
    if not user_input:
        return {"output": "缺少用户任务，无法执行联网概念总结。"}

    if "fetch_web" not in set(context.get("tools", []) or []):
        return {"output": "当前 skill 未获得 fetch_web 权限，无法执行网页检索。"}

    topic = _extract_topic(user_input)
    sentence_count = _extract_sentence_count(user_input) or 3
    query = _build_query(topic, user_input)
    result = context["run_tool"]("fetch_web", {"query": query})

    return {
        "output": _render_output(topic, sentence_count, query, result),
        "topic": topic,
        "sentence_count": sentence_count,
        "query": query,
    }


def _extract_sentence_count(text: str) -> int | None:
    patterns = [
        (r"(\d+)\s*句", lambda m: int(m.group(1))),
        (r"一句话|一\s*句", lambda m: 1),
        (r"两句话|二\s*句|两\s*句", lambda m: 2),
        (r"三句话|三\s*句", lambda m: 3),
        (r"四句话|四\s*句", lambda m: 4),
        (r"五句话|五\s*句", lambda m: 5),
    ]
    for pattern, parser in patterns:
        match = re.search(pattern, text)
        if match:
            try:
                return max(1, min(8, parser(match)))
            except Exception:
                return None
    return None


def _extract_topic(text: str) -> str:
    cleaned = " ".join(text.replace("，", " ").replace("。", " ").replace(",", " ").split())
    remove_patterns = [
        r"^(请|麻烦|帮我|帮忙)?\s*(搜索一下|搜一下|查一下|查查|联网搜索|网上搜|搜索|查询)",
        r"然后.*$",
        r"并.*总结.*$",
        r"用.*?句.*总结.*$",
        r"总结.*$",
        r"是什么",
        r"是什麼",
        r"介绍一下",
        r"说明一下",
    ]
    topic = cleaned
    for pattern in remove_patterns:
        topic = re.sub(pattern, " ", topic, flags=re.IGNORECASE).strip()
    topic = " ".join(topic.split())
    return topic[:80] if topic else cleaned[:80]


def _build_query(topic: str, user_input: str) -> str:
    topic = topic.strip() or user_input.strip()
    query = f"{topic} 是什么 官方 文档 overview"
    return query[:120]


def _render_output(topic: str, sentence_count: int, query: str, result: object) -> str:
    return (
        "## 联网检索结果\n\n"
        f"- 主题: {topic}\n"
        f"- 查询语句: {query}\n"
        f"- 目标: 基于检索结果，用 {sentence_count} 句话中文总结。\n\n"
        "## 原始检索材料\n\n"
        f"{result}\n\n"
        "## 写作要求\n\n"
        f"- 输出严格控制为 {sentence_count} 句话。\n"
        "- 优先依据官方或权威来源。\n"
        "- 每句话表达一个核心事实，并保留必要来源线索。\n"
        "- 如果材料不足，明确说明无法确认的部分。\n"
    )
