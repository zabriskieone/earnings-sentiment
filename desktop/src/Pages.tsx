import { useEffect, useMemo, useRef, useState } from "react";
import { api, getEngine, isTauri, openExternal, pickFolder, revealFile, useDataDir, type Guide, type Settings, type Storage } from "./api";
import { Icon, fmtBytes } from "./components";

// ================================================================ Guide
const CHART_GROUPS: { id: string; title: string; icon: string; blurb: string; keys: string[] }[] = [
  { id: "financials", title: "Financial charts", icon: "analyze", blurb: "What the company sold, kept and generated.",
    keys: ["revenue", "growth", "margins", "cash", "balance"] },
  { id: "sentiment", title: "Sentiment charts", icon: "spark", blurb: "How management talks about the results.",
    keys: ["tone", "tone_sources", "lm_mdna", "risk_length"] },
  { id: "health", title: "Health charts", icon: "check", blurb: "Overall financial strength and whether it is improving.",
    keys: ["gauge", "pillars", "fscore", "health"] },
];

const TABS_EXPLAINED: [string, string][] = [
  ["Overview", "The verdict for the latest quarter: every signal in plain English, the health score, revenue and tone at a glance."],
  ["Financials", "Revenue, growth, margins, cash flow and the balance sheet, plus a quarter-by-quarter table."],
  ["Sentiment", "Tone over time, by document and method, cautious language, risk factors, and the sentences behind the scores."],
  ["Health", "The 0-100 health score, its five pillars, the Piotroski F-Score and every metric behind them."],
  ["Sources", "A link to every filing used, so any figure can be checked against the original."],
];

export function GuidePage({ guide, target, clearTarget }: { guide: Guide | null; target: string | null; clearTarget: () => void }) {
  const [q, setQ] = useState("");
  const [open, setOpen] = useState<Record<string, boolean>>({});
  const [active, setActive] = useState("start");
  const contentRef = useRef<HTMLDivElement>(null);

  // jump to a chart or section requested from elsewhere (e.g. "Open in Guide")
  useEffect(() => {
    if (!target || !guide) return;
    if (guide.charts[target]) setOpen((o) => ({ ...o, [target]: true }));
    window.setTimeout(() => {
      document.getElementById(`g-${target}`)?.scrollIntoView({ behavior: "smooth", block: "start" });
      clearTarget();
    }, 60);
  }, [target, guide, clearTarget]);

  // highlight the section in view in the table of contents
  useEffect(() => {
    const root = contentRef.current?.closest(".main");
    if (!root) return;
    const onScroll = () => {
      const ids = ["start", "dashboard", ...CHART_GROUPS.map((g) => g.id), "glossary"];
      let cur = ids[0];
      for (const id of ids) {
        const el = document.getElementById(`g-${id}`);
        if (el && el.getBoundingClientRect().top < 280) cur = id;
      }
      setActive(cur);
    };
    root.addEventListener("scroll", onScroll);
    return () => root.removeEventListener("scroll", onScroll);
  }, [guide]);

  const ql = q.trim().toLowerCase();
  const chartHit = (k: string) => {
    const g = guide?.charts[k];
    return !ql || (g && [g.title, g.what, g.read, g.good, ...(g.terms || [])].join(" ").toLowerCase().includes(ql));
  };
  const terms = useMemo(() => Object.entries(guide?.glossary ?? {})
    .filter(([t, d]) => !ql || (t + " " + d).toLowerCase().includes(ql))
    .sort(([a], [b]) => a.localeCompare(b, undefined, { sensitivity: "base" })), [guide, ql]);
  const byLetter = useMemo(() => {
    const m: Record<string, [string, string][]> = {};
    for (const [t, d] of terms) {
      const L = /[a-z]/i.test(t[0]) ? t[0].toUpperCase() : "#";
      (m[L] ||= []).push([t, d]);
    }
    return m;
  }, [terms]);

  if (!guide) return <div className="page"><p className="muted">Loading…</p></div>;
  const go = (id: string) => document.getElementById(`g-${id}`)?.scrollIntoView({ behavior: "smooth", block: "start" });
  const chartCount = CHART_GROUPS.reduce((n, g) => n + g.keys.filter(chartHit).length, 0);
  const setAll = (v: boolean) => setOpen(Object.fromEntries(Object.keys(guide.charts).map((k) => [k, v])));

  return (
    <div className="page guide-page" ref={contentRef}>
      <div className="page-head" data-tauri-drag-region>
        <h2 data-tauri-drag-region>Guide</h2>
        <p className="muted" data-tauri-drag-region>How to read every number and chart in EarningsPulse, in plain English.</p>
      </div>
      <div className="guide-layout">
        <nav className="toc card" aria-label="Guide contents">
          <div className="search small"><Icon name="search" size={15} /><input placeholder="Search the guide" value={q} onChange={(e) => setQ(e.target.value)} /></div>
          {q && <p className="muted small">{chartCount} charts · {terms.length} terms</p>}
          {!q && <button className={active === "start" ? "on" : ""} onClick={() => go("start")}><Icon name="book" size={15} /> Start here</button>}
          {!q && <button className={active === "dashboard" ? "on" : ""} onClick={() => go("dashboard")}><Icon name="analyze" size={15} /> Reading the dashboard</button>}
          {CHART_GROUPS.map((g) => (
            <button key={g.id} className={active === g.id ? "on" : ""} onClick={() => go(g.id)}><Icon name={g.icon} size={15} /> {g.title}</button>
          ))}
          <button className={active === "glossary" ? "on" : ""} onClick={() => go("glossary")}><Icon name="guide" size={15} /> Glossary A–Z</button>
        </nav>

        <div className="guide-content">
          {!q && (
            <>
              <section id="g-start" className="g-section">
                <h3>Start here</h3>
                <div className="primer">
                  {[["The numbers", "What the company sold (revenue), what it kept (margins, net income) and the cash it generated. Compare with the same quarter last year: many businesses are seasonal."],
                    ["The words", "Management explains the results in writing. The tone index measures how upbeat or cautious that language is. A change in tone can come before a change in the numbers."],
                    ["The health", "The health score (0-100) and the F-Score (0-9) summarise financial strength and whether it is improving."],
                    ["The verdict", "“What changed” lists every signal; the overall direction counts positives against negatives. Every figure links to its filing."]].map(([t, d], i) => (
                    <div key={t} className="card primer-card"><div className="n">{i + 1}</div><b>{t}</b><span>{d}</span></div>
                  ))}
                </div>
                <h4>Quick reference</h4>
                <div className="refs">
                  <div className="card ref">
                    <b>Tone index</b>
                    <div className="scale tone"><span>-1</span><div /><span>0</span><div /><span>+1</span></div>
                    <p className="muted small">Negative ← neutral → positive. Watch the change between quarters more than the level.</p>
                  </div>
                  <div className="card ref">
                    <b>Health score</b>
                    <div className="bands"><span className="b weak">0-39 Weak</span><span className="b mixed">40-54 Mixed</span><span className="b ok">55-74 Healthy</span><span className="b strong">75+ Strong</span></div>
                  </div>
                  <div className="card ref">
                    <b>Piotroski F-Score</b>
                    <div className="bands"><span className="b weak">0-3 Weak</span><span className="b mixed">4-6 Average</span><span className="b strong">7-9 Strong</span></div>
                  </div>
                </div>
              </section>

              <section id="g-dashboard" className="g-section">
                <h3>Reading the dashboard</h3>
                <div className="tab-list">
                  {TABS_EXPLAINED.map(([t, d]) => <div key={t} className="tab-row"><span className="tab-chip">{t}</span><span>{d}</span></div>)}
                </div>
              </section>
            </>
          )}

          {CHART_GROUPS.map((grp) => {
            const keys = grp.keys.filter(chartHit);
            if (!keys.length) return null;
            return (
              <section key={grp.id} id={`g-${grp.id}`} className="g-section">
                <div className="row between"><h3>{grp.title}</h3>
                  <div className="row"><button className="link-btn small" onClick={() => setAll(true)}>Expand all</button>
                    <button className="link-btn small" onClick={() => setAll(false)}>Collapse all</button></div></div>
                <p className="muted">{grp.blurb}</p>
                <div className="accordion">
                  {keys.map((k) => {
                    const g = guide.charts[k];
                    const isOpen = !!open[k] || !!ql;
                    return (
                      <div key={k} id={`g-${k}`} className={isOpen ? "acc open" : "acc"}>
                        <button className="acc-head" aria-expanded={isOpen} onClick={() => setOpen((o) => ({ ...o, [k]: !o[k] }))}>
                          <div><b>{g.title}</b><span>{g.what}</span></div>
                          <span className="chev">⌄</span>
                        </button>
                        {isOpen && (
                          <div className="acc-body">
                            <div className="acc-grid">
                              <div><h5>How to read it</h5><p>{g.read}</p></div>
                              <div><h5>What good looks like</h5><p>{g.good}</p></div>
                            </div>
                            {g.terms && g.terms.length > 0 && (
                              <div className="term-chips">
                                {g.terms.map((t) => <button key={t} className="term-chip" title={guide.glossary[t]} onClick={() => { setQ(""); window.setTimeout(() => document.getElementById(`t-${t}`)?.scrollIntoView({ behavior: "smooth", block: "center" }), 30); }}>{t}</button>)}
                              </div>
                            )}
                          </div>
                        )}
                      </div>
                    );
                  })}
                </div>
              </section>
            );
          })}

          <section id="g-glossary" className="g-section">
            <h3>Glossary A–Z</h3>
            {!q && (
              <div className="letters">
                {Object.keys(byLetter).map((L) => <button key={L} onClick={() => document.getElementById(`l-${L}`)?.scrollIntoView({ behavior: "smooth", block: "start" })}>{L}</button>)}
              </div>
            )}
            {terms.length === 0 && <p className="muted">No matching terms.</p>}
            {Object.entries(byLetter).map(([L, items]) => (
              <div key={L} id={`l-${L}`} className="letter-group">
                <div className="letter">{L}</div>
                <div className="gloss">
                  {items.map(([t, d]) => <div key={t} id={`t-${t}`} className="card term"><b>{t}</b><span>{d}</span></div>)}
                </div>
              </div>
            ))}
          </section>
        </div>
      </div>
    </div>
  );
}

// ================================================================ Settings
const EMAIL_RE = /^[^@\s]+@[^@\s]+\.[^@\s]+$/;

export function SettingsPage({ settings, onSaved, theme, setTheme, goModels }: {
  settings: Settings | null; onSaved: (s: Settings) => void; theme: Settings["theme"];
  setTheme: (t: Settings["theme"]) => void; goModels: () => void;
}) {
  const [name, setName] = useState(settings?.sec_name ?? "");
  const [email, setEmail] = useState(settings?.sec_email ?? "");
  const [touched, setTouched] = useState(false);
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);
  const [storage, setStorage] = useState<Storage | null>(null);
  const [defaultDir, setDefaultDir] = useState("");
  const [logFile, setLogFile] = useState("");
  const [busy, setBusy] = useState("");

  useEffect(() => { setName(settings?.sec_name ?? ""); setEmail(settings?.sec_email ?? ""); }, [settings?.sec_name, settings?.sec_email]);
  const loadStorage = () => api<Storage>("/api/storage").then(setStorage).catch(() => {});
  useEffect(() => {
    loadStorage();
    getEngine().then((e) => { setLogFile(e.log_file || ""); setDefaultDir(e.default_data_dir || ""); });
  }, []);

  const nameOk = name.trim().length > 1;
  const emailOk = EMAIL_RE.test(email.trim());
  const changed = name.trim() !== (settings?.sec_name ?? "") || email.trim() !== (settings?.sec_email ?? "");

  async function save() {
    setTouched(true);
    if (!nameOk || !emailOk) return;
    try {
      const s = await api<Settings>("/api/settings", { method: "PUT", body: JSON.stringify({ sec_name: name, sec_email: email }) });
      onSaved(s);
      setMsg({ ok: true, text: "Saved. You can now analyze any company." });
    } catch (e: any) {
      setMsg({ ok: false, text: e.message });
    }
  }

  async function changeLocation() {
    const folder = await pickFolder("Choose where EarningsPulse keeps filings, models and AI summaries");
    if (!folder || !storage) return;
    const total = Object.values(storage.sizes).reduce((a, b) => a + b, 0);
    if (!window.confirm(`Move ${fmtBytes(total)} of EarningsPulse data to\n${folder.replace(/\/$/, "")}/EarningsPulse ?\n\nThe app will restart when it's done.`)) return;
    setBusy("Moving your data…");
    try {
      const r = await api<{ data_dir: string }>("/api/storage/move", { method: "POST", body: JSON.stringify({ target: folder, remove_old: true }) });
      await useDataDir(r.data_dir);
      setBusy(isTauri() ? "Restarting…" : "");
      loadStorage();
    } catch (e: any) {
      setBusy("");
      setMsg({ ok: false, text: e.message });
    }
  }

  async function resetLocation() {
    if (!defaultDir || !window.confirm(`Move EarningsPulse data back to the standard location?\n${defaultDir}`)) return;
    setBusy("Moving your data…");
    try {
      const r = await api<{ data_dir: string }>("/api/storage/move", { method: "POST", body: JSON.stringify({ target: defaultDir, remove_old: true }) });
      await useDataDir(r.data_dir);
    } catch (e: any) {
      setBusy("");
      setMsg({ ok: false, text: e.message });
    }
  }

  async function clearCache() {
    if (!window.confirm("Delete downloaded filings? They are downloaded again when needed. Models and settings are kept.")) return;
    setStorage(await api<Storage>("/api/storage/clear-cache", { method: "POST" }));
  }

  const sizes = storage?.sizes;
  const total = sizes ? Object.values(sizes).reduce((a, b) => a + b, 0) : 0;
  const rows: { key: keyof Storage["sizes"]; label: string; sub: string; action?: JSX.Element }[] = [
    { key: "filings", label: "Downloaded filings", sub: "SEC filings, financial data and logos (re-downloaded when needed)",
      action: <button className="btn ghost small" onClick={clearCache} disabled={!sizes?.filings}>Clear</button> },
    { key: "models", label: "AI models", sub: "Tone models you have downloaded", action: <button className="btn ghost small" onClick={goModels}>Manage</button> },
    { key: "summaries", label: "AI summaries", sub: "Written by the local summary model (Phase 2)" },
    { key: "logs", label: "Logs", sub: "Engine log for troubleshooting" },
  ];

  return (
    <div className="page narrow">
      <div className="page-head" data-tauri-drag-region><h2 data-tauri-drag-region>Settings</h2></div>

      <div className="card setting">
        <h3>Your SEC identity</h3>
        <p className="muted">The SEC asks every app that downloads filings to identify itself
          (<button className="link-btn inline" onClick={() => openExternal("https://www.sec.gov/os/accessing-edgar-data")}>SEC policy</button>).
          This is only sent to sec.gov and stored on this Mac.</p>
        <div className="form-grid">
          <label className="form-field">
            <span>Name</span>
            <div className={`input-icon ${touched && !nameOk ? "bad" : ""}`}><Icon name="user" size={16} />
              <input value={name} placeholder="Jane Doe" autoComplete="name" onChange={(e) => { setName(e.target.value); setMsg(null); }} onBlur={() => setTouched(true)} /></div>
            {touched && !nameOk && <small className="error">Please enter your name.</small>}
          </label>
          <label className="form-field">
            <span>E-mail</span>
            <div className={`input-icon ${touched && !emailOk ? "bad" : ""}`}><Icon name="mail" size={16} />
              <input value={email} type="email" placeholder="jane@example.com" autoComplete="email" onChange={(e) => { setEmail(e.target.value); setMsg(null); }}
                onBlur={() => setTouched(true)} onKeyDown={(e) => e.key === "Enter" && save()} /></div>
            {touched && !emailOk && <small className="error">Please enter a valid e-mail address.</small>}
          </label>
        </div>
        <div className="row between form-foot">
          <span className="muted small">{nameOk && emailOk ? <>Sent to the SEC as: <code>{name.trim()} {email.trim()}</code></> : "Both fields are required."}</span>
          <button className="btn primary" onClick={save} disabled={!changed || !nameOk || !emailOk}>{settings?.sec_user_agent_valid && !changed ? "Saved" : "Save"}</button>
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
        <div className="card-head"><h3>Storage</h3><span className="muted small">{fmtBytes(total)} in total</span></div>
        <p className="muted">Filings, models and AI summaries are kept together in one folder. You can move it, for example to an external drive.</p>
        <div className="location">
          <Icon name="folder" />
          <code>{storage?.data_dir ?? settings?.data_dir}</code>
          <div className="row">
            <button className="btn ghost small" onClick={() => storage && revealFile(storage.data_dir)}>Show in Finder</button>
            <button className="btn small" onClick={changeLocation} disabled={!!busy}>Change…</button>
          </div>
        </div>
        {defaultDir && storage && storage.data_dir !== defaultDir && (
          <button className="link-btn small" onClick={resetLocation}>Move back to the standard location</button>
        )}
        {busy && <p className="muted small">{busy}</p>}
        <div className="usage">
          {rows.map((r) => (
            <div key={r.key} className="usage-row">
              <div><b>{r.label}</b><span className="muted small">{r.sub}</span></div>
              <div className="usage-bar"><div style={{ width: `${total ? Math.max(1, ((sizes?.[r.key] ?? 0) / total) * 100) : 0}%` }} /></div>
              <span className="size">{fmtBytes(sizes?.[r.key] ?? 0)}</span>
              <div className="usage-act">{r.action}</div>
            </div>
          ))}
        </div>
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
