from __future__ import annotations

from langchain_core.prompts import ChatPromptTemplate


STORAGE_ROUTER_PROMPT = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            "\n".join(
                [
                    "你是 Agent 的记忆存储路由器。",
                    "你的任务是判断一段内容是否值得长期保存，以及应该保存到哪里。",
                    "只能输出 JSON，不要输出 Markdown，不要解释。",
                    "",
                    "可选 destination：",
                    "- none：不需要保存。适合闲聊、重复内容、无价值内容、敏感密钥。",
                    "- session_memory：只进入会话数据库。适合普通对话、临时上下文、一次性命令结果。",
                    "- user_memory：写入 USER.md。适合稳定的用户偏好、协作方式、禁忌和长期目标。",
                    "- project_memory：写入 MEMORY.md。适合稳定的项目事实、环境、命令、常见修复。",
                    "- decision_memory：写入 DECISIONS.md。适合架构选择、方案取舍、长期决策原因。",
                    "- scheduled_task：写入 SCHEDULED_TASKS.md 或 scheduled_tasks 表。适合未来提醒、定时动作。",
                    "- rag：进入 RAG 离线处理。适合较长文档、知识资料、API 文档、设计说明、需要语义检索的大段内容。",
                    "",
                    "判断原则：",
                    "- 密钥、token、密码、隐私敏感内容不要长期保存，destination 用 none。",
                    "- 短小稳定事实优先存 Markdown memory。",
                    "- 长文档、参考资料、可检索知识优先存 rag。",
                    "- 临时消息只存 session_memory。",
                    "",
                    "JSON 格式：",
                    '{{"should_store": true, "destination": "project_memory", "memory_id": "project", "section": "环境", "reason": "这是稳定项目环境信息", "content": "归一化后要保存的内容"}}',
                ]
            ),
        ),
        (
            "human",
            "\n".join(
                [
                    "可用 Markdown 记忆文件：",
                    "{memory_targets}",
                    "",
                    "待判断内容：",
                    "{content}",
                    "",
                    "额外上下文：",
                    "{context}",
                ]
            ),
        ),
    ]
)

