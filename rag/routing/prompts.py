from __future__ import annotations

from langchain_core.prompts import ChatPromptTemplate


QUERY_ROUTE_PROMPT = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            "你是 RAG 检索路由器。只能输出 direct 或 hybrid_rerank。"
            "direct 适合短查询、明确事实、简单关键词检索。"
            "hybrid_rerank 适合复杂问题、比较、分析、方案、长问题、需要语义召回或重排的问题。",
        ),
        ("human", "用户问题：{query}\n\n应该使用哪条检索路由？"),
    ]
)

