import { useEffect, useRef, useState } from "react";
import { alertText, api, openExternal, type Alert, type Company, type WatchResponse } from "./api";
import { CompanyLogo, Icon } from "./components";

type Props = {
  watch: WatchResponse | null; alerts: Alert[]; secOk: boolean; reload: () => Promise<void>;
  open: (c: { ticker: string; name: string }, jobId?: string | null) => void; goSettings: () => void;
};

function ago(ts: number | null | undefined): string {
  if (!ts) return "never";
  const s = Date.now() / 1000 - ts;
  if (s < 60) return "just now";
  if (s < 3600) return `${Math.round(s / 60)} min ago`;
  if (s < 86400) return `${Math.round(s / 3600)} h ago`;
  return `${Math.round(s / 86400)} d ago`;
}

function until(ts: number | null | undefined): string {
  if (!ts) return "";
  const m = Math.max(0, Math.round((ts - Date.now() / 1000) / 60));
  return m <= 1 ? "in a minute" : `in ${m} min`;
}

export default function WatchlistPage({ watch, alerts, secOk, reload, open, goSettings }: Props) {
  const [query, setQuery] = useState("");
  const [matches, setMatches] = useState<Company[]>([]);
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const [checking, setChecking] = useState(false);
  const [checkMsg, setCheckMsg] = useState("");
  const timer = useRef<number>();

  useEffect(() => {
    window.clearTimeout(timer.current);
    if (!query.trim() || !secOk) { setMatches([]); return; }
    timer.current = window.setTimeout(() => {
      api<Company[]>(`/api/companies?q=${encodeURIComponent(query)}&limit=6`).then(setMatches).catch(() => setMatches([]));
    }, 150);
  }, [query, secOk]);

  async function add(c: Company) {
    setBusy(c.ticker); setError(""); setQuery(""); setMatches([]);
    try { await api("/api/watchlist", { method: "POST", body: JSON.stringify({ ticker: c.ticker }) }); await reload(); }
    catch (e: any) { setError(e.message); }
    finally { setBusy(""); }
  }

  async function remove(ticker: string) {
    await api(`/api/watchlist/${encodeURIComponent(ticker)}`, { method: "DELETE" }).catch(() => {});
    await reload();
  }

  async function checkNow() {
    setChecking(true); setCheckMsg("");
    try {
      const r = await api<{ new: Alert[]; busy: boolean }>("/api/watchlist/check", { method: "POST" });
      setCheckMsg(r.busy ? "A check is already running." : r.new.length ? `${r.new.length} new filing${r.new.length > 1 ? "s" : ""} found.` : "No new filings.");
      await reload();
    } catch (e: any) { setCheckMsg(e.message); }
    finally { setChecking(false); }
  }

  const items = watch?.items ?? [];
  const unreadBy = new Set(alerts.filter((a) => !a.read).map((a) => a.ticker));
  const latestJob = (t: string) => alerts.find((a) => a.ticker === t && a.job_id && a.job_status === "done")?.job_id;

  return (
    <div className="page">
      <div className="page-head">
        <div>
          <h1>Watchlist</h1>
          <p className="muted">Follow companies and hear about new results the day they are filed. While EarningsPulse is open it checks
            SEC EDGAR every 30 minutes; a new 10-Q or 10-K is analysed for you automatically.</p>
        </div>
        <div className="head-actions">
          <button className="btn" onClick={checkNow} disabled={checking || !items.length || !secOk}>
            <Icon name="refresh" size={15} /> {checking || watch?.checking ? "Checking…" : "Check now"}
          </button>
        </div>
      </div>

      {!secOk && <div className="callout"><Icon name="mail" size={16} /> Add your name and e-mail in <button className="link-btn" onClick={goSettings}>Settings</button> first; the SEC asks every app to identify itself.</div>}

      <div className="watch-layout">
        <div className="stack">
          <div className="card">
            <div className="card-head"><h3>Companies you follow</h3>
              <span className="muted small">Last check {ago(watch?.last_run)}{watch?.next_run ? ` · next ${until(watch.next_run)}` : ""}{checkMsg ? ` · ${checkMsg}` : ""}</span>
            </div>
            <div className="search watch-add">
              <Icon name="plus" />
              <input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Add a company or ticker"
                aria-label="Add a company to the watchlist" disabled={!secOk}
                onKeyDown={(e) => { if (e.key === "Enter" && matches[0]) add(matches[0]); }} />
              {matches.length > 0 && (
                <ul className="suggest">
                  {matches.map((c) => (
                    <li key={c.ticker} onMouseDown={() => add(c)}><b>{c.ticker}</b> <span>{c.name}</span>
                      {items.some((i) => i.ticker === c.ticker) && <em className="muted small">already followed</em>}</li>
                  ))}
                </ul>
              )}
            </div>
            {error && <p className="error small">{error}</p>}
            {busy && <p className="muted small">Adding {busy}…</p>}
            {watch?.error && <p className="error small">Last check failed: {watch.error}</p>}

            {items.length === 0 ? (
              <div className="empty">
                <Icon name="star" size={28} />
                <p>Nothing here yet. Add a company above, or press <b>☆ Watch</b> on any analysis.</p>
              </div>
            ) : (
              <ul className="watch-list">
                {items.map((i) => (
                  <li key={i.ticker} className={unreadBy.has(i.ticker) ? "fresh" : ""}>
                    <CompanyLogo ticker={i.ticker} size={40} />
                    <div className="w-main">
                      <div><b>{i.ticker}</b> <span className="muted">{i.name}</span> {unreadBy.has(i.ticker) && <span className="badge">New</span>}</div>
                      <div className="muted small">
                        {i.last_filing ? <>Latest: {i.last_filing.form === "8-K" ? "results (8-K)" : i.last_filing.form} filed {i.last_filing.filed}</> : "No recent filings"}
                        {i.error && <span className="error"> · could not check: {i.error}</span>}
                      </div>
                    </div>
                    <div className="w-meta">
                      {i.verdict ? <span className={`pill ${i.verdict.startsWith("Improving") ? "up" : i.verdict.startsWith("Deteriorating") ? "down" : ""}`}>{i.verdict}</span>
                        : <span className="muted small">Not analysed yet</span>}
                      {i.health != null && <span className="muted small">Health {Math.round(i.health)} · {i.latest}</span>}
                    </div>
                    <button className="btn ghost" onClick={() => open(i, latestJob(i.ticker))} disabled={!secOk}>Open</button>
                    <button className="icon-btn" title={`Stop following ${i.ticker}`} aria-label={`Remove ${i.ticker}`} onClick={() => remove(i.ticker)}><Icon name="x" size={15} /></button>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </div>

        <div className="card alerts">
          <div className="card-head"><h3><Icon name="bell" size={16} /> Alerts</h3>
            {alerts.some((a) => !a.read) && <button className="link-btn small" onClick={() => api("/api/alerts/read", { method: "POST", body: "{}" }).then(reload)}>Mark all read</button>}
          </div>
          {alerts.length === 0 ? (
            <p className="muted small">New filings from companies you follow appear here, and as a Mac notification. Results days are
              usually 4–6 weeks after a quarter ends; the 10-Q or 10-K follows the earnings release, often the same day or a few days later.</p>
          ) : (
            <ul className="alert-list">
              {alerts.slice(0, 30).map((a) => (
                <li key={a.id} className={a.read ? "" : "unread"}>
                  <span className={`a-dot ${a.kind}`} />
                  <div>
                    <p>{alertText(a)}</p>
                    <div className="a-actions">
                      <span className="muted small">{ago(a.created_at)}</span>
                      {a.kind === "report" && (
                        a.job_status === "running" ? <span className="muted small">Analysing…</span>
                          : <button className="link-btn small" onClick={() => {
                              api("/api/alerts/read", { method: "POST", body: JSON.stringify({ id: a.id }) }).then(reload);
                              open(a, a.job_status === "done" ? a.job_id : null);
                            }}>{a.job_status === "done" ? "Analysis ready, open" : "Analyse"}</button>
                      )}
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
    </div>
  );
}
