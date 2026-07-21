# Skill Registry

```json
{
  "skills": [
    {
      "id": "web-concept-summary",
      "summary": "联网查询某个概念、产品或技术，并按指定句数生成简洁总结。",
      "path": "skills/generated/web-concept-summary/SKILL.md",
      "type": "workflow",
      "enabled": true,
      "entry": "scripts/entry.py:run",
      "tools": [
        "fetch_web"
      ],
      "references": [
        "reference/search_summary_rules.md"
      ],
      "max_steps": 6
    },
    {
      "id": "mcp-server-config",
      "summary": "查询并整理新增 MCP Server 的配置字段、传输方式和示例 JSON。",
      "path": "skills/generated/mcp-server-config/SKILL.md",
      "type": "workflow",
      "enabled": true,
      "entry": "scripts/entry.py:run",
      "tools": [
        "fetch_web"
      ],
      "references": [
        "reference/mcp_config_notes.md"
      ],
      "max_steps": 8
    },
    {
      "id": "boss-job-search",
      "summary": "在 Boss 直聘等网页来源查询岗位信息，并按关键词、城市、薪资等条件整理岗位列表。",
      "path": "skills/generated/boss-job-search/SKILL.md",
      "type": "workflow",
      "enabled": true,
      "entry": "scripts/entry.py:run",
      "tools": [
        "fetch_web"
      ],
      "references": [
        "reference/query_rules.md"
      ],
      "max_steps": 8
    }
  ]
}
```
