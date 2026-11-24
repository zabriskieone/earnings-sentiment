import { useEffect, useState } from "react";
import { api, getEngine, openExternal, type Guide, type Settings } from "./api";
import { Icon } from "./components";

// ---------------------------------------------------------------- Guide
export function GuidePage({ guide }: { guide: Guide | null }) {
  const [q, setQ] = useState("");
  if (!guide) return <div className="page"><p className="muted">Loading…</p></div>;
  const terms = Object.entries(guide.glossary).filter(([t, d]) => !q || (t + d).toLowerCase().includes(q.toLowerCase()));
  return (
    <div className="page">
      <div className="page-head">
        <h2>Guide</h2>
        <p className="muted">New to earnings reports? Each quarter a company reports what it sold, what it kept and the cash it
          generated, and management explains the results in writing. EarningsPulse reads both: the numbers and the tone.</p>
      </div>
      <h3>Every chart, explained</h3>
      <div className="guide-grid">
        {Object.entries(guide.charts).map(([k, g]) => (
          <details key={k} className="card guide-item">
            <summary>{g.title}</summary>
            <p><b>What it shows.</b> {g.what}</p>
            <p><b>How to read it.</b> {g.read}</p>
            <p><b>What good looks like.</b> {g.good}</p>
          </details>
        ))}
      </div>
      <div className="row between"><h3>Glossary</h3>
        <div className="search small"><Icon name="search" size={15} /><input placeholder="Search terms (EPS, TTM, FinBERT…)" value={q} onChange={(e) => setQ(e.target.value)} /></div>
      </div>
      <div className="gloss">
        {terms.map(([t, d]) => <div key={t} className="card term"><b>{t}</b><span>{d}</span></div>)}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------- Settings
export function SettingsPage({ settings, onSaved, theme, setTheme }: {
  settings: Settings | null; onSaved: (s: Settings) => void; theme: Settings["theme"]; setTheme: (t: Settings["theme"]) => void;
}) {
  const [ua, setUa] = useState(settings?.sec_user_agent ?? "");
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);
  const [logFile, setLogFile] = useState("");
  useEffect(() => setUa(settings?.sec_user_agent ?? ""), [settings?.sec_user_agent]);
  useEffect(() => { getEngine().then((e) => setLogFile(e.log_file || "")); }, []);

  async function save() {
    try {
      const s = await api<Settings>("/api/settings", { method: "PUT", body: JSON.stringify({ sec_user_agent: ua }) });
      onSaved(s);
      setMsg({ ok: true, text: "Saved." });
    } catch (e: any) {
      setMsg({ ok: false, text: e.message });
    }
  }

  return (
    <div className="page narrow">
      <div className="page-head"><h2>Settings</h2></div>

      <div className="card setting">
        <h3>Your SEC identity</h3>
        <p className="muted">The SEC asks every app that downloads filings to identify itself with a name and contact e-mail
          (<button className="link-btn inline" onClick={() => openExternal("https://www.sec.gov/os/accessing-edgar-data")}>SEC policy</button>).
          It is only sent to sec.gov and stored on this Mac.</p>
        <div className="row">
          <input className="input" value={ua} placeholder="Jane Doe jane@example.com" onChange={(e) => setUa(e.target.value)} onKeyDown={(e) => e.key === "Enter" && save()} />
          <button className="btn primary" onClick={save}>Save</button>
        </div>
        {msg && <p className={msg.ok ? "ok small" : "error small"}>{msg.text}</p>}
      </div>

      <div className="card setting">
        <h3>Appearance</h3>
        <div className="segmented">
          {(["system", "light", "dark"] as const).map((t) => (
            <button key={t} className={theme === t ? "on" : ""} onClick={() => setTheme(t)}>
              <Icon name={t === "dark" ? "moon" : t === "light" ? "sun" : "settings"} size={15} /> {t[0].toUpperCase() + t.slice(1)}
            </button>
          ))}
        </div>
      </div>

      <div className="card setting">
        <h3>Storage</h3>
        <p className="muted small">Downloaded filings, models and settings live in:<br /><code>{settings?.data_dir}</code></p>
        {logFile && <p className="muted small">Engine log: <code>{logFile}</code></p>}
      </div>

      <div className="card setting">
        <h3>About</h3>
        <p className="muted small">EarningsPulse is a free, open-source hobby research tool. Automated text and ratio analysis of public
          SEC filings; not investment advice. Verify figures against the linked filings.</p>
        <button className="btn ghost" onClick={() => openExternal("https://github.com/zabriskieone/earnings-sentiment")}>
          <Icon name="external" size={14} /> Project on GitHub</button>
      </div>
    </div>
  );
}
