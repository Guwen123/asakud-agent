import React, { useEffect, useState } from "react";
import { createRoot } from "react-dom/client";
import "./styles.css";

const API_BASE = import.meta.env.VITE_API_BASE || "http://127.0.0.1:8000";

const navItems = [
  "基础信息",
  "电脑状态",
  "Agent 状态",
  "Skill 管理",
  "Style 管理",
  "工具链路",
  "运行日志",
];

function App() {
  const [status, setStatus] = useState(null);
  const [skills, setSkills] = useState([]);
  const [styles, setStyles] = useState([]);
  const [active, setActive] = useState("基础信息");
  const [notice, setNotice] = useState("正在连接 Agent 控制台...");

  async function refresh() {
    try {
      const [statusRes, skillsRes, stylesRes] = await Promise.all([
        fetch(`${API_BASE}/api/dashboard/status`),
        fetch(`${API_BASE}/api/dashboard/skills`),
        fetch(`${API_BASE}/api/dashboard/styles`),
      ]);
      const statusData = await statusRes.json();
      const skillsData = await skillsRes.json();
      const stylesData = await stylesRes.json();
      setStatus(statusData);
      setSkills(skillsData.skills || []);
      setStyles(stylesData.styles || []);
      setNotice("Agent 状态已同步");
    } catch (error) {
      setNotice(`连接失败：${error.message}`);
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
    setNotice(`正在安装 ${kind} 包：${file.name}`);
    try {
      const response = await fetch(`${API_BASE}/api/dashboard/${kind}/upload`, {
        method: "POST",
        body,
      });
      const payload = await response.json();
      if (!response.ok) {
        throw new Error(payload.detail || "上传失败");
      }
      setNotice(`${kind === "skills" ? "Skill" : "Style"} 已安装：${file.name}`);
      await refresh();
    } catch (error) {
      setNotice(`安装失败：${error.message}`);
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
            <button
              key={item}
              className={active === item ? "active" : ""}
              onClick={() => setActive(item)}
            >
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
            <p>实时控制台</p>
            <h1>{active}</h1>
          </div>
          <button className="refresh" onClick={refresh}>刷新状态</button>
        </header>

        <section className="hero-grid">
          <AgentCard agent={agent} runtime={runtime} />
          <SystemCard computer={computer} />
          <MetricCard title="CPU" value={computer.cpu?.cores || 0} unit="cores" sub={computer.cpu?.load_average?.join(" / ") || "load unavailable"} />
          <RingCard title="内存占用" value={computer.memory?.percent} detail={`${computer.memory?.used_mb || 0} / ${computer.memory?.total_mb || 0} MB`} />
          <RingCard title="磁盘占用" value={computer.disk?.percent} detail={`${computer.disk?.used_mb || 0} / ${computer.disk?.total_mb || 0} MB`} />
        </section>

        <section className="switch-row">
          <StatusTile label="后台 Worker" active={runtime.background_workers} />
          <StatusTile label="调度器" active={runtime.scheduler} />
          <StatusTile label="NapCat" active={runtime.napcat} />
          <StatusTile label="Redis" active={runtime.redis} />
          <StatusTile label="Fetch Web" active={(runtime.tools || []).includes("fetch_web")} />
        </section>

        <section className="management-grid">
          <PackagePanel
            title="Skill Library"
            subtitle="可执行技能包，支持 SKILL.md / reference / scripts / entry"
            count={skills.length}
            items={skills}
            emptyText="还没有注册业务 Skill"
            onUpload={(file) => uploadPackage("skills", file)}
          />
          <PackagePanel
            title="Style Library"
            subtitle="最终语气层，可上传风格包替换回答方式"
            count={styles.length}
            items={styles}
            emptyText="还没有额外 Style"
            onUpload={(file) => uploadPackage("styles", file)}
          />
        </section>
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
        <p>点击网络配置连接服务</p>
        <h2>{agent.name || "sakuro-agent"}</h2>
        <small>{agent.description || "Local long-running memory agent"}</small>
        <div className="agent-meta">
          <span>{agent.language || "zh-CN"}</span>
          <span>{Math.floor((agent.uptime_seconds || 0) / 60)} min uptime</span>
          <span>{runtime.skill_count || 0} skills</span>
        </div>
      </div>
    </article>
  );
}

function SystemCard({ computer }) {
  return (
    <article className="card system-card">
      <h2>系统信息</h2>
      <dl>
        <div><dt>平台</dt><dd>{computer.platform || "Unknown"}</dd></div>
        <div><dt>处理器</dt><dd>{computer.processor || "Unknown CPU"}</dd></div>
        <div><dt>Python</dt><dd>{computer.python || "-"}</dd></div>
        <div><dt>进程</dt><dd>PID {computer.pid || "-"}</dd></div>
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
        <strong>添加压缩包</strong>
        <small>拖入 zip，或点击选择文件</small>
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

createRoot(document.getElementById("root")).render(<App />);
