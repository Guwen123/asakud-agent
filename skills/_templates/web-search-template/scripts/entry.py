from __future__ import annotations


def run(context: dict) -> dict:
    user_input = str(context.get("user_input", "") or "").strip()
    if not user_input:
        return {"output": "缺少用户任务，无法执行网页检索。"}

    if "fetch_web" not in set(context.get("tools", []) or []):
        return {"output": "当前 skill 未获得 fetch_web 权限，无法执行网页检索。"}

    query = _build_query(user_input)
    result = context["run_tool"]("fetch_web", {"query": query})

    return {
        "output": _render_output(query, result),
        "query": query,
    }


def _build_query(user_input: str) -> str:
    text = " ".join(user_input.split())
    return text if len(text) <= 120 else text[:120]


def _render_output(query: str, result: object) -> str:
    return (
        "## 网页检索结果\n\n"
        f"- 查询语句: {query}\n"
        "- 工具: fetch_web\n\n"
        "## 原始结果\n\n"
        f"{result}\n"
    )
