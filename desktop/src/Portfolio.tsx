import { useEffect, useMemo, useRef, useState } from "react";
import { alertText, api, openExternal, type Alert, type Company, type WatchItem, type WatchResponse } from "./api";
import { CompanyLogo, Icon } from "./components";

// Portfolio: the companies you follow, side by side, plus new-filing alerts.

type Props = {
  watch: WatchResponse | null; alerts: Alert[]; secOk: boolean; reload: () => Promise<void>;
  open: (c: { ticker: string; name: string }, jobId?: string | null) => void; goSettings: () => void;
  startCompare: (tickers: string[]) => void;
};

type SortKey = "ticker" | "verdict" | "health" | "health_change" | "tone" | "revenue_yoy" | "gross_margin" | "fscore" | "filed";

const COLS: { key: SortKey; label: string; title: string; num?: boolean }[] = [
  { key: "ticker", label: "Company", title: "Sort by ticker" },
  { key: "verdict", label: "Overall", title: "Improving, stable or deteriorating, from the latest analysis" },
  { key: "health", label: "Health", title: "0-100 health score and change vs the same quarter a year ago", num: true },
  { key: "tone", label: "Tone", title: "How positive management's language is (-1 to +1) and change vs a year ago", num: true },
  { key: "revenue_yoy", label: "Revenue YoY", title: "Latest quarter's revenue vs the same quarter a year ago", num: true },
  { key: "gross_margin", label: "Gross margin", title: "Latest quarter", num: true },
  { key: "fscore", label: "F-Score", title: "Piotroski F-Score, 0-9 (higher is stronger)", num: true },
  { key: "filed", label: "Latest filing", title: "Most recent 10-Q, 10-K or earnings 8-K" },
];

const VERDICT_RANK: Record<string, number> = { Improving: 3, "Stable / mixed": 2, Deteriorating: 1 };
const vRank = (v: string | null) => (v ? VERDICT_RANK[v.split(" (")[0]] ?? 2 : 0);

function ago(ts: number | null | undefined): string {
  if (!ts) return "never";
  const s = Date.now() / 1000 - ts;
  if (s < 60) return "just now";
  if (s < 3600) return `${Math.round(s / 60)} min ago`;
  if (s < 86400) return `${Math.round(s / 3600)} h ago`;
  return `${Math.round(s / 86400)} d ago`;
}
const until = (ts: number | null | undefined) => {
  if (!ts) return "";
  const m = Math.max(0, Math.round((ts - Date.now() / 1000) / 60));
  return m <= 1 ? "in a minute" : `in ${m} min`;
};
const pct = (v: number | null, signed = true) => (v == null ? "–" : `${signed && v >= 0 ? "+" : v < 0 ? "−" : ""}${Math.abs(v * 100).toFixed(1)}%`);
const signed = (v: number | null, d = 2) => (v == null ? "" : `${v >= 0 ? "+" : "−"}${Math.abs(v).toFixed(d)}`);
const isStale = (i: WatchItem) => !i.analysed_at || (i.last_filing?.kind === "report" && !!i.period_end && i.last_filing.period != null && i.last_filing.period > i.period_end);

export default function PortfolioPage({ watch, alerts, secOk, reload, open, goSettings, startCompare }: Props) {
  const [query, setQuery] = useState("");
  const [matches, setMatches] = useState<Company[]>([]);
  const [paste, setPaste] = useState<string | null>(null);
  const [busy, setBusy] = useState("");
  const [msg, setMsg] = useState("");
  const [error, setError] = useState("");
  const [checking, setChecking] = useState(false);
  const [picked, setPicked] = useState<string[]>([]);
  const togglePick = (t: string) => setPicked((p) => (p.includes(t) ? p.filter((x) => x !== t) : p.length >= 3 ? p : [...p, t]));
  const [sort, setSort] = useState<{ key: SortKey; dir: 1 | -1 }>({ key: "health", dir: -1 });
  const timer = useRef<number>();

  const items = watch?.items ?? [];
  const b = watch?.batch ?? { queued: 0, running: 0, done: 0, errors: 0 };
  const batchActive = b.queued + b.running > 0;

  // refresh quickly while a batch is running
  useEffect(() => {
    if (!batchActive) return;
    const t = window.setInterval(() => reload().catch(() => {}), 2500);
    return () => window.clearInterval(t);
  }, [batchActive, reload]);

  useEffect(() => {
    window.clearTimeout(timer.current);
    if (!query.trim() || !secOk) { setMatches([]); return; }
    timer.current = window.setTimeout(() => {
      api<Company[]>(`/api/companies?q=${encodeURIComponent(query)}&limit=6`).then(setMatches).catch(() => setMatches([]));
    }, 150);
  }, [query, secOk]);

  async function addMany(tickers: string[]) {
    setError(""); setMsg(""); setBusy(tickers.length === 1 ? `Adding ${tickers[0]}…` : `Adding ${tickers.length} companies…`);
    try {
      const r = await api<{ added: string[]; failed: { ticker: string; error: string }[] }>("/api/watchlist/bulk", { method: "POST", body: JSON.stringify({ tickers }) });
      setMsg(r.added.length ? `Added ${r.added.join(", ")}.` : "");
      if (r.failed.length) setError(`Not found: ${r.failed.map((f) => f.ticker).join(", ")}. US-listed companies that file 10-Q/10-K reports only.`);
      if (r.added.length) await api("/api/portfolio/analyse", { method: "POST", body: JSON.stringify({ tickers: r.added, stale_only: true }) });
      await reload();
    } catch (e: any) { setError(e.message); }
    finally { setBusy(""); }
  }

  async function analyseAll(staleOnly: boolean) {
    setError("");
    try { await api("/api/portfolio/analyse", { method: "POST", body: JSON.stringify({ stale_only: staleOnly }) }); await reload(); }
    catch (e: any) { setError(e.message); }
  }

  async function checkNow() {
    setChecking(true); setMsg("");
    try {
      const r = await api<{ new: Alert[]; busy: boolean }>("/api/watchlist/check", { method: "POST" });
      setMsg(r.busy ? "A check is already running." : r.new.length ? `${r.new.length} new filing${r.new.length > 1 ? "s" : ""} found.` : "No new filings.");
      await reload();
    } catch (e: any) { setMsg(e.message); }
    finally { setChecking(false); }
  }

  const remove = async (t: string) => { await api(`/api/watchlist/${encodeURIComponent(t)}`, { method: "DELETE" }).catch(() => {}); await reload(); };

  const sorted = useMemo(() => {
    const val = (i: WatchItem): number | string | null =>
      sort.key === "ticker" ? i.ticker : sort.key === "verdict" ? vRank(i.verdict) : sort.key === "filed" ? i.last_filing?.filed ?? "" : (i[sort.key] as number | null);
    return [...items].sort((a, c) => {
      const x = val(a), y = val(c);
      if (x == null && y == null) return 0;
      if (x == null) return 1;
      if (y == null) return -1;
      return (x < y ? -1 : x > y ? 1 : 0) * sort.dir;
    });
  }, [items, sort]);

  const analysed = items.filter((i) => i.health != null);
  const avgHealth = analysed.length ? analysed.reduce((s, i) => s + (i.health ?? 0), 0) / analysed.length : null;
  const counts = { up: 0, flat: 0, down: 0 };
  analysed.forEach((i) => { const r = vRank(i.verdict); if (r === 3) counts.up++; else if (r === 1) counts.down++; else counts.flat++; });
  const stale = items.filter(isStale).length;
  const unreadBy = new Set(alerts.filter((a) => !a.read).map((a) => a.ticker));
  const best = [...analysed].sort((a, c) => (c.health ?? 0) - (a.health ?? 0))[0];
  const weakest = [...analysed].sort((a, c) => (a.health ?? 0) - (c.health ?? 0))[0];

  const th = (c: (typeof COLS)[number]) => (
    <th key={c.key} className={c.num ? "num" : ""} title={c.title} aria-sort={sort.key === c.key ? (sort.dir === 1 ? "ascending" : "descending") : "none"}>
      <button onClick={() => setSort((s) => ({ key: c.key, dir: s.key === c.key ? (s.dir === 1 ? -1 : 1) : c.num || c.key === "verdict" ? -1 : 1 }))}>
        {c.label}{sort.key === c.key ? (sort.dir === 1 ? " ↑" : " ↓") : ""}
      </button>
    </th>
  );

  return (
    <div className="page portfolio">
      <div className="page-head">
        <div>
          <h1>Portfolio</h1>
          <p className="muted">Every company you follow, side by side. While EarningsPulse is open it checks SEC EDGAR every 30 minutes,
            alerts you to new results and analyses new 10-Q and 10-K reports automatically.</p>
        </div>
        <div className="head-actions">
          <button className="btn" onClick={checkNow} disabled={checking || !items.length || !secOk} title="Look for new filings now">
            <Icon name="refresh" size={15} /> {checking || watch?.checking ? "Checking…" : "Check filings"}
          </button>
          {batchActive ? (
            <button className="btn" onClick={() => api("/api/portfolio/analyse", { method: "DELETE" }).then(reload)}>
              <span className="spinner" /> Analysing {b.done + b.errors + b.running}/{b.done + b.errors + b.running + b.queued} · Stop
            </button>
          ) : (
            <button className="btn primary" onClick={() => analyseAll(stale > 0)} disabled={!items.length || !secOk}
              title={stale ? "Analyse companies never analysed, or with a newer report than their last analysis" : "Re-run every analysis (cached filings make this quick)"}>
              <Icon name="bolt" size={15} /> {stale ? `Analyse ${stale} out of date` : "Refresh all"}
            </button>
          )}
        </div>
      </div>

      {!secOk && <div className="callout"><Icon name="mail" size={16} /> Add your name and e-mail in <button className="link-btn" onClick={goSettings}>Settings</button> first; the SEC asks every app to identify itself.</div>}

      {items.length > 0 && (
        <div className="pf-summary">
          <div className="card stat-card"><span className="muted small">Companies</span><b>{items.length}</b><span className="muted small">{analysed.length} analysed</span></div>
          <div className="card stat-card"><span className="muted small">Average health</span><b>{avgHealth == null ? "–" : Math.round(avgHealth)}</b>
            <div className="mini-bar"><span style={{ width: `${avgHealth ?? 0}%` }} /></div></div>
          <div className="card stat-card"><span className="muted small">Direction</span>
            <div className="dir-row"><span className="up">▲ {counts.up}</span><span className="flat">● {counts.flat}</span><span className="down">▼ {counts.down}</span></div>
            <div className="dir-bar">{analysed.length > 0 && <>
              <span className="up" style={{ flex: counts.up }} /><span className="flat" style={{ flex: counts.flat }} /><span className="down" style={{ flex: counts.down }} /></>}</div>
          </div>
          <div className="card stat-card"><span className="muted small">Strongest · weakest</span>
            <b className="pair">{best ? `${best.ticker} ${Math.round(best.health ?? 0)}` : "–"}</b>
            <span className="muted small">{weakest && weakest !== best ? `${weakest.ticker} ${Math.round(weakest.health ?? 0)}` : " "}</span></div>
        </div>
      )}

      <div className="card pf-table-card">
        <div className="card-head wrap">
          <div className="search pf-add">
            <Icon name="plus" />
            <input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Add a company or ticker" aria-label="Add a company"
              disabled={!secOk} onKeyDown={(e) => { if (e.key === "Enter" && matches[0]) { addMany([matches[0].ticker]); setQuery(""); setMatches([]); } }} />
            {matches.length > 0 && (
              <ul className="suggest">
                {matches.map((c) => (
                  <li key={c.ticker} onMouseDown={() => { addMany([c.ticker]); setQuery(""); setMatches([]); }}>
                    <b>{c.ticker}</b> <span>{c.name}</span>{items.some((i) => i.ticker === c.ticker) && <em className="muted small">already in portfolio</em>}
                  </li>
                ))}
              </ul>
            )}
          </div>
          <button className="btn ghost" onClick={() => setPaste(paste == null ? "" : null)} disabled={!secOk}>Paste a list</button>
          <span className="muted small pf-check">Last check {ago(watch?.last_run)}{watch?.next_run ? ` · next ${until(watch.next_run)}` : ""}</span>
        </div>
        {paste != null && (
          <div className="paste">
            <textarea value={paste} onChange={(e) => setPaste(e.target.value)} rows={3} autoFocus
              placeholder="AAPL, MSFT, NVDA, GOOGL — separated by commas, spaces or new lines (copy a column from a spreadsheet)" />
            <div className="row gap">
              <button className="btn primary" disabled={!paste.trim()} onClick={() => { addMany(paste.split(/[\s,;]+/).filter(Boolean)); setPaste(null); }}>
                Add {paste.split(/[\s,;]+/).filter(Boolean).length || ""} companies
              </button>
              <button className="btn ghost" onClick={() => setPaste(null)}>Cancel</button>
              <span className="muted small">Each new company is analysed automatically, one after another.</span>
            </div>
          </div>
        )}
        {(busy || msg || error || watch?.error) && (
          <p className="small pf-msg">{busy && <span className="muted">{busy} </span>}{msg && <span className="ok">{msg} </span>}
            {error && <span className="error">{error} </span>}{watch?.error && <span className="error">Last check failed: {watch.error}</span>}</p>
        )}

        {items.length === 0 ? (
          <div className="empty">
            <Icon name="star" size={28} />
            <p>Your portfolio is empty. Add companies above, paste a list of tickers, or press <b>+ Add to portfolio</b> on any analysis.</p>
          </div>
        ) : (
          <div className="table-scroll">
            <table className="table pf-table">
              <thead><tr><th className="pick" aria-label="Select to compare" />{COLS.map(th)}<th aria-label="Actions" /></tr></thead>
              <tbody>
                {sorted.map((i) => {
                  const st = i.batch?.status;
                  const r = vRank(i.verdict);
                  return (
                    <tr key={i.ticker} className={`${unreadBy.has(i.ticker) ? "fresh" : ""}${picked.includes(i.ticker) ? " picked" : ""}`}>
                      <td className="pick">
                        <input type="checkbox" checked={picked.includes(i.ticker)} onChange={() => togglePick(i.ticker)}
                          disabled={!picked.includes(i.ticker) && picked.length >= 3} aria-label={`Select ${i.ticker} to compare`}
                          title={!picked.includes(i.ticker) && picked.length >= 3 ? "Compare up to three companies" : "Select to compare"} />
                      </td>
                      <td>
                        <button className="pf-co" onClick={() => open(i, i.batch?.status === "done" ? i.batch.job_id : null)} disabled={!secOk} title={`Open ${i.name}`}>
                          <CompanyLogo ticker={i.ticker} size={32} />
                          <span><b>{i.ticker}</b>{unreadBy.has(i.ticker) && <span className="badge">New</span>}<small>{i.name}</small></span>
                        </button>
                      </td>
                      <td>
                        {st === "running" ? <span className="pill"><span className="spinner" /> Analysing</span>
                          : st === "queued" ? <span className="pill">Queued</span>
                          : st === "error" ? <span className="pill down" title={i.batch?.error}>Failed</span>
                          : i.verdict ? <span className={`pill ${r === 3 ? "up" : r === 1 ? "down" : ""}`}>{i.verdict}</span>
                          : <span className="muted small">Not analysed</span>}
                        {isStale(i) && i.analysed_at && st !== "running" && st !== "queued" && <div className="muted tiny">newer report out</div>}
                      </td>
                      <td className="num">
                        {i.health == null ? "–" : <div className="hcell"><b>{Math.round(i.health)}</b>
                          <div className="mini-bar"><span style={{ width: `${i.health}%` }} /></div>
                          {i.health_change != null && <small className={i.health_change > 0.5 ? "up" : i.health_change < -0.5 ? "down" : ""}>{signed(i.health_change, 0)}</small>}</div>}
                      </td>
                      <td className="num">{i.tone == null ? "–" : <>{signed(i.tone)}{i.tone_change != null && <small className={i.tone_change > 0.02 ? "up" : i.tone_change < -0.02 ? "down" : ""}> {signed(i.tone_change)}</small>}</>}</td>
                      <td className={`num ${i.revenue_yoy == null ? "" : i.revenue_yoy >= 0 ? "up" : "down"}`}>{pct(i.revenue_yoy)}</td>
                      <td className="num">{pct(i.gross_margin, false)}</td>
                      <td className="num">{i.fscore == null ? "–" : `${i.fscore}/9`}</td>
                      <td>{i.last_filing ? <button className="link-btn small" onClick={() => openExternal(i.last_filing!.url)}>
                        {i.last_filing.form === "8-K" ? "Results 8-K" : i.last_filing.form} · {i.last_filing.filed}</button> : <span className="muted small">–</span>}
                        {i.latest && <div className="muted tiny">analysed: {i.latest}</div>}</td>
                      <td className="actions">
                        <button className="icon-btn" title={`Remove ${i.ticker} from portfolio`} aria-label={`Remove ${i.ticker}`} onClick={() => remove(i.ticker)}><Icon name="x" size={15} /></button>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
        {picked.length > 0 && (
          <div className="compare-bar" role="region" aria-label="Compare selection">
            <span>{picked.map((t) => <span key={t} className="chip-sel">{t}<button aria-label={`Unselect ${t}`} onClick={() => togglePick(t)}>×</button></span>)}</span>
            <span className="muted small">{picked.length < 2 ? "Select one or two more to compare" : picked.length === 3 ? "Maximum of three" : "Add one more, or compare now"}</span>
            <button className="btn primary" disabled={picked.length < 2} onClick={() => startCompare(picked)}>Compare {picked.length > 1 ? picked.length : ""}</button>
          </div>
        )}
        {items.length > 0 && <p className="muted small foot">Tick two or three companies to compare them side by side. Click a company to open its full dashboard. Health and tone changes compare with the same quarter a year earlier.
          Each company keeps the quarters and model of its last analysis.</p>}
      </div>

      <div className="card alerts">
        <div className="card-head"><h3><Icon name="bell" size={16} /> Alerts</h3>
          {alerts.some((a) => !a.read) && <button className="link-btn small" onClick={() => api("/api/alerts/read", { method: "POST", body: "{}" }).then(reload)}>Mark all read</button>}
        </div>
        {alerts.length === 0 ? (
          <p className="muted small">New filings from your companies appear here and as a Mac notification. Results usually come 4–6 weeks after a
            quarter ends; the 10-Q or 10-K follows the earnings release, often the same day or a few days later.</p>
        ) : (
          <ul className="alert-list">
            {alerts.slice(0, 20).map((a) => (
              <li key={a.id} className={a.read ? "" : "unread"}>
                <span className={`a-dot ${a.kind}`} />
                <div>
                  <p>{alertText(a)}</p>
                  <div className="a-actions">
                    <span className="muted small">{ago(a.created_at)}</span>
                    {a.kind === "report" && (a.job_status === "running" ? <span className="muted small">Analysing…</span> : (
                      <button className="link-btn small" onClick={() => {
                        api("/api/alerts/read", { method: "POST", body: JSON.stringify({ id: a.id }) }).then(reload);
                        open(a, a.job_status === "done" ? a.job_id : null);
                      }}>{a.job_status === "done" ? "Analysis ready, open" : "Analyse"}</button>))}
                    {a.kind === "results" && <span className="muted small">Full analysis when the 10-Q/10-K is filed</span>}
                    <button className="link-btn small" onClick={() => openExternal(a.url)}>Filing <Icon name="external" size={11} /></button>
                  </div>
                </div>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}
