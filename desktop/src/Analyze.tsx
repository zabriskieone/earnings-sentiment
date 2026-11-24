import { useEffect, useMemo, useRef, useState } from "react";
import { api, openExternal, revealFile, isTauri, getEngine, type Company, type Guide, type HistoryItem, type WatchItem, type JobStatus, type ModelsResponse, type Result } from "./api";
import { ChartCard, CompanyLogo, Icon, Sparkline } from "./components";
import ChangesTab from "./Changes";

export type OpenRequest = { company: Company; jobId?: string; at: number };

type Props = {
  theme: "light" | "dark"; guide: Guide | null; secOk: boolean;
  goSettings: () => void; goModels: () => void; openGuide: (key: string) => void;
  openReq: OpenRequest | null; watched: Set<string>; toggleWatch: (ticker: string) => Promise<void>;
  portfolio: WatchItem[]; startCompare: (tickers: string[]) => void;
};

const QUARTER_OPTIONS = [
  { n: 4, hint: "1 year" }, { n: 6, hint: "1.5 years" }, { n: 8, hint: "2 years" }, { n: 10, hint: "2.5 years" }, { n: 12, hint: "3 years" },
];

const TABS = ["Overview", "Financials", "Sentiment", "Changes", "Health", "Sources"] as const;
type Tab = (typeof TABS)[number];

export default function Analyze({ theme, guide, secOk, goSettings, goModels, openGuide, openReq, watched, toggleWatch, portfolio, startCompare }: Props) {
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
  const [history, setHistory] = useState<HistoryItem[]>([]);
  const loadHistory = () => api<HistoryItem[]>("/api/history").then(setHistory).catch(() => {});
  useEffect(() => { loadHistory(); }, []);
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

  // opened from Portfolio: show a finished background analysis, or start one
  const handledReq = useRef(0);
  useEffect(() => {
    if (!openReq || handledReq.current === openReq.at) return;
    handledReq.current = openReq.at;
    const prev = history.find((h) => h.ticker === openReq.company.ticker);
    run({ company: openReq.company, quarters: prev?.quarters ?? quarters, model: prev?.model_id ?? "active", jobId: openReq.jobId });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [openReq]);

  async function run(over?: { company: Company; quarters: number; model: string; jobId?: string }) {
    const company = over?.company ?? picked;
    const q = over?.quarters ?? quarters;
    const model = over?.model ?? modelChoice;
    if (!company) return;
    if (over) { setPicked(over.company); setQuery(over.company.ticker); setQuarters(q); setModelChoice(model); }
    setError("");
    setTab("Overview");
    try {
      const body = { ticker: company.ticker, quarters: q, model_id: model === "active" ? null : model };
      let job_id = over?.jobId;
      if (job_id) {
        try { await api<JobStatus>(`/api/analyses/${job_id}`); } catch { job_id = undefined; } // engine restarted since
      }
      if (!job_id) ({ job_id } = await api<{ job_id: string }>("/api/analyses", { method: "POST", body: JSON.stringify(body) }));
      setJobId(job_id);
      setJob({ job_id, status: "running", progress: 0, message: "Starting", error: "" });
      for (;;) {
        await new Promise((r) => setTimeout(r, 450));
        const st = await api<JobStatus>(`/api/analyses/${job_id}`);
        setJob(st);
        if (st.status !== "running") {
          if (st.status === "error") setError(st.error);
          else loadHistory();
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
  const launch = !result && !running;
  const modelLabel = (id: string) =>
    id === "active" ? (models?.active ? `${models.active_name} (default)` : "Dictionary only")
      : id === "dictionary" ? "Dictionary only" : models?.models.find((m) => m.id === id)?.name ?? id;

  const search = (
    <div className={launch ? "search big" : "search"}>
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
        aria-label="Company or ticker"
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
  );

  const notices = (
    <>
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
    </>
  );

  return (
    <div className="page">
      {launch ? (
        <>
          <div className="page-head" data-tauri-drag-region>
            <h2 data-tauri-drag-region>Analyze a company</h2>
            <p className="muted" data-tauri-drag-region>Pick a company, how far back to look and which tone model to use. Everything runs on your Mac.</p>
          </div>
          {notices}
          <div className="launch">
            <div className="card launch-form">
              <label className="label">Company</label>
              {search}

              <label className="label">How many quarters</label>
              <div className="segmented wide" role="radiogroup" aria-label="Quarters">
                {QUARTER_OPTIONS.map((o) => (
                  <button key={o.n} role="radio" aria-checked={quarters === o.n} className={quarters === o.n ? "on" : ""} onClick={() => setQuarters(o.n)}>
                    <b>{o.n}</b><span>{o.hint}</span>
                  </button>
                ))}
              </div>
              <p className="muted small">More quarters show longer trends; each new quarter adds a few seconds the first time.</p>

              <label className="label">Tone model</label>
              <div className="model-pick" role="radiogroup" aria-label="Tone model">
                {models?.active && (
                  <ModelOption id="active" on={modelChoice === "active"} title={`${models.active_name}`} sub="Your default model" icon="models" pick={setModelChoice} />
                )}
                {installed.filter((m) => !m.active).map((m) => (
                  <ModelOption key={m.id} id={m.id} on={modelChoice === m.id} title={m.name} sub={m.tagline} icon={m.id.startsWith("distil") ? "bolt" : "models"} pick={setModelChoice} />
                ))}
                <ModelOption id="dictionary" on={modelChoice === "dictionary" || (!models?.active && modelChoice === "active")} title="Dictionary only"
                  sub="Loughran-McDonald word lists, instant" icon="guide" pick={setModelChoice} />
                {models && installed.length < models.models.length && (
                  <button className="model-opt more" onClick={goModels}><Icon name="download" /><div><b>Get more models</b><span>FinBERT-tone, DistilRoBERTa…</span></div></button>
                )}
              </div>

              <button className="btn primary block" onClick={() => run()} disabled={!picked || !secOk}>
                <Icon name="analyze" size={16} /> Analyze {picked ? picked.ticker : ""}
              </button>
              {error && <div className="error small" style={{ marginTop: 10 }}>{error}</div>}
            </div>

            <div className="launch-side">
              <div className="card recent">
                <div className="card-head"><h3>Recent analyses</h3>
                  {history.length > 0 && <button className="link-btn small" onClick={() => api("/api/history", { method: "DELETE" }).then(loadHistory)}>Clear</button>}
                </div>
                {history.length === 0 ? (
                  <p className="muted small">Companies you analyze appear here, so you can reopen them in one click
                    (results load from the local cache in seconds).</p>
                ) : (
                  <ul>
                    {history.slice(0, 7).map((h) => (
                      <li key={h.ticker + h.model_id}>
                        <button onClick={() => run({ company: { ticker: h.ticker, name: h.name, cik: "" }, quarters: h.quarters, model: h.model_id ?? "active" })} disabled={!secOk}>
                          <CompanyLogo ticker={h.ticker} size={34} />
                          <div className="rec-main"><b>{h.ticker}</b><span>{h.name}</span></div>
                          <div className="rec-meta">
                            <span className={`pill ${h.verdict.startsWith("Improving") ? "up" : h.verdict.startsWith("Deteriorating") ? "down" : ""}`}>{h.verdict}</span>
                            <span className="muted">{h.latest} · {timeAgo(h.analysed_at)}</span>
                          </div>
                        </button>
                      </li>
                    ))}
                  </ul>
                )}
              </div>
              <div className="card how">
                <h3>How it works</h3>
                <ol>
                  <li><b>Reads the filings:</b> each 10-Q / 10-K and earnings press release, straight from SEC EDGAR.</li>
                  <li><b>Scores the tone:</b> finance dictionary plus the AI model you pick, sentence by sentence.</li>
                  <li><b>Compares the numbers:</b> each quarter against the last one and the same quarter a year earlier.</li>
                  <li><b>Rates the health:</b> a five-pillar score and the Piotroski F-Score.</li>
                </ol>
                <button className="link-btn small" onClick={() => openGuide("start")}>Read the Guide <Icon name="external" size={12} /></button>
              </div>
            </div>
          </div>
        </>
      ) : (
        <>
          <div className="toolbar card">
            <button className="btn ghost small" onClick={() => { setJobId(null); setJob(null); setError(""); }} disabled={running}
              title="Back to the start page and your recent analyses">← New analysis</button>
            {search}
            <div className="segmented compact" role="radiogroup" aria-label="Quarters">
              {QUARTER_OPTIONS.map((o) => (
                <button key={o.n} className={quarters === o.n ? "on" : ""} onClick={() => setQuarters(o.n)} title={`${o.n} quarters (${o.hint})`}>{o.n}Q</button>
              ))}
            </div>
            <label className="field">
              <span>Tone model</span>
              <select value={modelChoice} onChange={(e) => setModelChoice(e.target.value)}>
                <option value="active">{modelLabel("active")}</option>
                {installed.filter((m) => !m.active).map((m) => <option key={m.id} value={m.id}>{m.name}</option>)}
                <option value="dictionary">Dictionary only</option>
              </select>
            </label>
            <button className="btn primary" onClick={() => run()} disabled={!picked || running || !secOk}>
              {running ? "Analyzing…" : "Analyze"}
            </button>
          </div>
          {notices}
        </>
      )}

      {running && job && (
        <div className="card progress-card">
          <div className="progress-head"><span>{job.message}</span><span>{Math.round(job.progress * 100)}%</span></div>
          <div className="bar"><div style={{ width: `${Math.max(3, job.progress * 100)}%` }} /></div>
        </div>
      )}
      {error && !launch && <div className="card error"><b>Something went wrong.</b> {error}</div>}

      {result && jobId && <Dashboard r={result} jobId={jobId} watched={watched.has(result.company.ticker)} toggleWatch={toggleWatch}
        portfolio={portfolio} startCompare={startCompare} tab={tab} setTab={setTab} guide={guide} onExport={exportReport} openGuide={openGuide} />}

      {toast && (
        <div className="toast">
          <Icon name="check" /> {toast.text}
          {toast.path && <button className="link-btn" onClick={() => revealFile(toast.path!)}>Show in Finder</button>}
        </div>
      )}
    </div>
  );
}

function ModelOption({ id, on, title, sub, icon, pick }: { id: string; on: boolean; title: string; sub: string; icon: string; pick: (id: string) => void }) {
  return (
    <button role="radio" aria-checked={on} className={on ? "model-opt on" : "model-opt"} onClick={() => pick(id)}>
      <Icon name={icon} />
      <div><b>{title}</b><span>{sub}</span></div>
      <span className="radio" />
    </button>
  );
}

function timeAgo(ts: number): string {
  const s = Date.now() / 1000 - ts;
  if (s < 90) return "just now";
  if (s < 3600) return `${Math.round(s / 60)} min ago`;
  if (s < 86400) return `${Math.round(s / 3600)} h ago`;
  return `${Math.round(s / 86400)} d ago`;
}

function Dashboard({ r, jobId, watched, toggleWatch, portfolio, startCompare, tab, setTab, guide, onExport, openGuide }: { r: Result; jobId: string; watched: boolean; toggleWatch: (t: string) => Promise<void>; portfolio: WatchItem[]; startCompare: (t: string[]) => void; tab: Tab; setTab: (t: Tab) => void; guide: Guide | null; onExport: (k: "pdf" | "html" | "csv") => void; openGuide: (k: string) => void }) {
  const c = r.charts;
  const [evQ, setEvQ] = useState(r.evidence[0]?.quarter);
  const ev = useMemo(() => r.evidence.find((e) => e.quarter === evQ) ?? r.evidence[0], [r, evQ]);
  return (
    <>
      <div className="hero company">
        <div className="hero-actions">
        <ComparePicker me={r.company.ticker} portfolio={portfolio} start={startCompare} />
        <button className={watched ? "btn watch on" : "btn watch"} onClick={() => toggleWatch(r.company.ticker).catch(() => {})}
          aria-pressed={watched} title={watched ? "Remove from your portfolio" : "Add to your portfolio: get an alert when it files new results"}>
          <Icon name={watched ? "check" : "plus"} size={15} /> {watched ? "In portfolio" : "Add to portfolio"}
        </button>
        </div>
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
              <ChartCard fig={c.gauge} guideKey="gauge" guide={guide} openGuide={openGuide} />
              <ChartCard fig={c.pillars} guideKey="pillars" guide={guide} openGuide={openGuide} />
            </div>
          </div>
          <div className="grid two">
            <ChartCard fig={c.revenue} guideKey="revenue" guide={guide} openGuide={openGuide} />
            <ChartCard fig={c.tone} guideKey="tone" guide={guide} openGuide={openGuide} />
          </div>
        </>
      )}

      {tab === "Financials" && (
        <>
          <div className="grid two">
            <ChartCard fig={c.revenue} guideKey="revenue" guide={guide} openGuide={openGuide} />
            <ChartCard fig={c.growth} guideKey="growth" guide={guide} openGuide={openGuide} />
            <ChartCard fig={c.margins} guideKey="margins" guide={guide} openGuide={openGuide} />
            <ChartCard fig={c.cash} guideKey="cash" guide={guide} openGuide={openGuide} />
            <ChartCard fig={c.balance} guideKey="balance" guide={guide} openGuide={openGuide} />
          </div>
          <Table rows={r.table} />
          <p className="muted small">Fourth-quarter flows are derived as full year minus nine months, as 10-K filings report annual totals.</p>
        </>
      )}

      {tab === "Sentiment" && (
        <>
          <div className="grid two">
            <ChartCard fig={c.tone} guideKey="tone" guide={guide} openGuide={openGuide} />
            <ChartCard fig={c.tone_sources} guideKey="tone_sources" guide={guide} openGuide={openGuide} />
            <ChartCard fig={c.lm_mdna} guideKey="lm_mdna" guide={guide} openGuide={openGuide} />
            <ChartCard fig={c.risk_length} guideKey="risk_length" guide={guide} openGuide={openGuide} />
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

      {tab === "Changes" && <ChangesTab jobId={jobId} latest={r.latest.label} modelName={r.method.used_model ? r.method.model_name : null} openGuide={openGuide} />}

      {tab === "Health" && (
        <>
          <div className="grid three">
            <ChartCard fig={c.gauge} guideKey="gauge" guide={guide} openGuide={openGuide} />
            <ChartCard fig={c.pillars} guideKey="pillars" guide={guide} openGuide={openGuide} />
            <ChartCard fig={c.fscore} guideKey="fscore" guide={guide} openGuide={openGuide} />
          </div>
          <ChartCard fig={c.health} guideKey="health" guide={guide} openGuide={openGuide} />
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

function ComparePicker({ me, portfolio, start }: { me: string; portfolio: WatchItem[]; start: (t: string[]) => void }) {
  const [open, setOpen] = useState(false);
  const [pos, setPos] = useState<{ top: number; right: number }>({ top: 0, right: 0 });
  const btn = useRef<HTMLButtonElement>(null);
  const [sel, setSel] = useState<string[]>([]);
  // the hero clips its overflow, so the popover is placed in the window under the button
  const toggleOpen = () => {
    const r = btn.current?.getBoundingClientRect();
    if (r) setPos({ top: r.bottom + 8, right: window.innerWidth - r.right });
    setOpen((o) => !o);
  };
  useEffect(() => {
    if (!open) return;
    const close = () => setOpen(false);
    const main = document.querySelector(".main");
    main?.addEventListener("scroll", close, { passive: true });
    window.addEventListener("resize", close);
    return () => { main?.removeEventListener("scroll", close); window.removeEventListener("resize", close); };
  }, [open]);
  const [typed, setTyped] = useState("");
  const others = portfolio.filter((p) => p.ticker !== me);
  const toggle = (t: string) => setSel((s) => (s.includes(t) ? s.filter((x) => x !== t) : s.length >= 2 ? s : [...s, t]));
  const go = () => {
    const extra = typed.split(/[\s,]+/).map((t) => t.trim().toUpperCase().replace(/^\$/, "")).filter(Boolean);
    const list = [me, ...sel, ...extra].filter((t, i, a) => a.indexOf(t) === i).slice(0, 3);
    if (list.length >= 2) { setOpen(false); start(list); }
  };
  return (
    <div className="picker-wrap">
      <button ref={btn} className="btn watch" onClick={toggleOpen} aria-expanded={open}><Icon name="analyze" size={15} /> Compare with…</button>
      {open && (
        <div className="picker" style={{ top: pos.top, right: pos.right }} role="dialog" aria-label={`Compare ${me} with`}>
          <p className="small muted">Compare {me} with up to two companies.</p>
          {others.length > 0 && <div className="picker-chips">{others.map((p) => (
            <button key={p.ticker} className={sel.includes(p.ticker) ? "chip-btn on" : "chip-btn"} onClick={() => toggle(p.ticker)}
              aria-pressed={sel.includes(p.ticker)}>{p.ticker}</button>))}</div>}
          <input className="input" value={typed} onChange={(e) => setTyped(e.target.value)} placeholder={others.length ? "or type tickers, e.g. GOOGL" : "Tickers, e.g. MSFT, GOOGL"}
            onKeyDown={(e) => e.key === "Enter" && go()} aria-label="Other tickers" />
          <div className="row gap"><button className="btn primary" onClick={go} disabled={!sel.length && !typed.trim()}>Compare</button>
            <button className="btn ghost" onClick={() => setOpen(false)}>Cancel</button></div>
        </div>
      )}
    </div>
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
