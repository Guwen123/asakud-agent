import React, { useEffect, useRef, useState } from "react";
import { createRoot } from "react-dom/client";
import "./styles.css";

const API_BASE = import.meta.env.VITE_API_BASE || "http://127.0.0.1:8000";
const LANGUAGE_STORAGE_KEY = "asakud-dashboard-language";
const navItems = ["overview", "skills", "styles", "mcp", "settings", "runtime"];
const modelKeys = ["main_model", "route_model", "multimodal_model"];
const initialMcpForm = {
  name: "my-mcp",
  base_url: "",
  transport: "mcp-jsonrpc",
  authorization: "",
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
      skills: "Skills",
      styles: "Styles",
      mcp: "MCP Servers",
      settings: "Settings",
      runtime: "Runtime",
    },
    topbar: {
      eyebrow: "Live Agent Control",
      refresh: "Refresh",
      languageSwitch: "中文",
      languageAria: "Switch language to Chinese",
    },
    notices: {
      connecting: "Connecting to Agent console...",
      synced: "Agent state synchronized.",
      connectionFailed: (error) => `Connection failed: ${error}`,
      installing: (kind, file) => `Installing ${kind} package: ${file}`,
      installed: (kind, file) => `${kind} installed: ${file}`,
      installFailed: (error) => `Install failed: ${error}`,
      savingModels: "Saving model settings...",
      modelsSaved: "Model settings saved to agent.config.md.",
      modelSaveFailed: (error) => `Model save failed: ${error}`,
      addingMcp: (name) => `Adding MCP server: ${name}`,
      mcpSavedTools: (count) => `MCP server saved with ${count} tools.`,
      mcpSavedProbe: (error) => `MCP server saved, but probe failed: ${error}`,
      mcpSaveFailed: (error) => `MCP save failed: ${error}`,
      probingMcp: (name) => `Probing MCP server: ${name}`,
      mcpTools: (name, count) => `MCP server ${name} returned ${count} tools.`,
      mcpProbeFailed: (error) => `MCP probe failed: ${error}`,
      languageSwitched: "Language switched to English.",
    },
    kinds: { skills: "Skill", styles: "Style" },
    agent: {
      eyebrow: "Local long-running Agent",
      fallbackName: "asakud-agent",
      fallbackDesc: "Memory, tools, skills, and styles.",
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
    },
    runtimeFlags: {
      workers: "Workers",
      scheduler: "Scheduler",
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
      temperature: "Temperature",
      maxTokens: "Max Output Tokens",
    },
  },
  zh: {
    brand: { title: "asakud-agent", subtitle: "控制台" },
    nav: {
      overview: "总览",
      skills: "技能",
      styles: "风格",
      mcp: "MCP 服务",
      settings: "设置",
      runtime: "运行时",
    },
    topbar: {
      eyebrow: "实时智能体控制",
      refresh: "刷新",
      languageSwitch: "EN",
      languageAria: "切换语言为英文",
    },
    notices: {
      connecting: "正在连接智能体控制台...",
      synced: "智能体状态已同步。",
      connectionFailed: (error) => `连接失败：${error}`,
      installing: (kind, file) => `正在安装${kind}包：${file}`,
      installed: (kind, file) => `${kind}已安装：${file}`,
      installFailed: (error) => `安装失败：${error}`,
      savingModels: "正在保存模型设置...",
      modelsSaved: "模型设置已保存到 agent.config.md。",
      modelSaveFailed: (error) => `模型保存失败：${error}`,
      addingMcp: (name) => `正在添加 MCP 服务：${name}`,
      mcpSavedTools: (count) => `MCP 服务已保存，加载到 ${count} 个工具。`,
      mcpSavedProbe: (error) => `MCP 服务已保存，但探测失败：${error}`,
      mcpSaveFailed: (error) => `MCP 保存失败：${error}`,
      probingMcp: (name) => `正在探测 MCP 服务：${name}`,
      mcpTools: (name, count) => `MCP 服务 ${name} 返回 ${count} 个工具。`,
      mcpProbeFailed: (error) => `MCP 探测失败：${error}`,
      languageSwitched: "已切换为中文。",
    },
    kinds: { skills: "Skill", styles: "Style" },
    agent: {
      eyebrow: "本地长期运行智能体",
      fallbackName: "asakud-agent",
      fallbackDesc: "记忆、工具、技能和风格系统。",
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
    },
    runtimeFlags: {
      workers: "后台任务",
      scheduler: "调度器",
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
  const [mcp, setMcp] = useState({ enabled: false, servers: [] });
  const [mcpTools, setMcpTools] = useState({});
  const [mcpForm, setMcpForm] = useState(initialMcpForm);
  const [active, setActive] = useState("overview");
  const [notice, setNotice] = useState(() => I18N[getInitialLanguage()].notices.connecting);
  const modelDirtyRef = useRef(false);

  async function refresh() {
    try {
      const [statusRes, skillsRes, stylesRes, mcpRes, modelsRes] = await Promise.all([
        fetch(`${API_BASE}/api/dashboard/status`),
        fetch(`${API_BASE}/api/dashboard/skills`),
        fetch(`${API_BASE}/api/dashboard/styles`),
        fetch(`${API_BASE}/api/dashboard/mcp`),
        fetch(`${API_BASE}/api/dashboard/models`),
      ]);
      const statusData = await statusRes.json();
      const skillsData = await skillsRes.json();
      const stylesData = await stylesRes.json();
      const mcpData = await mcpRes.json();
      const modelsData = await modelsRes.json();
      setStatus(statusData);
      setSkills(skillsData.skills || []);
      setStyles(stylesData.styles || []);
      setMcp(mcpData || { enabled: false, servers: [] });
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
  }, [lang]);

  function toggleLanguage() {
    const nextLang = lang === "en" ? "zh" : "en";
    setLang(nextLang);
    setNotice(I18N[nextLang].notices.languageSwitched);
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

  const computer = status?.computer || {};
  const runtime = status?.runtime || {};
  const agent = status?.agent || {};

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

        {active === "settings" ? (
          <ModelSettingsPanel
            copy={copy}
            models={models}
            form={modelForm}
            onChange={updateModelField}
            onSubmit={saveModels}
          />
        ) : (
          <>
            <section className="hero-grid">
              <AgentCard copy={copy} agent={agent} runtime={runtime} />
              <SystemCard copy={copy} computer={computer} />
              <MetricCard
                title={copy.metrics.cpu}
                value={computer.cpu?.cores || 0}
                unit={copy.metrics.cores}
                sub={computer.cpu?.load_average?.join(" / ") || copy.metrics.loadUnavailable}
              />
              <RingCard title={copy.metrics.memory} value={computer.memory?.percent} detail={`${computer.memory?.used_mb || 0} / ${computer.memory?.total_mb || 0} MB`} />
              <RingCard title={copy.metrics.disk} value={computer.disk?.percent} detail={`${computer.disk?.used_mb || 0} / ${computer.disk?.total_mb || 0} MB`} />
            </section>

            <section className="switch-row">
              <StatusTile label={copy.runtimeFlags.workers} active={runtime.background_workers} />
              <StatusTile label={copy.runtimeFlags.scheduler} active={runtime.scheduler} />
              <StatusTile label={copy.runtimeFlags.napcat} active={runtime.napcat} />
              <StatusTile label={copy.runtimeFlags.redis} active={runtime.redis} />
              <StatusTile label={copy.runtimeFlags.mcp} active={runtime.mcp} />
            </section>

            <section className="management-grid">
              <PackagePanel
                copy={copy}
                title={copy.packages.skillTitle}
                subtitle={copy.packages.skillSubtitle}
                count={skills.length}
                items={skills}
                emptyText={copy.packages.skillEmpty}
                onUpload={(file) => uploadPackage("skills", file)}
              />
              <PackagePanel
                copy={copy}
                title={copy.packages.styleTitle}
                subtitle={copy.packages.styleSubtitle}
                count={styles.length}
                items={styles}
                emptyText={copy.packages.styleEmpty}
                onUpload={(file) => uploadPackage("styles", file)}
              />
            </section>

            <McpPanel
              copy={copy}
              mcp={mcp}
              toolsByServer={mcpTools}
              form={mcpForm}
              setForm={setMcpForm}
              onSubmit={addMcpServer}
              onProbe={probeMcpServer}
            />
          </>
        )}
      </section>
    </main>
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

function PackagePanel({ copy, title, subtitle, count, items, emptyText, onUpload }) {
  const [dragging, setDragging] = useState(false);

  function handleDrop(event) {
    event.preventDefault();
    setDragging(false);
    onUpload(event.dataTransfer.files?.[0]);
  }

  return (
    <article className="card package-panel">
      <div className="panel-head">
        <div>
          <p>{subtitle}</p>
          <h2>{title}</h2>
        </div>
        <span>{count}</span>
      </div>

      <label
        className={dragging ? "drop-zone dragging" : "drop-zone"}
        onDragOver={(event) => {
          event.preventDefault();
          setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={handleDrop}
      >
        <input type="file" accept=".zip" onChange={(event) => onUpload(event.target.files?.[0])} />
        <strong>{copy.packages.addZip}</strong>
        <small>{copy.packages.dropHint}</small>
      </label>

      <div className="package-list">
        {items.length === 0 && <div className="empty">{emptyText}</div>}
        {items.map((item) => (
          <div className="package-item" key={item.id}>
            <div>
              <strong>{item.name || item.id}</strong>
              <small>{item.summary || item.path || copy.packages.noSummary}</small>
            </div>
            <span>{item.entry ? copy.packages.script : item.source || item.type || copy.packages.workflow}</span>
          </div>
        ))}
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

function ModelSettingsPanel({ copy, models, form, onChange, onSubmit }) {
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
              <label>
                <span>{copy.models.modelName}</span>
                <input value={item.name || ""} onChange={(event) => onChange(key, "name", event.target.value)} placeholder="gpt-4.1-mini" />
              </label>
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
