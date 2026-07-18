import React, { useEffect, useRef, useState } from "react";
import { createRoot } from "react-dom/client";
import "./styles.css";

const API_BASE = import.meta.env.VITE_API_BASE || "http://127.0.0.1:8000";

const navItems = ["Overview", "Skills", "Styles", "MCP Servers", "Settings", "Runtime"];
const initialMcpForm = {
  name: "my-mcp",
  base_url: "",
  transport: "mcp-jsonrpc",
  authorization: "",
};
const modelLabels = {
  main_model: "Main Model",
  route_model: "Route Model",
  multimodal_model: "Multimodal Model",
};
const emptyModelSettings = {
  main_model: emptyModelConfig(),
  route_model: emptyModelConfig(),
  multimodal_model: emptyModelConfig(),
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

function App() {
  const [status, setStatus] = useState(null);
  const [skills, setSkills] = useState([]);
  const [styles, setStyles] = useState([]);
  const [models, setModels] = useState(emptyModelSettings);
  const [modelForm, setModelForm] = useState(emptyModelSettings);
  const [mcp, setMcp] = useState({ enabled: false, servers: [] });
  const [mcpTools, setMcpTools] = useState({});
  const [mcpForm, setMcpForm] = useState(initialMcpForm);
  const [active, setActive] = useState("Overview");
  const [notice, setNotice] = useState("Connecting to Agent console...");
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
      setNotice("Agent state synchronized.");
    } catch (error) {
      setNotice(`Connection failed: ${error.message}`);
    }
  }

  useEffect(() => {
    refresh();
    const timer = window.setInterval(refresh, 8000);
    return () => window.clearInterval(timer);
  }, []);

  async function uploadPackage(kind, file) {
    if (!file) return;
    const body = new FormData();
    body.append("file", file);
    setNotice(`Installing ${kind} package: ${file.name}`);
    try {
      const response = await fetch(`${API_BASE}/api/dashboard/${kind}/upload`, {
        method: "POST",
        body,
      });
      const payload = await response.json();
      if (!response.ok) {
        throw new Error(payload.detail || "Upload failed");
      }
      setNotice(`${kind === "skills" ? "Skill" : "Style"} installed: ${file.name}`);
      await refresh();
    } catch (error) {
      setNotice(`Install failed: ${error.message}`);
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
    setNotice("Saving model settings...");
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
      setNotice("Model settings saved to agent.config.md.");
      await refresh();
    } catch (error) {
      setNotice(`Model save failed: ${error.message}`);
    }
  }

  async function addMcpServer(event) {
    event.preventDefault();
    setNotice(`Adding MCP server: ${mcpForm.name}`);
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
          ? `MCP server saved, but probe failed: ${payload.probe_error}`
          : `MCP server saved with ${payload.tools.length} tools.`
      );
      if (payload.server?.name) {
        setMcpTools((current) => ({ ...current, [payload.server.name]: payload.tools || [] }));
      }
      await refresh();
    } catch (error) {
      setNotice(`MCP save failed: ${error.message}`);
    }
  }

  async function probeMcpServer(name) {
    setNotice(`Probing MCP server: ${name}`);
    try {
      const response = await fetch(`${API_BASE}/api/dashboard/mcp/servers/${name}/tools`);
      const payload = await response.json();
      if (!response.ok || !payload.ok) {
        throw new Error(payload.error || payload.detail || "Probe failed");
      }
      setMcpTools((current) => ({ ...current, [name]: payload.tools || [] }));
      setNotice(`MCP server ${name} returned ${payload.tools.length} tools.`);
    } catch (error) {
      setNotice(`MCP probe failed: ${error.message}`);
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
            <strong>Sakuro</strong>
            <small>Agent Console</small>
          </div>
        </div>
        <nav>
          {navItems.map((item) => (
            <button key={item} className={active === item ? "active" : ""} onClick={() => setActive(item)}>
              <span>{item}</span>
              <i />
            </button>
          ))}
        </nav>
        <div className="notice">{notice}</div>
      </aside>

      <section className="content">
        <header className="topbar">
          <div>
            <p>Live Agent Control</p>
            <h1>{active}</h1>
          </div>
          <button className="refresh" onClick={refresh}>Refresh</button>
        </header>

        {active === "Settings" ? (
          <ModelSettingsPanel
            models={models}
            form={modelForm}
            onChange={updateModelField}
            onSubmit={saveModels}
          />
        ) : (
          <>
            <section className="hero-grid">
              <AgentCard agent={agent} runtime={runtime} />
              <SystemCard computer={computer} />
              <MetricCard title="CPU" value={computer.cpu?.cores || 0} unit="cores" sub={computer.cpu?.load_average?.join(" / ") || "load unavailable"} />
              <RingCard title="Memory" value={computer.memory?.percent} detail={`${computer.memory?.used_mb || 0} / ${computer.memory?.total_mb || 0} MB`} />
              <RingCard title="Disk" value={computer.disk?.percent} detail={`${computer.disk?.used_mb || 0} / ${computer.disk?.total_mb || 0} MB`} />
            </section>

            <section className="switch-row">
              <StatusTile label="Workers" active={runtime.background_workers} />
              <StatusTile label="Scheduler" active={runtime.scheduler} />
              <StatusTile label="NapCat" active={runtime.napcat} />
              <StatusTile label="Redis" active={runtime.redis} />
              <StatusTile label="MCP" active={runtime.mcp} />
            </section>

            <section className="management-grid">
              <PackagePanel
                title="Skill Library"
                subtitle="Executable task packages with SKILL.md, references, scripts, and entries."
                count={skills.length}
                items={skills}
                emptyText="No executable skills registered yet."
                onUpload={(file) => uploadPackage("skills", file)}
              />
              <PackagePanel
                title="Style Library"
                subtitle="Final response style packages. ATRI lives here, not in skills."
                count={styles.length}
                items={styles}
                emptyText="No extra styles registered yet."
                onUpload={(file) => uploadPackage("styles", file)}
              />
            </section>

            <McpPanel
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

function AgentCard({ agent, runtime }) {
  return (
    <article className="card agent-card">
      <div className="avatar">
        <div className="avatar-face" />
        <span className="online-dot" />
      </div>
      <div>
        <p>Local long-running Agent</p>
        <h2>{agent.name || "sakuro-agent"}</h2>
        <small>{agent.description || "Memory, tools, skills, and styles."}</small>
        <div className="agent-meta">
          <span>{agent.language || "zh-CN"}</span>
          <span>{Math.floor((agent.uptime_seconds || 0) / 60)} min uptime</span>
          <span>{runtime.skill_count || 0} skills</span>
          <span>{runtime.mcp_server_count || 0} MCP servers</span>
        </div>
      </div>
    </article>
  );
}

function SystemCard({ computer }) {
  return (
    <article className="card system-card">
      <h2>System</h2>
      <dl>
        <div><dt>Platform</dt><dd>{computer.platform || "Unknown"}</dd></div>
        <div><dt>Processor</dt><dd>{computer.processor || "Unknown CPU"}</dd></div>
        <div><dt>Python</dt><dd>{computer.python || "-"}</dd></div>
        <div><dt>Process</dt><dd>PID {computer.pid || "-"}</dd></div>
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

function PackagePanel({ title, subtitle, count, items, emptyText, onUpload }) {
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
        <strong>Add zip package</strong>
        <small>Drop a zip here, or click to choose a file.</small>
      </label>

      <div className="package-list">
        {items.length === 0 && <div className="empty">{emptyText}</div>}
        {items.map((item) => (
          <div className="package-item" key={item.id}>
            <div>
              <strong>{item.name || item.id}</strong>
              <small>{item.summary || item.path || "No summary yet"}</small>
            </div>
            <span>{item.entry ? "script" : item.source || item.type || "workflow"}</span>
          </div>
        ))}
      </div>
    </article>
  );
}

function McpPanel({ mcp, toolsByServer, form, setForm, onSubmit, onProbe }) {
  return (
    <article className="card mcp-panel">
      <div className="panel-head">
        <div>
          <p>Connect local or remote MCP gateways. New servers are written into agent.config.md.</p>
          <h2>MCP Servers</h2>
        </div>
        <span>{mcp.servers?.length || 0}</span>
      </div>

      <form className="mcp-form" onSubmit={onSubmit}>
        <label>
          <span>Name</span>
          <input value={form.name} onChange={(event) => setForm({ ...form, name: event.target.value })} placeholder="local" />
        </label>
        <label>
          <span>Server URL</span>
          <input value={form.base_url} onChange={(event) => setForm({ ...form, base_url: event.target.value })} placeholder="https://your-mcp-gateway.example.com/mcp" />
        </label>
        <label>
          <span>Transport</span>
          <select value={form.transport} onChange={(event) => setForm({ ...form, transport: event.target.value })}>
            <option value="mcp-jsonrpc">MCP JSON-RPC / Streamable HTTP</option>
            <option value="simple-http">Simple HTTP gateway</option>
          </select>
        </label>
        <label>
          <span>Bearer token (optional)</span>
          <input value={form.authorization} onChange={(event) => setForm({ ...form, authorization: event.target.value })} placeholder="${MCP_SERVER_TOKEN}" />
        </label>
        <button className="refresh" type="submit">Save and Load</button>
      </form>

      <div className="mcp-list">
        {(mcp.servers || []).map((server) => (
          <div className="mcp-item" key={server.name}>
            <div>
              <strong>{server.name}</strong>
              <small>{server.base_url}{server.endpoint || ""}</small>
              <em>{server.transport} · {server.enabled ? "enabled" : "disabled"} · {server.has_auth ? "auth" : "no auth"}</em>
            </div>
            <button onClick={() => onProbe(server.name)}>Probe Tools</button>
            <ToolList tools={toolsByServer[server.name] || []} />
          </div>
        ))}
      </div>
    </article>
  );
}

function ModelSettingsPanel({ models, form, onChange, onSubmit }) {
  return (
    <article className="card model-panel">
      <div className="panel-head">
        <div>
          <p>Configure the three LLM roles used by the Agent runtime.</p>
          <h2>Model Settings</h2>
        </div>
        <span>{Object.keys(modelLabels).length}</span>
      </div>

      <form className="model-form" onSubmit={onSubmit}>
        {Object.entries(modelLabels).map(([key, label]) => {
          const item = form[key] || models[key] || emptyModelConfig();
          return (
            <section className="model-card" key={key}>
              <div>
                <p>{key}</p>
                <h3>{label}</h3>
              </div>
              <label>
                <span>Provider</span>
                <input value={item.provider || ""} onChange={(event) => onChange(key, "provider", event.target.value)} placeholder="custom" />
              </label>
              <label>
                <span>Base URL</span>
                <input value={item.base_url || ""} onChange={(event) => onChange(key, "base_url", event.target.value)} placeholder="https://api.openai.com/v1" />
              </label>
              <label>
                <span>API Key</span>
                <input value={item.api_key || ""} onChange={(event) => onChange(key, "api_key", event.target.value)} placeholder="${OPENAI_API_KEY}" />
              </label>
              <label>
                <span>Model Name</span>
                <input value={item.name || ""} onChange={(event) => onChange(key, "name", event.target.value)} placeholder="gpt-4.1-mini" />
              </label>
              <label>
                <span>Temperature</span>
                <input type="number" step="0.1" value={item.temperature ?? 0} onChange={(event) => onChange(key, "temperature", Number(event.target.value))} />
              </label>
              <label>
                <span>Max Output Tokens</span>
                <input type="number" min="1" value={item.max_output_tokens || 2048} onChange={(event) => onChange(key, "max_output_tokens", Number(event.target.value))} />
              </label>
            </section>
          );
        })}
        <button className="refresh model-save" type="submit">Save Model Settings</button>
      </form>
    </article>
  );
}

function ToolList({ tools }) {
  if (!tools.length) {
    return <div className="tool-list empty">No live tool probe yet.</div>;
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
