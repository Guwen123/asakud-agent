from __future__ import annotations

import re
from typing import Any


def run(context: dict) -> dict:
    user_input = str(context.get("user_input", "") or "").strip()
    recent_summary = str(context.get("recent_summary", "") or "").strip()

    if not user_input:
        return {"output": "缺少岗位查询任务，无法执行 Boss 直聘检索。"}

    if "fetch_web" not in set(context.get("tools", []) or []):
        return {"output": "当前 skill 未获得 fetch_web 权限，无法联网查询 Boss 直聘岗位。"}

    criteria = _parse_criteria(user_input, recent_summary)
    query = _build_query(criteria)
    result = context["run_tool"]("fetch_web", {"query": query})

    return {
        "output": _render_output(criteria, query, result),
        "query": query,
        "criteria": criteria,
    }


def _parse_criteria(user_input: str, recent_summary: str = "") -> dict:
    text = " ".join((user_input or "").split())
    combined = " ".join([text, recent_summary]).strip()

    cities = [
        "北京", "上海", "广州", "深圳", "杭州", "南京", "苏州", "成都", "重庆", "武汉", "西安", "长沙",
        "郑州", "天津", "青岛", "厦门", "合肥", "宁波", "无锡", "远程"
    ]
    city = next((c for c in cities if c in combined), "")

    job_type = ""
    for token in ["实习", "校招", "全职", "兼职", "远程", "应届"]:
        if token in combined:
            job_type = token
            break

    count = 10
    m = re.search(r"前\s*(\d+)\s*条|(?:返回|展示|列出)\s*(\d+)\s*(?:条|个|份)", combined)
    if m:
        nums = [g for g in m.groups() if g]
        if nums:
            count = max(1, min(30, int(nums[0])))

    salary = ""
    sm = re.search(r"(\d+\s*(?:/天|每天|元/天|k|K|万|以上|起))", combined)
    if sm:
        salary = sm.group(1)

    keyword = text
    cleanup_terms = ["帮我", "请", "查询", "查", "搜索", "找", "Boss直聘", "BOSS直聘", "Boss 直聘", "boss直聘", "岗位", "职位"]
    for term in cleanup_terms:
        keyword = keyword.replace(term, " ")
    if city:
        keyword = keyword.replace(city, " ")
    if salary:
        keyword = keyword.replace(salary, " ")
    keyword = " ".join(keyword.split()) or text

    return {
        "keyword": keyword,
        "city": city,
        "job_type": job_type,
        "salary": salary,
        "count": count,
        "raw_input": text,
    }


def _build_query(criteria: dict) -> str:
    parts = ["Boss 直聘"]
    if criteria.get("keyword"):
        parts.append(str(criteria["keyword"]))
    if criteria.get("city"):
        parts.append(str(criteria["city"]))
    if criteria.get("job_type"):
        parts.append(str(criteria["job_type"]))
    if criteria.get("salary"):
        parts.append(str(criteria["salary"]))
    parts.append("岗位 薪资 公司 要求")
    return " ".join(p for p in parts if p).strip()


def _render_output(criteria: dict, query: str, result: Any) -> str:
    city = criteria.get("city") or "未指定"
    job_type = criteria.get("job_type") or "未指定"
    count = criteria.get("count") or 10
    salary = criteria.get("salary") or "未指定"

    return (
        "## Boss 直聘岗位检索\n\n"
        f"- 关键词: {criteria.get('keyword') or criteria.get('raw_input')}\n"
        f"- 城市: {city}\n"
        f"- 岗位类型: {job_type}\n"
        f"- 薪资条件: {salary}\n"
        f"- 默认展示数量: 前 {count} 条左右\n"
        f"- 查询语句: {query}\n\n"
        "## 检索结果\n\n"
        f"{result}\n\n"
        "## 整理要求\n\n"
        "请基于以上检索结果整理岗位、公司、城市、薪资、要求、发布时间和链接；"
        "检索结果未显示的信息应标注为“未显示/需确认”，不要编造。"
    )
