import React, { useEffect, useRef, useState } from "react";
import { createRoot } from "react-dom/client";
import "./styles.css";

const API_BASE = import.meta.env.VITE_API_BASE || "http://127.0.0.1:8000";
const LANGUAGE_STORAGE_KEY = "asakud-dashboard-language";
const navItems = ["overview", "research", "performance", "skills", "styles", "mcp", "napcat", "settings", "runtime"];
const modelKeys = ["main_model", "route_model", "multimodal_model"];
const initialMcpForm = {
  name: "my-mcp",
  base_url: "",
  transport: "mcp-jsonrpc",
  authorization: "",
};
const initialNapcatForm = {
  enabled: true,
  http_url: "http://127.0.0.1:3000",
  token: "",
  callback_path: "/getMessage",
  reply_path: "/sendMessage",
  report_format: "string",
};
const emptyModelSettings = {
  main_model: emptyModelConfig(),
  route_model: emptyModelConfig(),
  multimodal_model: emptyModelConfig(),
};

const I18N = {
  en: {
    brand: { title: "asakud-agent", subtitle: "Control Dashboard" },
    nav: {
      overview: "Overview",
      research: "Research",
      performance: "Performance",
      skills: "Skills",
      styles: "Styles",
      mcp: "MCP Servers",
      napcat: "NapCat QQ",
      settings: "Settings",
      runtime: "Runtime",
    },
    topbar: {
      eyebrow: "Live Agent Control",
      refresh: "Refresh",
      languageSwitch: "中文",
      languageAria: "Switch language to Chinese",
    },
    pages: {
      overview: "Agent, computer, and service health at a glance.",
      research: "Stored crawl dates and web research results from fetch_web.",
      researchTitle: "Web Research Records",
      researchSubtitle: "Recent fetch_web queries, crawl dates, status, and summarized results.",
      performance: "Fine-grained Agent performance traces for node execution, tool latency, and token usage.",
      performanceTitle: "Performance Monitor",
      performanceSubtitle: "Recent LangGraph runs, tool calls, and model token consumption.",
      runtime: "Focused runtime diagnostics for local services and resources.",
      runtimeTitle: "Runtime Health",
      runtimeSubtitle: "Background workers, adapters, cache, and MCP status.",
    },
    notices: {
      connecting: "Connecting to Agent console...",
      synced: "Agent state synchronized.",
      connectionFailed: (error) => `Connection failed: ${error}`,
      installing: (kind, file) => `Installing ${kind} package: ${file}`,
      installed: (kind, file) => `${kind} installed: ${file}`,
      installFailed: (error) => `Install failed: ${error}`,
      togglingPackage: (kind, name, state) => `${state} ${kind}: ${name}`,
      packageToggled: (kind, name, state) => `${kind} ${name} is now ${state}.`,
      packageToggleFailed: (error) => `Toggle failed: ${error}`,
      savingModels: "Saving model settings...",
      modelsSaved: "Model settings saved to agent.config.md.",
      modelSaveFailed: (error) => `Model save failed: ${error}`,
      discoveringModels: (key) => `Fetching model list for ${key}...`,
      modelsDiscovered: (key, count) => `${count} models loaded for ${key}.`,
      modelDiscoverFailed: (error) => `Model discovery failed: ${error}`,
      savingNapcat: "Saving NapCat QQ settings...",
      napcatSaved: "NapCat QQ settings saved to agent.config.md.",
      napcatSaveFailed: (error) => `NapCat save failed: ${error}`,
      addingMcp: (name) => `Adding MCP server: ${name}`,
      mcpSavedTools: (count) => `MCP server saved with ${count} tools.`,
      mcpSavedProbe: (error) => `MCP server saved, but probe failed: ${error}`,
      mcpSaveFailed: (error) => `MCP save failed: ${error}`,
      probingMcp: (name) => `Probing MCP server: ${name}`,
      mcpTools: (name, count) => `MCP server ${name} returned ${count} tools.`,
      mcpProbeFailed: (error) => `MCP probe failed: ${error}`,
      languageSwitched: "Language switched to English.",
      deletingCrawl: "Deleting crawl record...",
      crawlDeleted: "Crawl record deleted.",
      crawlDeleteFailed: (error) => `Delete failed: ${error}`,
    },
    kinds: { skills: "Skill", styles: "Style" },
    agent: {
      eyebrow: "Web Research Agent",
      fallbackName: "asakud-agent",
      fallbackDesc: "Search, browse, extract, summarize, and monitor public web information.",
      uptime: (minutes) => `${minutes} min uptime`,
      skills: (count) => `${count} skills`,
      mcpServers: (count) => `${count} MCP servers`,
    },
    system: {
      title: "System",
      platform: "Platform",
      processor: "Processor",
      python: "Python",
      process: "Process",
      unknown: "Unknown",
      unknownCpu: "Unknown CPU",
    },
    metrics: {
      cpu: "CPU",
      cores: "cores",
      loadUnavailable: "load unavailable",
      memory: "Memory",
      disk: "Disk",
      traces: "Traces",
      avgRun: "Avg Run",
      avgNode: "Avg Node",
      avgTool: "Avg Tool",
      tokens: "Tokens",
      estimatedTokens: "Estimated",
      slowestNode: "Slowest Node",
      slowestTool: "Slowest Tool",
    },
    performance: {
      empty: "No Agent traces yet. Send a message to generate runtime metrics.",
      nodes: "Node timings",
      tools: "Tool latency",
      models: "Model calls",
      noTools: "No tools were called in this trace.",
      noModels: "No model usage was recorded.",
      actual: "actual",
      estimated: "estimated",
      input: "input",
      output: "output",
      total: "total",
      ok: "ok",
      failed: "failed",
    },
    research: {
      empty: "No crawl records yet. Ask the Agent to search the web to create one.",
      query: "Query",
      result: "Result",
      date: "Crawl date",
      status: "Status",
      ok: "ok",
      failed: "failed",
      delete: "Delete",
      expand: "Expand full result",
      collapse: "Collapse result",
      previous: "Previous",
      next: "Next",
      pageInfo: (page, totalPages, total) => `Page ${page} / ${totalPages} · ${total} records`,
      count: (count) => `${count} crawls`,
    },
    runtimeFlags: {
      workers: "Workers",
      napcat: "NapCat",
      redis: "Redis",
      mcp: "MCP",
    },
    packages: {
      skillTitle: "Skill Library",
      skillSubtitle: "Executable task packages with SKILL.md, references, scripts, and entries.",
      skillEmpty: "No executable skills registered yet.",
      styleTitle: "Style Library",
      styleSubtitle: "Final response style packages. ATRI lives here, not in skills.",
      styleEmpty: "No extra styles registered yet.",
      addZip: "Add zip package",
      dropHint: "Drop a zip here, or click to choose a file.",
      noSummary: "No summary yet",
      script: "script",
      workflow: "workflow",
      enabled: "enabled",
      disabled: "disabled",
      enable: "Enable",
      disable: "Disable",
    },
    napcat: {
      subtitle: "Connect a NapCat-compatible QQ HTTP server for callbacks and replies.",
      title: "NapCat QQ",
      enabled: "Enable NapCat",
      httpUrl: "HTTP server URL",
      token: "Access token (optional)",
      callbackPath: "Callback path",
      replyPath: "Reply path",
      reportFormat: "Report format",
      save: "Save NapCat",
      formats: {
        string: "String messages",
        array: "Array/CQ segments",
      },
    },
    mcp: {
      subtitle: "Connect local or remote MCP gateways. New servers are written into agent.config.md.",
      title: "MCP Servers",
      name: "Name",
      serverUrl: "Server URL",
      transport: "Transport",
      token: "Bearer token (optional)",
      save: "Save and Load",
      probe: "Probe Tools",
      enabled: "enabled",
      disabled: "disabled",
      auth: "auth",
      noAuth: "no auth",
      noProbe: "No live tool probe yet.",
      transports: {
        jsonrpc: "MCP JSON-RPC / Streamable HTTP",
        simple: "Simple HTTP gateway",
      },
    },
    models: {
      subtitle: "Configure the three LLM roles used by the Agent runtime.",
      title: "Model Settings",
      save: "Save Model Settings",
      keys: {
        main_model: "Main Model",
        route_model: "Route Model",
        multimodal_model: "Multimodal Model",
      },
      provider: "Provider",
      baseUrl: "Base URL",
      apiKey: "API Key",
      modelName: "Model Name",
      discover: "Get Models",
      discovering: "Loading...",
      selectPlaceholder: "Select a model",
      noModels: "Click Get Models first",
      temperature: "Temperature",
      maxTokens: "Max Output Tokens",
    },
  },
  zh: {
    brand: { title: "asakud-agent", subtitle: "控制台" },
    nav: {
      overview: "总览",
      research: "网页记录",
      performance: "性能监控",
      skills: "技能",
      styles: "风格",
      mcp: "MCP 服务",
      napcat: "NapCat QQ",
      settings: "设置",
      runtime: "运行时",
    },
    topbar: {
      eyebrow: "实时智能体控制",
      refresh: "刷新",
      languageSwitch: "EN",
      languageAria: "切换语言为英文",
    },
    pages: {
      overview: "快速查看智能体、电脑资源和服务健康状态。",
      research: "查看 fetch_web 保存的爬取日期和网页研究结果。",
      researchTitle: "网页研究记录",
      researchSubtitle: "最近的 fetch_web 查询、爬取日期、状态和结果摘要。",
      performance: "细粒度查看节点执行时长、工具调用延迟和 Token 消耗。",
      performanceTitle: "性能监控",
      performanceSubtitle: "最近的 LangGraph 运行、工具调用和模型 Token 消耗。",
      runtime: "聚焦本地服务与系统资源的运行诊断。",
      runtimeTitle: "运行健康",
      runtimeSubtitle: "后台任务、适配器、缓存和 MCP 状态。",
    },
    notices: {
      connecting: "正在连接智能体控制台...",
      synced: "智能体状态已同步。",
      connectionFailed: (error) => `连接失败：${error}`,
      installing: (kind, file) => `正在安装${kind}包：${file}`,
      installed: (kind, file) => `${kind}已安装：${file}`,
      installFailed: (error) => `安装失败：${error}`,
      togglingPackage: (kind, name, state) => `正在${state}${kind}：${name}`,
      packageToggled: (kind, name, state) => `${kind} ${name} 现在是${state}。`,
      packageToggleFailed: (error) => `切换失败：${error}`,
      savingModels: "正在保存模型设置...",
      modelsSaved: "模型设置已保存到 agent.config.md。",
      modelSaveFailed: (error) => `模型保存失败：${error}`,
      discoveringModels: (key) => `正在获取 ${key} 的模型列表...`,
      modelsDiscovered: (key, count) => `${key} 已加载 ${count} 个模型。`,
      modelDiscoverFailed: (error) => `模型发现失败：${error}`,
      savingNapcat: "正在保存 NapCat QQ 设置...",
      napcatSaved: "NapCat QQ 设置已保存到 agent.config.md。",
      napcatSaveFailed: (error) => `NapCat 保存失败：${error}`,
      addingMcp: (name) => `正在添加 MCP 服务：${name}`,
      mcpSavedTools: (count) => `MCP 服务已保存，加载到 ${count} 个工具。`,
      mcpSavedProbe: (error) => `MCP 服务已保存，但探测失败：${error}`,
      mcpSaveFailed: (error) => `MCP 保存失败：${error}`,
      probingMcp: (name) => `正在探测 MCP 服务：${name}`,
      mcpTools: (name, count) => `MCP 服务 ${name} 返回 ${count} 个工具。`,
      mcpProbeFailed: (error) => `MCP 探测失败：${error}`,
      languageSwitched: "已切换为中文。",
      deletingCrawl: "正在删除爬取记录...",
      crawlDeleted: "爬取记录已删除。",
      crawlDeleteFailed: (error) => `删除失败：${error}`,
    },
    kinds: { skills: "Skill", styles: "Style" },
    agent: {
      eyebrow: "网页研究智能体",
      fallbackName: "asakud-agent",
      fallbackDesc: "面向公开网页的搜索、浏览、提取、汇总与监控。",
      uptime: (minutes) => `已运行 ${minutes} 分钟`,
      skills: (count) => `${count} 个技能`,
      mcpServers: (count) => `${count} 个 MCP 服务`,
    },
    system: {
      title: "系统",
      platform: "平台",
      processor: "处理器",
      python: "Python",
      process: "进程",
      unknown: "未知",
      unknownCpu: "未知 CPU",
    },
    metrics: {
      cpu: "CPU",
      cores: "核",
      loadUnavailable: "负载不可用",
      memory: "内存",
      disk: "磁盘",
      traces: "Trace",
      avgRun: "平均运行",
      avgNode: "平均节点",
      avgTool: "平均工具",
      tokens: "Token",
      estimatedTokens: "估算",
      slowestNode: "最慢节点",
      slowestTool: "最慢工具",
    },
    performance: {
      empty: "还没有 Agent 运行记录。发送一条消息后会生成性能指标。",
      nodes: "节点耗时",
      tools: "工具延迟",
      models: "模型调用",
      noTools: "本次 trace 没有调用工具。",
      noModels: "本次 trace 没有记录模型用量。",
      actual: "实际",
      estimated: "估算",
      input: "输入",
      output: "输出",
      total: "总量",
      ok: "成功",
      failed: "失败",
    },
    research: {
      empty: "还没有爬取记录。让 Agent 搜索网页后会在这里生成记录。",
      query: "查询",
      result: "结果",
      date: "爬取日期",
      status: "状态",
      ok: "成功",
      failed: "失败",
      delete: "删除",
      expand: "展开完整结果",
      collapse: "收起结果",
      previous: "上一页",
      next: "下一页",
      pageInfo: (page, totalPages, total) => `第 ${page} / ${totalPages} 页 · 共 ${total} 条`,
      count: (count) => `${count} 条记录`,
    },
    runtimeFlags: {
      workers: "后台任务",
      napcat: "NapCat",
      redis: "Redis",
      mcp: "MCP",
    },
    packages: {
      skillTitle: "Skill 库",
      skillSubtitle: "包含 SKILL.md、references、scripts 和 entry 的可执行任务包。",
      skillEmpty: "还没有注册可执行 Skill。",
      styleTitle: "Style 库",
      styleSubtitle: "最终回复风格包。ATRI 在这里，而不是在 skills 中。",
      styleEmpty: "还没有额外 Style。",
      addZip: "添加 zip 包",
      dropHint: "把 zip 拖到这里，或点击选择文件。",
      noSummary: "暂无摘要",
      script: "脚本",
      workflow: "流程",
      enabled: "已启用",
      disabled: "已禁用",
      enable: "启用",
      disable: "禁用",
    },
    napcat: {
      subtitle: "连接兼容 NapCat 的 QQ HTTP 服务，用于接收回调和发送回复。",
      title: "NapCat QQ",
      enabled: "启用 NapCat",
      httpUrl: "HTTP 服务地址",
      token: "访问 Token（可选）",
      callbackPath: "回调路径",
      replyPath: "回复路径",
      reportFormat: "上报格式",
      save: "保存 NapCat",
      formats: {
        string: "字符串消息",
        array: "数组 / CQ 段",
      },
    },
    mcp: {
      subtitle: "连接本地或远程 MCP 网关。新服务会写入 agent.config.md。",
      title: "MCP 服务",
      name: "名称",
      serverUrl: "服务地址",
      transport: "传输方式",
      token: "Bearer token（可选）",
      save: "保存并加载",
      probe: "探测工具",
      enabled: "已启用",
      disabled: "已禁用",
      auth: "有鉴权",
      noAuth: "无鉴权",
      noProbe: "还没有实时工具探测结果。",
      transports: {
        jsonrpc: "MCP JSON-RPC / Streamable HTTP",
        simple: "Simple HTTP 网关",
      },
    },
    models: {
      subtitle: "配置智能体运行时使用的三个 LLM 角色。",
      title: "模型设置",
      save: "保存模型设置",
      keys: {
        main_model: "主模型",
        route_model: "路由模型",
        multimodal_model: "多模态模型",
      },
      provider: "服务商",
      baseUrl: "Base URL",
      apiKey: "API Key",
      modelName: "模型名称",
      discover: "获取模型",
      discovering: "加载中...",
      selectPlaceholder: "选择模型",
      noModels: "请先点击获取模型",
      temperature: "温度",
      maxTokens: "最大输出 Token",
    },
  },
};

function emptyModelConfig() {
  return {
    provider: "custom",
    protocol: "openai-compatible",
    base_url: "",
    api_key: "",
    name: "",
    temperature: 0,
    max_output_tokens: 2048,
  };
}

function getInitialLanguage() {
  if (typeof window === "undefined") return "en";
  const stored = window.localStorage.getItem(LANGUAGE_STORAGE_KEY);
  return stored === "zh" ? "zh" : "en";
}

function App() {
  const [lang, setLang] = useState(getInitialLanguage);
  const copy = I18N[lang];
  const [status, setStatus] = useState(null);
  const [skills, setSkills] = useState([]);
  const [styles, setStyles] = useState([]);
  const [models, setModels] = useState(emptyModelSettings);
  const [modelForm, setModelForm] = useState(emptyModelSettings);
  const [modelOptions, setModelOptions] = useState({});
  const [modelLoading, setModelLoading] = useState({});
  const [napcat, setNapcat] = useState(initialNapcatForm);
  const [napcatForm, setNapcatForm] = useState(initialNapcatForm);
  const [mcp, setMcp] = useState({ enabled: false, servers: [] });
  const [mcpTools, setMcpTools] = useState({});
  const [mcpForm, setMcpForm] = useState(initialMcpForm);
  const [performance, setPerformance] = useState({ summary: {}, traces: [] });
  const [crawls, setCrawls] = useState([]);
  const [crawlMeta, setCrawlMeta] = useState({ page: 1, limit: 10, total: 0, total_pages: 1 });
  const [crawlPage, setCrawlPage] = useState(1);
  const [active, setActive] = useState("overview");
  const [notice, setNotice] = useState(() => I18N[getInitialLanguage()].notices.connecting);
  const modelDirtyRef = useRef(false);
  const napcatDirtyRef = useRef(false);

  async function refresh() {
    try {
      const [statusRes, skillsRes, stylesRes, mcpRes, napcatRes, modelsRes, performanceRes, crawlsRes] = await Promise.all([
        fetch(`${API_BASE}/api/dashboard/status`),
        fetch(`${API_BASE}/api/dashboard/skills`),
        fetch(`${API_BASE}/api/dashboard/styles`),
        fetch(`${API_BASE}/api/dashboard/mcp`),
        fetch(`${API_BASE}/api/dashboard/napcat`),
        fetch(`${API_BASE}/api/dashboard/models`),
        fetch(`${API_BASE}/api/dashboard/performance?limit=10`),
        fetch(`${API_BASE}/api/dashboard/crawls?limit=10&page=${crawlPage}`),
      ]);
      const statusData = await statusRes.json();
      const skillsData = await skillsRes.json();
      const stylesData = await stylesRes.json();
      const mcpData = await mcpRes.json();
      const napcatData = await napcatRes.json();
      const modelsData = await modelsRes.json();
      const performanceData = await performanceRes.json();
      const crawlsData = await crawlsRes.json();
      setStatus(statusData);
      setSkills(skillsData.skills || []);
      setStyles(stylesData.styles || []);
      setMcp(mcpData || { enabled: false, servers: [] });
      setPerformance(performanceData || { summary: {}, traces: [] });
      setCrawls(crawlsData.crawls || []);
      setCrawlMeta({
        page: crawlsData.page || crawlPage,
        limit: crawlsData.limit || 10,
        total: crawlsData.total || 0,
        total_pages: crawlsData.total_pages || 1,
      });
      setNapcat(napcatData.napcat || initialNapcatForm);
      if (!napcatDirtyRef.current) {
        setNapcatForm(napcatData.napcat || initialNapcatForm);
      }
      setModels(modelsData.models || emptyModelSettings);
      if (!modelDirtyRef.current) {
        setModelForm(modelsData.models || emptyModelSettings);
      }
      setNotice(copy.notices.synced);
    } catch (error) {
      setNotice(copy.notices.connectionFailed(error.message));
    }
  }

  useEffect(() => {
    window.localStorage.setItem(LANGUAGE_STORAGE_KEY, lang);
    refresh();
    const timer = window.setInterval(refresh, 8000);
    return () => window.clearInterval(timer);
  }, [lang, crawlPage]);

  function toggleLanguage() {
    const nextLang = lang === "en" ? "zh" : "en";
    setLang(nextLang);
    setNotice(I18N[nextLang].notices.languageSwitched);
  }

  function noticeMessage(key, ...args) {
    const value = copy.notices[key] || I18N.en.notices[key];
    return typeof value === "function" ? value(...args) : value;
  }

  async function uploadPackage(kind, file) {
    if (!file) return;
    const body = new FormData();
    body.append("file", file);
    const kindLabel = copy.kinds[kind] || kind;
    setNotice(copy.notices.installing(kindLabel, file.name));
    try {
      const response = await fetch(`${API_BASE}/api/dashboard/${kind}/upload`, {
        method: "POST",
        body,
      });
      const payload = await response.json();
      if (!response.ok) {
        throw new Error(payload.detail || "Upload failed");
      }
      setNotice(copy.notices.installed(kindLabel, file.name));
      await refresh();
    } catch (error) {
      setNotice(copy.notices.installFailed(error.message));
    }
  }

  async function togglePackageEnabled(kind, item) {
    const id = item?.id || "";
    if (!id) return;
    const kindLabel = copy.kinds[kind] || kind;
    const name = item.name || id;
    const nextEnabled = item.enabled === false;
    const actionLabel = nextEnabled ? copy.packages.enable : copy.packages.disable;
    const stateLabel = nextEnabled ? copy.packages.enabled : copy.packages.disabled;
    setNotice(copy.notices.togglingPackage(kindLabel, name, actionLabel));
    try {
      const response = await fetch(`${API_BASE}/api/dashboard/${kind}/${encodeURIComponent(id)}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ enabled: nextEnabled }),
      });
      const payload = await response.json();
      if (!response.ok || !payload.ok) {
        throw new Error(payload.detail || "Toggle failed");
      }
      setNotice(copy.notices.packageToggled(kindLabel, name, stateLabel));
      await refresh();
    } catch (error) {
      setNotice(copy.notices.packageToggleFailed(error.message));
    }
  }

  function updateModelField(modelKey, field, value) {
    modelDirtyRef.current = true;
    setModelForm((current) => ({
      ...current,
      [modelKey]: {
        ...(current[modelKey] || emptyModelConfig()),
        [field]: value,
      },
    }));
  }

  async function discoverModels(modelKey) {
    const item = modelForm[modelKey] || emptyModelConfig();
    setNotice(noticeMessage("discoveringModels", copy.models.keys[modelKey] || modelKey));
    setModelLoading((current) => ({ ...current, [modelKey]: true }));
    try {
      const response = await fetch(`${API_BASE}/api/dashboard/models/discover`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          provider: item.provider || "custom",
          protocol: item.protocol || "openai-compatible",
          base_url: item.base_url || "",
          api_key: item.api_key || "",
        }),
      });
      const payload = await response.json();
      if (!response.ok || !payload.ok) {
        throw new Error(payload.detail || "Failed to fetch model list");
      }
      const nextOptions = Array.isArray(payload.models) ? payload.models : [];
      setModelOptions((current) => ({ ...current, [modelKey]: nextOptions }));
      if (!item.name && nextOptions.length) {
        updateModelField(modelKey, "name", nextOptions[0]);
      }
      setNotice(noticeMessage("modelsDiscovered", copy.models.keys[modelKey] || modelKey, nextOptions.length));
    } catch (error) {
      setNotice(noticeMessage("modelDiscoverFailed", error.message));
    } finally {
      setModelLoading((current) => ({ ...current, [modelKey]: false }));
    }
  }

  function updateNapcatForm(nextForm) {
    napcatDirtyRef.current = true;
    setNapcatForm(nextForm);
  }

  async function saveNapcat(event) {
    event.preventDefault();
    setNotice(copy.notices.savingNapcat);
    try {
      const response = await fetch(`${API_BASE}/api/dashboard/napcat`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(napcatForm),
      });
      const payload = await response.json();
      if (!response.ok || !payload.ok) {
        throw new Error(payload.detail || "Failed to save NapCat settings");
      }
      setNapcat(payload.napcat || napcatForm);
      setNapcatForm(payload.napcat || napcatForm);
      napcatDirtyRef.current = false;
      setNotice(copy.notices.napcatSaved);
      await refresh();
    } catch (error) {
      setNotice(copy.notices.napcatSaveFailed(error.message));
    }
  }

  async function saveModels(event) {
    event.preventDefault();
    setNotice(copy.notices.savingModels);
    try {
      const response = await fetch(`${API_BASE}/api/dashboard/models`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(modelForm),
      });
      const payload = await response.json();
      if (!response.ok || !payload.ok) {
        throw new Error(payload.detail || "Failed to save model settings");
      }
      setModels(payload.models || modelForm);
      setModelForm(payload.models || modelForm);
      modelDirtyRef.current = false;
      setNotice(copy.notices.modelsSaved);
      await refresh();
    } catch (error) {
      setNotice(copy.notices.modelSaveFailed(error.message));
    }
  }

  async function addMcpServer(event) {
    event.preventDefault();
    setNotice(copy.notices.addingMcp(mcpForm.name));
    try {
      const response = await fetch(`${API_BASE}/api/dashboard/mcp/servers`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          ...mcpForm,
          enabled: true,
          timeout_seconds: 5,
        }),
      });
      const payload = await response.json();
      if (!response.ok) {
        throw new Error(payload.detail || "Failed to add MCP server");
      }
      setNotice(
        payload.probe_error
          ? copy.notices.mcpSavedProbe(payload.probe_error)
          : copy.notices.mcpSavedTools(payload.tools.length)
      );
      if (payload.server?.name) {
        setMcpTools((current) => ({ ...current, [payload.server.name]: payload.tools || [] }));
      }
      await refresh();
    } catch (error) {
      setNotice(copy.notices.mcpSaveFailed(error.message));
    }
  }

  async function probeMcpServer(name) {
    setNotice(copy.notices.probingMcp(name));
    try {
      const response = await fetch(`${API_BASE}/api/dashboard/mcp/servers/${name}/tools`);
      const payload = await response.json();
      if (!response.ok || !payload.ok) {
        throw new Error(payload.error || payload.detail || "Probe failed");
      }
      setMcpTools((current) => ({ ...current, [name]: payload.tools || [] }));
      setNotice(copy.notices.mcpTools(name, payload.tools.length));
    } catch (error) {
      setNotice(copy.notices.mcpProbeFailed(error.message));
    }
  }

  async function deleteCrawlRecord(item) {
    const id = item?.id || "";
    if (!id) return;
    setNotice(copy.notices.deletingCrawl);
    try {
      const response = await fetch(`${API_BASE}/api/dashboard/crawls/${encodeURIComponent(id)}`, {
        method: "DELETE",
      });
      const payload = await response.json();
      if (!response.ok || !payload.ok) {
        throw new Error(payload.detail || "Delete failed");
      }
      setNotice(copy.notices.crawlDeleted);
      if (crawls.length <= 1 && crawlPage > 1) {
        setCrawlPage((page) => Math.max(1, page - 1));
      } else {
        await refresh();
      }
    } catch (error) {
      setNotice(copy.notices.crawlDeleteFailed(error.message));
    }
  }

  const computer = status?.computer || {};
  const runtime = status?.runtime || {};
  const agent = status?.agent || {};

  function renderActivePanel() {
    switch (active) {
      case "skills":
        return (
          <PackagePanel
            copy={copy}
            title={copy.packages.skillTitle}
            subtitle={copy.packages.skillSubtitle}
            count={skills.length}
            items={skills}
            emptyText={copy.packages.skillEmpty}
            onUpload={(file) => uploadPackage("skills", file)}
            onToggle={(item) => togglePackageEnabled("skills", item)}
          />
        );
      case "styles":
        return (
          <PackagePanel
            copy={copy}
            title={copy.packages.styleTitle}
            subtitle={copy.packages.styleSubtitle}
            count={styles.length}
            items={styles}
            emptyText={copy.packages.styleEmpty}
            onUpload={(file) => uploadPackage("styles", file)}
            onToggle={(item) => togglePackageEnabled("styles", item)}
          />
        );
      case "mcp":
        return (
          <McpPanel
            copy={copy}
            mcp={mcp}
            toolsByServer={mcpTools}
            form={mcpForm}
            setForm={setMcpForm}
            onSubmit={addMcpServer}
            onProbe={probeMcpServer}
          />
        );
      case "napcat":
        return (
          <NapcatPanel
            copy={copy}
            napcat={napcat}
            form={napcatForm}
            setForm={updateNapcatForm}
            onSubmit={saveNapcat}
          />
        );
      case "settings":
        return (
          <ModelSettingsPanel
            copy={copy}
            models={models}
            form={modelForm}
            modelOptions={modelOptions}
            modelLoading={modelLoading}
            onChange={updateModelField}
            onDiscover={discoverModels}
            onSubmit={saveModels}
          />
        );
      case "research":
        return (
          <ResearchPanel
            copy={copy}
            crawls={crawls}
            meta={crawlMeta}
            onDelete={deleteCrawlRecord}
            onPageChange={setCrawlPage}
          />
        );
      case "performance":
        return <PerformancePanel copy={copy} performance={performance} />;
      case "runtime":
        return <RuntimePanel copy={copy} computer={computer} runtime={runtime} />;
      case "overview":
      default:
        return <OverviewPanel copy={copy} agent={agent} computer={computer} runtime={runtime} />;
    }
  }

  return (
    <main className="shell">
      <aside className="sidebar">
        <div className="brand">
          <span className="brand-mark" />
          <div>
            <strong>{copy.brand.title}</strong>
            <small>{copy.brand.subtitle}</small>
          </div>
        </div>
        <nav>
          {navItems.map((item) => (
            <button key={item} className={active === item ? "active" : ""} onClick={() => setActive(item)}>
              <span>{copy.nav[item]}</span>
              <i />
            </button>
          ))}
        </nav>
        <div className="notice">{notice}</div>
      </aside>

      <section className="content">
        <header className="topbar">
          <div>
            <p>{copy.topbar.eyebrow}</p>
            <h1>{copy.nav[active]}</h1>
          </div>
          <div className="top-actions">
            <button className="language-toggle" type="button" onClick={toggleLanguage} aria-label={copy.topbar.languageAria}>
              {copy.topbar.languageSwitch}
            </button>
            <button className="refresh" type="button" onClick={refresh}>{copy.topbar.refresh}</button>
          </div>
        </header>

        {renderActivePanel()}
      </section>
    </main>
  );
}

function OverviewPanel({ copy, agent, computer, runtime }) {
  return (
    <div className="page-stack">
      <p className="page-intro">{copy.pages.overview}</p>
      <section className="hero-grid">
        <AgentCard copy={copy} agent={agent} runtime={runtime} />
        <SystemCard copy={copy} computer={computer} />
        <MetricCard
          title={copy.metrics.cpu}
          value={computer.cpu?.cores || 0}
          unit={copy.metrics.cores}
          sub={computer.cpu?.load_average?.join(" / ") || copy.metrics.loadUnavailable}
        />
        <RingCard
          title={copy.metrics.memory}
          value={computer.memory?.percent}
          detail={`${computer.memory?.used_mb || 0} / ${computer.memory?.total_mb || 0} MB`}
        />
        <RingCard
          title={copy.metrics.disk}
          value={computer.disk?.percent}
          detail={`${computer.disk?.used_mb || 0} / ${computer.disk?.total_mb || 0} MB`}
        />
      </section>
      <RuntimeFlags copy={copy} runtime={runtime} />
    </div>
  );
}

function ResearchPanel({ copy, crawls, meta, onDelete, onPageChange }) {
  const items = Array.isArray(crawls) ? crawls : [];
  const [expanded, setExpanded] = useState({});
  const page = Number(meta?.page || 1);
  const totalPages = Number(meta?.total_pages || 1);
  const total = Number(meta?.total || items.length);

  function toggleExpanded(id) {
    setExpanded((current) => ({ ...current, [id]: !current[id] }));
  }

  return (
    <div className="page-stack">
      <p className="page-intro">{copy.pages.research}</p>
      <article className="card research-card">
        <div className="panel-head">
          <div>
            <p>{copy.pages.researchSubtitle}</p>
            <h2>{copy.pages.researchTitle}</h2>
          </div>
          <span>{copy.research.count(total)}</span>
        </div>
      </article>
      <section className="crawl-list">
        {items.length === 0 && <div className="empty">{copy.research.empty}</div>}
        {items.map((item) => {
          const fullText = String(item.ok === false ? item.error : item.result || "");
          const isExpanded = Boolean(expanded[item.id]);
          const isLong = fullText.length > 700;
          const displayText = isExpanded || !isLong ? fullText : shortText(fullText, 700);
          return (
            <article className={`card crawl-card ${item.ok === false ? "failed" : ""}`} key={item.id}>
              <div className="crawl-head">
                <div>
                  <small>{copy.research.query}</small>
                  <strong>{item.query || "-"}</strong>
                </div>
                <div className="crawl-actions">
                  <button type="button" onClick={() => onDelete(item)}>{copy.research.delete}</button>
                </div>
              </div>
              <div className="crawl-meta">
                <span>{copy.research.date}: {formatDateTime(item.created_at)}</span>
                <em className={item.ok === false ? "failed" : "ok"}>
                  {copy.research.status}: {item.ok === false ? copy.research.failed : copy.research.ok}
                </em>
              </div>
              <div className="crawl-result">
                <small>{copy.research.result}</small>
                <p className={isExpanded ? "expanded" : ""}>{displayText || "-"}</p>
                {isLong && (
                  <button className="text-toggle" type="button" onClick={() => toggleExpanded(item.id)}>
                    {isExpanded ? copy.research.collapse : copy.research.expand}
                  </button>
                )}
              </div>
            </article>
          );
        })}
      </section>
      <div className="pagination-bar">
        <button type="button" disabled={page <= 1} onClick={() => onPageChange(Math.max(1, page - 1))}>
          {copy.research.previous}
        </button>
        <span>{copy.research.pageInfo(page, totalPages, total)}</span>
        <button type="button" disabled={page >= totalPages} onClick={() => onPageChange(Math.min(totalPages, page + 1))}>
          {copy.research.next}
        </button>
      </div>
    </div>
  );
}

function PerformancePanel({ copy, performance }) {
  const summary = performance?.summary || {};
  const traces = performance?.traces || [];
  const slowestNode = summary.slowest_node || {};
  const slowestTool = summary.slowest_tool || {};
  const totalTokens = Number(summary.total_tokens || 0);
  const estimatedTokens = Number(summary.estimated_total_tokens || 0);

  return (
    <div className="page-stack">
      <p className="page-intro">{copy.pages.performance}</p>
      <article className="card performance-card">
        <div className="panel-head">
          <div>
            <p>{copy.pages.performanceSubtitle}</p>
            <h2>{copy.pages.performanceTitle}</h2>
          </div>
          <span>{summary.trace_count || 0}</span>
        </div>
        <section className="perf-summary-grid">
          <PerfStat title={copy.metrics.traces} value={summary.trace_count || 0} unit="" />
          <PerfStat title={copy.metrics.avgRun} value={formatMs(summary.avg_total_duration_ms)} unit="ms" />
          <PerfStat title={copy.metrics.avgNode} value={formatMs(summary.avg_node_duration_ms)} unit="ms" />
          <PerfStat title={copy.metrics.avgTool} value={formatMs(summary.avg_tool_latency_ms)} unit="ms" />
          <PerfStat title={copy.metrics.tokens} value={totalTokens || estimatedTokens} unit={totalTokens ? copy.performance.actual : copy.performance.estimated} />
        </section>
        <section className="bottleneck-grid">
          <BottleneckCard title={copy.metrics.slowestNode} item={slowestNode} />
          <BottleneckCard title={copy.metrics.slowestTool} item={slowestTool} />
        </section>
      </article>

      <section className="trace-list">
        {traces.length === 0 && <div className="empty">{copy.performance.empty}</div>}
        {traces.map((trace) => (
          <TraceCard key={trace.trace_id} copy={copy} trace={trace} />
        ))}
      </section>
    </div>
  );
}

function PerfStat({ title, value, unit }) {
  return (
    <article className="perf-stat">
      <p>{title}</p>
      <strong>{value}</strong>
      {unit && <small>{unit}</small>}
    </article>
  );
}

function BottleneckCard({ title, item }) {
  const name = item?.name || "-";
  const duration = item?.duration_ms != null ? `${formatMs(item.duration_ms)} ms` : "-";
  return (
    <article className="bottleneck-card">
      <p>{title}</p>
      <strong>{name}</strong>
      <small>{duration}</small>
    </article>
  );
}

function TraceCard({ copy, trace }) {
  const tokens = trace.tokens || {};
  const actualTotal = Number(tokens.total_tokens || 0);
  const estimatedTotal = Number(tokens.estimated_total_tokens || 0);
  const displayTotal = actualTotal || estimatedTotal;

  return (
    <article className="card trace-card">
      <div className="trace-head">
        <div>
          <strong>{shortTraceId(trace.trace_id)}</strong>
          <small>{trace.started_at || "-"}</small>
        </div>
        <div className="trace-pills">
          <span>{formatMs(trace.total_duration_ms)} ms</span>
          <span>{trace.node_count || 0} nodes</span>
          <span>{trace.tool_count || 0} tools</span>
          <span>{displayTotal} tokens</span>
        </div>
      </div>

      <div className="token-row">
        <span>{copy.performance.actual}: {copy.performance.input} {tokens.input_tokens || 0} / {copy.performance.output} {tokens.output_tokens || 0} / {copy.performance.total} {tokens.total_tokens || 0}</span>
        <span>{copy.performance.estimated}: {copy.performance.input} {tokens.estimated_input_tokens || 0} / {copy.performance.output} {tokens.estimated_output_tokens || 0} / {copy.performance.total} {tokens.estimated_total_tokens || 0}</span>
      </div>

      <TraceSection title={copy.performance.nodes} items={trace.nodes || []} emptyText="-" />
      <TraceSection title={copy.performance.tools} items={trace.tools || []} emptyText={copy.performance.noTools} copy={copy} />
      <ModelCallSection title={copy.performance.models} calls={trace.model_calls || []} emptyText={copy.performance.noModels} />
    </article>
  );
}

function TraceSection({ title, items, emptyText, copy }) {
  return (
    <section className="trace-section">
      <h3>{title}</h3>
      {items.length === 0 && <small>{emptyText}</small>}
      <div className="timing-list">
        {items.map((item, index) => (
          <div className="timing-item" key={`${item.name}-${index}`}>
            <span>{item.name || "-"}</span>
            <strong>{formatMs(item.duration_ms)} ms</strong>
            {copy && <em className={item.ok === false ? "failed" : "ok"}>{item.ok === false ? copy.performance.failed : copy.performance.ok}</em>}
          </div>
        ))}
      </div>
    </section>
  );
}

function ModelCallSection({ title, calls, emptyText }) {
  return (
    <section className="trace-section">
      <h3>{title}</h3>
      {calls.length === 0 && <small>{emptyText}</small>}
      <div className="timing-list">
        {calls.map((item, index) => (
          <div className="timing-item model-call" key={`${item.model_key}-${index}`}>
            <span>{item.model_key || "model"}</span>
            <strong>{formatMs(item.duration_ms)} ms</strong>
            <em>{item.total_tokens || item.estimated_total_tokens || 0} tokens</em>
          </div>
        ))}
      </div>
    </section>
  );
}

function formatMs(value) {
  const number = Number(value || 0);
  if (!Number.isFinite(number)) return "0";
  if (number >= 1000) return number.toFixed(0);
  return number.toFixed(1);
}

function shortTraceId(value) {
  const text = String(value || "");
  return text ? `trace-${text.slice(0, 8)}` : "trace";
}

function formatDateTime(value) {
  if (!value) return "-";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return String(value);
  return date.toLocaleString();
}

function shortText(value, limit = 900) {
  const text = String(value || "").replace(/\s+/g, " ").trim();
  if (text.length <= limit) return text;
  return `${text.slice(0, Math.max(0, limit - 3)).trim()}...`;
}

function RuntimePanel({ copy, computer, runtime }) {
  const activeCount = [
    runtime.background_workers,
    runtime.napcat,
    runtime.redis,
    runtime.mcp,
  ].filter(Boolean).length;

  return (
    <div className="page-stack">
      <p className="page-intro">{copy.pages.runtime}</p>
      <article className="card runtime-card">
        <div className="panel-head">
          <div>
            <p>{copy.pages.runtimeSubtitle}</p>
            <h2>{copy.pages.runtimeTitle}</h2>
          </div>
          <span>{activeCount}/4</span>
        </div>
        <RuntimeFlags copy={copy} runtime={runtime} compact />
      </article>
      <section className="runtime-grid">
        <SystemCard copy={copy} computer={computer} />
        <MetricCard
          title={copy.metrics.cpu}
          value={computer.cpu?.cores || 0}
          unit={copy.metrics.cores}
          sub={computer.cpu?.load_average?.join(" / ") || copy.metrics.loadUnavailable}
        />
        <RingCard
          title={copy.metrics.memory}
          value={computer.memory?.percent}
          detail={`${computer.memory?.used_mb || 0} / ${computer.memory?.total_mb || 0} MB`}
        />
        <RingCard
          title={copy.metrics.disk}
          value={computer.disk?.percent}
          detail={`${computer.disk?.used_mb || 0} / ${computer.disk?.total_mb || 0} MB`}
        />
      </section>
    </div>
  );
}

function RuntimeFlags({ copy, runtime, compact = false }) {
  return (
    <section className={compact ? "switch-row compact" : "switch-row"}>
      <StatusTile label={copy.runtimeFlags.workers} active={runtime.background_workers} />
      <StatusTile label={copy.runtimeFlags.napcat} active={runtime.napcat} />
      <StatusTile label={copy.runtimeFlags.redis} active={runtime.redis} />
      <StatusTile label={copy.runtimeFlags.mcp} active={runtime.mcp} />
    </section>
  );
}

function AgentCard({ copy, agent, runtime }) {
  return (
    <article className="card agent-card">
      <div className="avatar">
        <div className="avatar-face" />
        <span className="online-dot" />
      </div>
      <div>
        <p>{copy.agent.eyebrow}</p>
        <h2>{agent.name || copy.agent.fallbackName}</h2>
        <small>{agent.description || copy.agent.fallbackDesc}</small>
        <div className="agent-meta">
          <span>{agent.language || "zh-CN"}</span>
          <span>{copy.agent.uptime(Math.floor((agent.uptime_seconds || 0) / 60))}</span>
          <span>{copy.agent.skills(runtime.skill_count || 0)}</span>
          <span>{copy.agent.mcpServers(runtime.mcp_server_count || 0)}</span>
        </div>
      </div>
    </article>
  );
}

function SystemCard({ copy, computer }) {
  return (
    <article className="card system-card">
      <h2>{copy.system.title}</h2>
      <dl>
        <div><dt>{copy.system.platform}</dt><dd>{computer.platform || copy.system.unknown}</dd></div>
        <div><dt>{copy.system.processor}</dt><dd>{computer.processor || copy.system.unknownCpu}</dd></div>
        <div><dt>{copy.system.python}</dt><dd>{computer.python || "-"}</dd></div>
        <div><dt>{copy.system.process}</dt><dd>PID {computer.pid || "-"}</dd></div>
      </dl>
    </article>
  );
}

function MetricCard({ title, value, unit, sub }) {
  return (
    <article className="card metric-card">
      <span className="metric-icon" />
      <p>{title}</p>
      <strong>{value}<small>{unit}</small></strong>
      <em>{sub}</em>
    </article>
  );
}

function RingCard({ title, value, detail }) {
  const percent = Number.isFinite(value) ? value : 0;
  return (
    <article className="card ring-card">
      <div className="ring" style={{ "--value": `${percent * 3.6}deg` }}>
        <span>{Math.round(percent)}%</span>
      </div>
      <div>
        <p>{title}</p>
        <small>{detail}</small>
      </div>
    </article>
  );
}

function StatusTile({ label, active }) {
  return (
    <article className={active ? "status-tile on" : "status-tile"}>
      <strong>{active ? "1" : "0"}</strong>
      <span>{label}</span>
    </article>
  );
}

function PackagePanel({ copy, title, subtitle, count, items, emptyText, onUpload, onToggle }) {
  const fileInputRef = useRef(null);

  return (
    <article className="card package-panel">
      <div className="panel-head">
        <div>
          <p>{subtitle}</p>
          <h2>{title}</h2>
        </div>
        <div className="panel-actions">
          <span>{count}</span>
          <button className="upload-button" type="button" onClick={() => fileInputRef.current?.click()}>
            {copy.packages.addZip}
          </button>
          <input
            ref={fileInputRef}
            type="file"
            accept=".zip"
            onChange={(event) => {
              onUpload(event.target.files?.[0]);
              event.target.value = "";
            }}
          />
        </div>
      </div>

      <div className="package-list">
        {items.length === 0 && <div className="empty">{emptyText}</div>}
        {items.map((item) => {
          const enabled = item.enabled !== false;
          return (
            <div className={enabled ? "package-item" : "package-item disabled"} key={item.id}>
              <div>
                <strong>{item.name || item.id}</strong>
                <small>{item.summary || item.path || copy.packages.noSummary}</small>
              </div>
              <div className="package-actions">
                <span>{item.entry ? copy.packages.script : item.source || item.type || copy.packages.workflow}</span>
                <em className={enabled ? "package-state on" : "package-state"}>{enabled ? copy.packages.enabled : copy.packages.disabled}</em>
                <button type="button" onClick={() => onToggle?.(item)}>
                  {enabled ? copy.packages.disable : copy.packages.enable}
                </button>
              </div>
            </div>
          );
        })}
      </div>
    </article>
  );
}

function McpPanel({ copy, mcp, toolsByServer, form, setForm, onSubmit, onProbe }) {
  return (
    <article className="card mcp-panel">
      <div className="panel-head">
        <div>
          <p>{copy.mcp.subtitle}</p>
          <h2>{copy.mcp.title}</h2>
        </div>
        <span>{mcp.servers?.length || 0}</span>
      </div>

      <form className="mcp-form" onSubmit={onSubmit}>
        <label>
          <span>{copy.mcp.name}</span>
          <input value={form.name} onChange={(event) => setForm({ ...form, name: event.target.value })} placeholder="local" />
        </label>
        <label>
          <span>{copy.mcp.serverUrl}</span>
          <input value={form.base_url} onChange={(event) => setForm({ ...form, base_url: event.target.value })} placeholder="https://your-mcp-gateway.example.com/mcp" />
        </label>
        <label>
          <span>{copy.mcp.transport}</span>
          <select value={form.transport} onChange={(event) => setForm({ ...form, transport: event.target.value })}>
            <option value="mcp-jsonrpc">{copy.mcp.transports.jsonrpc}</option>
            <option value="simple-http">{copy.mcp.transports.simple}</option>
          </select>
        </label>
        <label>
          <span>{copy.mcp.token}</span>
          <input value={form.authorization} onChange={(event) => setForm({ ...form, authorization: event.target.value })} placeholder="${MCP_SERVER_TOKEN}" />
        </label>
        <button className="refresh" type="submit">{copy.mcp.save}</button>
      </form>

      <div className="mcp-list">
        {(mcp.servers || []).map((server) => (
          <div className="mcp-item" key={server.name}>
            <div>
              <strong>{server.name}</strong>
              <small>{server.base_url}{server.endpoint || ""}</small>
              <em>{server.transport} / {server.enabled ? copy.mcp.enabled : copy.mcp.disabled} / {server.has_auth ? copy.mcp.auth : copy.mcp.noAuth}</em>
            </div>
            <button type="button" onClick={() => onProbe(server.name)}>{copy.mcp.probe}</button>
            <ToolList copy={copy} tools={toolsByServer[server.name] || []} />
          </div>
        ))}
      </div>
    </article>
  );
}

function NapcatPanel({ copy, napcat, form, setForm, onSubmit }) {
  const enabled = form.enabled !== false;
  return (
    <article className="card napcat-panel">
      <div className="panel-head">
        <div>
          <p>{copy.napcat.subtitle}</p>
          <h2>{copy.napcat.title}</h2>
        </div>
        <span>{napcat.enabled ? copy.packages.enabled : copy.packages.disabled}</span>
      </div>

      <form className="napcat-form" onSubmit={onSubmit}>
        <label className="toggle-field">
          <input type="checkbox" checked={enabled} onChange={(event) => setForm({ ...form, enabled: event.target.checked })} />
          <span>{copy.napcat.enabled}</span>
        </label>
        <label>
          <span>{copy.napcat.httpUrl}</span>
          <input value={form.http_url || ""} onChange={(event) => setForm({ ...form, http_url: event.target.value })} placeholder="http://127.0.0.1:3000" />
        </label>
        <label>
          <span>{copy.napcat.token}</span>
          <input value={form.token || ""} onChange={(event) => setForm({ ...form, token: event.target.value })} placeholder="optional token" />
        </label>
        <label>
          <span>{copy.napcat.callbackPath}</span>
          <input value={form.callback_path || ""} onChange={(event) => setForm({ ...form, callback_path: event.target.value })} placeholder="/getMessage" />
        </label>
        <label>
          <span>{copy.napcat.replyPath}</span>
          <input value={form.reply_path || ""} onChange={(event) => setForm({ ...form, reply_path: event.target.value })} placeholder="/sendMessage" />
        </label>
        <label>
          <span>{copy.napcat.reportFormat}</span>
          <select value={form.report_format || "string"} onChange={(event) => setForm({ ...form, report_format: event.target.value })}>
            <option value="string">{copy.napcat.formats.string}</option>
            <option value="array">{copy.napcat.formats.array}</option>
          </select>
        </label>
        <button className="refresh model-save" type="submit">{copy.napcat.save}</button>
      </form>
    </article>
  );
}

function ModelSettingsPanel({ copy, models, form, modelOptions, modelLoading, onChange, onDiscover, onSubmit }) {
  return (
    <article className="card model-panel">
      <div className="panel-head">
        <div>
          <p>{copy.models.subtitle}</p>
          <h2>{copy.models.title}</h2>
        </div>
        <span>{modelKeys.length}</span>
      </div>

      <form className="model-form" onSubmit={onSubmit}>
        {modelKeys.map((key) => {
          const item = form[key] || models[key] || emptyModelConfig();
          const rawOptions = modelOptions[key] || [];
          const options = item.name && !rawOptions.includes(item.name) ? [item.name, ...rawOptions] : rawOptions;
          const isLoading = Boolean(modelLoading[key]);
          return (
            <section className="model-card" key={key}>
              <div>
                <p>{key}</p>
                <h3>{copy.models.keys[key]}</h3>
              </div>
              <label>
                <span>{copy.models.provider}</span>
                <input value={item.provider || ""} onChange={(event) => onChange(key, "provider", event.target.value)} placeholder="custom" />
              </label>
              <label>
                <span>{copy.models.baseUrl}</span>
                <input value={item.base_url || ""} onChange={(event) => onChange(key, "base_url", event.target.value)} placeholder="https://api.openai.com/v1" />
              </label>
              <label>
                <span>{copy.models.apiKey}</span>
                <input value={item.api_key || ""} onChange={(event) => onChange(key, "api_key", event.target.value)} placeholder="your-api-key" />
              </label>
              <div className="model-select-row">
                <label>
                  <span>{copy.models.modelName}</span>
                  <select value={item.name || ""} onChange={(event) => onChange(key, "name", event.target.value)}>
                    <option value="">{options.length ? (copy.models.selectPlaceholder || I18N.en.models.selectPlaceholder) : (copy.models.noModels || I18N.en.models.noModels)}</option>
                    {options.map((name) => (
                      <option key={name} value={name}>{name}</option>
                    ))}
                  </select>
                </label>
                <button className="model-discover" type="button" onClick={() => onDiscover(key)} disabled={isLoading}>
                  {isLoading ? (copy.models.discovering || I18N.en.models.discovering) : (copy.models.discover || I18N.en.models.discover)}
                </button>
              </div>
              <label>
                <span>{copy.models.temperature}</span>
                <input type="number" step="0.1" value={item.temperature ?? 0} onChange={(event) => onChange(key, "temperature", Number(event.target.value))} />
              </label>
              <label>
                <span>{copy.models.maxTokens}</span>
                <input type="number" min="1" value={item.max_output_tokens || 2048} onChange={(event) => onChange(key, "max_output_tokens", Number(event.target.value))} />
              </label>
            </section>
          );
        })}
        <button className="refresh model-save" type="submit">{copy.models.save}</button>
      </form>
    </article>
  );
}

function ToolList({ copy, tools }) {
  if (!tools.length) {
    return <div className="tool-list empty">{copy.mcp.noProbe}</div>;
  }
  return (
    <div className="tool-list">
      {tools.map((tool) => (
        <span key={tool.name} title={tool.description || ""}>{tool.name}</span>
      ))}
    </div>
  );
}

createRoot(document.getElementById("root")).render(<App />);
