import { useEffect, useMemo, useRef, useState } from "react";
import { api, openExternal, revealFile, isTauri, getEngine, type Company, type Guide, type JobStatus, type ModelsResponse, type Result } from "./api";
import { ChartCard, CompanyLogo, Icon, Sparkline } from "./components";

type Props = { theme: "light" | "dark"; guide: Guide | null; secOk: boolean; goSettings: () => void; goModels: () => void };

const TABS = ["Overview", "Financials", "Sentiment", "Health", "Sources"] as const;
type Tab = (typeof TABS)[number];

export default function Analyze({ theme, guide, secOk, goSettings, goModels }: Props) {
  const [query, setQuery] = useState("AAPL");
  const [picked, setPicked] = useState<Company | null>({ ticker: "AAPL", name: "Apple Inc.", cik: "0000320193" });
  const [matches, setMatches] = useState<Company[]>([]);
  const [showList, setShowList] = useState(false);
  const [quarters, setQuarters] = useState(8);
  const [models, setModels] = useState<ModelsResponse | null>(null);
  const [modelChoice, setModelChoice] = useState<string>("active");
  const [job, setJob] = useState<JobStatus | null>(null);
  const [error, setError] = useState("");
  const [results, setResults] = useState<Record<string, Result>>({});
  const [jobId, setJobId] = useState<string | null>(null);
  const [tab, setTab] = useState<Tab>("Overview");
  const [toast, setToast] = useState<{ text: string; path?: string } | null>(null);
  const searchTimer = useRef<number>();

  useEffect(() => {
    api<ModelsResponse>("/api/models").then(setModels).catch(() => {});
  }, []);

  // company search (debounced)
  useEffect(() => {
    if (!secOk || !showList) return;
    window.clearTimeout(searchTimer.current);
    searchTimer.current = window.setTimeout(() => {
      api<Company[]>(`/api/companies?q=${encodeURIComponent(query)}&limit=8`).then(setMatches).catch(() => setMatches([]));
    }, 150);
  }, [query, secOk, showList]);

  // result for the current theme (charts are styled per theme by the engine)
  const result = jobId ? results[`${jobId}:${theme}`] : undefined;
  useEffect(() => {
    if (!jobId || job?.status !== "done" || results[`${jobId}:${theme}`]) return;
    api<Result>(`/api/analyses/${jobId}/result?theme=${theme}`)
      .then((r) => setResults((m) => ({ ...m, [`${jobId}:${theme}`]: r })))
      .catch((e) => setError(String(e.message || e)));
  }, [jobId, job?.status, theme, results]);

  async function run() {
    if (!picked) return;
    setError("");
    setTab("Overview");
    try {
      const body = { ticker: picked.ticker, quarters, model_id: modelChoice === "active" ? null : modelChoice };
      const { job_id } = await api<{ job_id: string }>("/api/analyses", { method: "POST", body: JSON.stringify(body) });
      setJobId(job_id);
      setJob({ job_id, status: "running", progress: 0, message: "Starting", error: "" });
      for (;;) {
        await new Promise((r) => setTimeout(r, 450));
        const st = await api<JobStatus>(`/api/analyses/${job_id}`);
        setJob(st);
        if (st.status !== "running") {
          if (st.status === "error") setError(st.error);
          break;
        }
      }
    } catch (e: any) {
      setError(e.message || String(e));
      setJob(null);
    }
  }

  async function exportReport(kind: "pdf" | "html" | "csv") {
    if (!jobId) return;
    if (!isTauri()) {
      const e = await getEngine();
      const r = await fetch(`${e.url}/api/analyses/${jobId}/report.${kind === "csv" ? "csv" : kind}`.replace("report.csv", "data.csv"), { headers: { "X-EP-Token": e.token } });
      const url = URL.createObjectURL(await r.blob());
      const a = document.createElement("a");
      a.href = url;
      a.download = `${result?.company.ticker}_${kind === "csv" ? "quarters.csv" : "report." + kind}`;
      a.click();
      return;
    }
    try {
      const { path } = await api<{ path: string }>(`/api/analyses/${jobId}/export?kind=${kind}`, { method: "POST" });
      setToast({ text: `Saved to Downloads: ${path.split("/").pop()}`, path });
      window.setTimeout(() => setToast(null), 6000);
    } catch (e: any) {
      setError(e.message);
    }
  }

  const running = job?.status === "running";
  const installed = models?.models.filter((m) => m.installed) ?? [];

  return (
    <div className="page">
      {/* ------------------------------------------------ search bar */}
      <div className="toolbar card">
        <div className="search">
          <Icon name="search" />
          <input
            value={query}
            placeholder="Search a company or ticker (e.g. Apple, MSFT)"
            onChange={(e) => { setQuery(e.target.value); setPicked(null); setShowList(true); }}
            onFocus={() => setShowList(true)}
            onBlur={() => window.setTimeout(() => setShowList(false), 150)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && matches[0] && !picked) { setPicked(matches[0]); setQuery(`${matches[0].ticker}`); setShowList(false); }
              else if (e.key === "Enter" && picked) run();
            }}
            disabled={!secOk}
          />
          {picked && <span className="picked">{picked.name}</span>}
          {showList && matches.length > 0 && (
            <ul className="suggest">
              {matches.map((c) => (
                <li key={c.ticker} onMouseDown={() => { setPicked(c); setQuery(c.ticker); setShowList(false); }}>
                  <b>{c.ticker}</b> <span>{c.name}</span>
                </li>
              ))}
            </ul>
          )}
        </div>
        <label className="field">
          <span>Quarters</span>
          <select value={quarters} onChange={(e) => setQuarters(Number(e.target.value))}>
            {[4, 6, 8, 10, 12].map((n) => <option key={n} value={n}>{n}</option>)}
          </select>
        </label>
        <label className="field">
          <span>Tone model</span>
          <select value={modelChoice} onChange={(e) => setModelChoice(e.target.value)}>
            <option value="active">{models?.active ? `${models.active_name} (default)` : "Dictionary only"}</option>
            {installed.filter((m) => !m.active).map((m) => <option key={m.id} value={m.id}>{m.name}</option>)}
            <option value="dictionary">Dictionary only</option>
          </select>
        </label>
        <button className="btn primary" onClick={run} disabled={!picked || running || !secOk}>
          {running ? "Analysing…" : "Analyse"}
        </button>
      </div>

      {!secOk && (
        <div className="notice card">
          <Icon name="help" /> <span>The SEC asks every app that downloads filings for a name and e-mail.</span>
          <button className="btn" onClick={goSettings}>Add it in Settings</button>
        </div>
      )}
      {secOk && models && !models.active && (
        <div className="notice card subtle">
          <Icon name="spark" /> <span>Tone is scored with the finance dictionary. Download an AI model for sentence-level scoring.</span>
          <button className="btn" onClick={goModels}>Browse models</button>
        </div>
      )}

      {running && job && (
        <div className="card progress-card">
          <div className="progress-head"><span>{job.message}</span><span>{Math.round(job.progress * 100)}%</span></div>
          <div className="bar"><div style={{ width: `${Math.max(3, job.progress * 100)}%` }} /></div>
        </div>
      )}
      {error && <div className="card error"><b>Something went wrong.</b> {error}</div>}

      {!result && !running && !error && <Welcome />}
      {result && <Dashboard r={result} tab={tab} setTab={setTab} guide={guide} onExport={exportReport} />}

      {toast && (
        <div className="toast">
          <Icon name="check" /> {toast.text}
          {toast.path && <button className="link-btn" onClick={() => revealFile(toast.path!)}>Show in Finder</button>}
        </div>
      )}
    </div>
  );
}

function Welcome() {
  const steps = [
    ["Read the filings", "Downloads each 10-Q / 10-K and the earnings press release from SEC EDGAR."],
    ["Score the tone", "Rates management's language with a finance dictionary and an AI model running on your Mac."],
    ["Compare the numbers", "Compares each quarter with the previous one and the same quarter last year."],
    ["Rate the health", "A transparent five-pillar scorecard plus the Piotroski F-Score."],
  ];
  return (
    <div className="welcome">
      <div className="hero">
        <h1>Sentiment &amp; health from every quarterly result</h1>
        <p>Search any company that files with the US SEC, then press Analyse. Everything runs on your Mac; every figure links back to its filing.</p>
      </div>
      <div className="steps">
        {steps.map(([t, d], i) => (
          <div key={t} className="card step"><div className="n">{i + 1}</div><b>{t}</b><span>{d}</span></div>
        ))}
      </div>
    </div>
  );
}

function Dashboard({ r, tab, setTab, guide, onExport }: { r: Result; tab: Tab; setTab: (t: Tab) => void; guide: Guide | null; onExport: (k: "pdf" | "html" | "csv") => void }) {
  const c = r.charts;
  const [evQ, setEvQ] = useState(r.evidence[0]?.quarter);
  const ev = useMemo(() => r.evidence.find((e) => e.quarter === evQ) ?? r.evidence[0], [r, evQ]);
  return (
    <>
      <div className="hero company">
        <CompanyLogo ticker={r.company.ticker} size={64} />
        <div>
          <h1>{r.company.name} <span className="ticker">{r.company.ticker}</span></h1>
          <p>Latest quarter <b>{r.latest.label}</b> · period ended {r.latest.period_end} · {r.latest.form} filed {r.latest.filed}</p>
          <div className="chips">
            <span className="chip">{r.quarters} quarters</span>
            <span className="chip">Tone: {r.method.model_name}</span>
            <span className="chip strong">Overall: {r.verdict.label}</span>
          </div>
        </div>
      </div>

      <div className="kpis">
        {r.kpis.map((k) => (
          <div key={k.name} className="card kpi" title={k.help}>
            <div className="kpi-name">{k.name}</div>
            <div className="kpi-value">{k.value}</div>
            {k.delta && <div className={`kpi-delta ${k.delta.startsWith("-") ? "down" : k.delta.startsWith("+") ? "up" : ""}`}>{k.delta}</div>}
            <Sparkline values={r.sparks[k.name] || []} />
          </div>
        ))}
      </div>

      <div className="row between">
        <div className="tabs" role="tablist">
          {TABS.map((t) => <button key={t} role="tab" aria-selected={tab === t} className={tab === t ? "tab on" : "tab"} onClick={() => setTab(t)}>{t}</button>)}
        </div>
        <div className="exports">
          <button className="btn ghost" onClick={() => onExport("pdf")}><Icon name="download" size={15} /> PDF</button>
          <button className="btn ghost" onClick={() => onExport("html")}><Icon name="download" size={15} /> HTML</button>
          <button className="btn ghost" onClick={() => onExport("csv")}><Icon name="download" size={15} /> CSV</button>
        </div>
      </div>

      {tab === "Overview" && (
        <>
          <div className="grid overview">
            <div className="card insights">
              <div className="card-head"><h3>What changed in {r.latest.label}</h3><span className="verdict">{r.verdict.label}</span></div>
              <p className="muted">{r.verdict.detail}</p>
              <ul>
                {r.insights.map((i, n) => (
                  <li key={n} className={i.signal}><span className="dot">{i.signal === "positive" ? "▲" : i.signal === "negative" ? "▼" : "●"}</span><span className="area">{i.area}</span><span>{i.text}</span></li>
                ))}
              </ul>
            </div>
            <div className="stack">
              <ChartCard fig={c.gauge} guideKey="gauge" guide={guide} />
              <ChartCard fig={c.pillars} guideKey="pillars" guide={guide} />
            </div>
          </div>
          <div className="grid two">
            <ChartCard fig={c.revenue} guideKey="revenue" guide={guide} />
            <ChartCard fig={c.tone} guideKey="tone" guide={guide} />
          </div>
        </>
      )}

      {tab === "Financials" && (
        <>
          <div className="grid two">
            <ChartCard fig={c.revenue} guideKey="revenue" guide={guide} />
            <ChartCard fig={c.growth} guideKey="growth" guide={guide} />
            <ChartCard fig={c.margins} guideKey="margins" guide={guide} />
            <ChartCard fig={c.cash} guideKey="cash" guide={guide} />
            <ChartCard fig={c.balance} guideKey="balance" guide={guide} />
          </div>
          <Table rows={r.table} />
          <p className="muted small">Fourth-quarter flows are derived as full year minus nine months, as 10-K filings report annual totals.</p>
        </>
      )}

      {tab === "Sentiment" && (
        <>
          <div className="grid two">
            <ChartCard fig={c.tone} guideKey="tone" guide={guide} />
            <ChartCard fig={c.tone_sources} guideKey="tone_sources" guide={guide} />
            <ChartCard fig={c.lm_mdna} guideKey="lm_mdna" guide={guide} />
            <ChartCard fig={c.risk_length} guideKey="risk_length" guide={guide} />
          </div>
          <div className="card">
            <div className="card-head">
              <h3>Evidence: the sentences driving the scores</h3>
              <select value={evQ} onChange={(e) => setEvQ(e.target.value)}>
                {r.evidence.map((e) => <option key={e.quarter}>{e.quarter}</option>)}
              </select>
            </div>
            {ev?.docs.map((d) => (
              <div key={d.section} className="evidence">
                <div className="ev-head">
                  <b>{d.label}</b>
                  <span className="muted">{d.n_sentences} sentences · dictionary tone {fmtSigned(d.lm.net_tone)}{d.model_score != null ? ` · ${r.method.model_name} ${fmtSigned(d.model_score)}` : ""}</span>
                  <button className="link-btn" onClick={() => openExternal(d.source_url)}>Open filing <Icon name="external" size={13} /></button>
                </div>
                {d.top_positive.slice(0, 2).map((s, i) => <blockquote key={"p" + i} className="pos">{s.text}<span>{fmtSigned(s.score)}</span></blockquote>)}
                {d.top_negative.slice(0, 2).map((s, i) => <blockquote key={"n" + i} className="neg">{s.text}<span>{fmtSigned(s.score)}</span></blockquote>)}
              </div>
            ))}
          </div>
        </>
      )}

      {tab === "Health" && (
        <>
          <div className="grid three">
            <ChartCard fig={c.gauge} guideKey="gauge" guide={guide} />
            <ChartCard fig={c.pillars} guideKey="pillars" guide={guide} />
            <ChartCard fig={c.fscore} guideKey="fscore" guide={guide} />
          </div>
          <ChartCard fig={c.health} guideKey="health" guide={guide} />
          <div className="grid two">
            <div className="card">
              <h3>Scorecard metrics · {r.latest.label}</h3>
              <table className="table"><thead><tr><th>Metric</th><th>Value</th><th>Score</th></tr></thead>
                <tbody>{r.scorecard.map((s) => <tr key={s.metric}><td>{s.metric}</td><td>{s.value}</td><td>{s.score == null ? "n/a" : Math.round(s.score)}</td></tr>)}</tbody></table>
            </div>
            {r.fscore && (
              <div className="card">
                <h3>Piotroski F-Score · {r.fscore.score}/{r.fscore.available}</h3>
                <table className="table"><tbody>{r.fscore.signals.map((s) => (
                  <tr key={s.signal}><td>{s.signal}</td><td className="muted">{s.group}</td><td>{s.pass == null ? "n/a" : s.pass ? <span className="pass">Yes</span> : <span className="fail">No</span>}</td></tr>
                ))}</tbody></table>
              </div>
            )}
          </div>
        </>
      )}

      {tab === "Sources" && (
        <div className="card">
          <h3>Sources: every figure is traceable</h3>
          <table className="table"><tbody>{r.sources.map((s) => (
            <tr key={s.url}><td>{s.what}</td><td><button className="link-btn" onClick={() => openExternal(s.url)}>Open <Icon name="external" size={13} /></button></td></tr>
          ))}</tbody></table>
          <p className="muted small">Tone method: {r.method.model_name}{r.method.used_model ? " (runs on this Mac)" : ""}. Dictionary: {r.method.dictionary_source}. Generated {r.generated_at}.</p>
          {r.warnings.length > 0 && <p className="muted small">Data notes: {r.warnings.join("; ")}</p>}
        </div>
      )}
    </>
  );
}

function Table({ rows }: { rows: Record<string, string>[] }) {
  if (!rows.length) return null;
  const cols = Object.keys(rows[0]);
  return (
    <div className="card table-card">
      <h3>Quarter by quarter</h3>
      <table className="table"><thead><tr>{cols.map((c) => <th key={c}>{c}</th>)}</tr></thead>
        <tbody>{rows.map((r, i) => <tr key={i}>{cols.map((c) => <td key={c}>{r[c]}</td>)}</tr>)}</tbody></table>
    </div>
  );
}

const fmtSigned = (v: number | null | undefined) => (v == null ? "n/a" : `${v >= 0 ? "+" : ""}${v.toFixed(2)}`);
