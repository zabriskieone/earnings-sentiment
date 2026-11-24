import { useEffect, useState } from "react";
import { api, type CompareResult, type Guide } from "./api";
import { ChartCard, CompanyLogo, Icon } from "./components";

// Two or three companies side by side, lined up by calendar quarter.

const CHART_GUIDE: Record<string, string> = {
  growth: "growth", op_margin: "margins", gross_margin: "margins", fcf_margin: "cash", health: "health", tone: "tone",
};
const ORDER = ["growth", "op_margin", "health", "tone", "gross_margin", "fcf_margin"];

type Props = {
  tickers: string[]; theme: "light" | "dark"; guide: Guide | null; openGuide: (k: string) => void;
  back: () => void; openCompany: (c: { ticker: string; name: string }, jobId?: string | null) => void;
};

export default function ComparePage({ tickers, theme, guide, openGuide, back, openCompany }: Props) {
  const [cid, setCid] = useState<string | null>(null);
  const [status, setStatus] = useState<{ progress: number; message: string; status: string; error: string } | null>(null);
  const [results, setResults] = useState<Record<string, CompareResult>>({});
  const [error, setError] = useState("");
  const key = tickers.join(",");

  useEffect(() => {
    let live = true;
    setCid(null); setStatus(null); setResults({}); setError("");
    (async () => {
      try {
        const { compare_id } = await api<{ compare_id: string }>("/api/compare", { method: "POST", body: JSON.stringify({ tickers }) });
        if (!live) return;
        setCid(compare_id);
        for (;;) {
          const st = await api<{ progress: number; message: string; status: string; error: string }>(`/api/compare/${compare_id}`);
          if (!live) return;
          setStatus(st);
          if (st.status !== "running") { if (st.status === "error") setError(st.error); break; }
          await new Promise((r) => setTimeout(r, 500));
        }
      } catch (e: any) { if (live) setError(e.message || String(e)); }
    })();
    return () => { live = false; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key]);

  const r = cid ? results[`${cid}:${theme}`] : undefined;
  useEffect(() => {
    if (!cid || status?.status !== "done" || results[`${cid}:${theme}`]) return;
    api<CompareResult>(`/api/compare/${cid}/result?theme=${theme}`)
      .then((x) => setResults((m) => ({ ...m, [`${cid}:${theme}`]: x })))
      .catch((e) => setError(e.message));
  }, [cid, status?.status, theme, results]);

  return (
    <div className="page compare">
      <div className="page-head">
        <button className="link-btn back" onClick={back}>← Back</button>
        <h1>{tickers.join(" vs ")}</h1>
        <p className="muted">Side by side, with every quarter placed by the calendar months it covers, so companies with different
          fiscal years line up fairly. Colours: {tickers.map((t, i) => <span key={t} className={`swatch s${i}`}>{t}</span>)}</p>
      </div>

      {error && <div className="callout error-callout"><Icon name="help" size={16} /> {error}</div>}
      {!r && !error && (
        <div className="card progress-card">
          <p><b>{status?.message || "Starting"}</b> <span className="muted">· companies you analysed recently open instantly</span></p>
          <div className="bar"><div style={{ width: `${Math.round(100 * (status?.progress ?? 0.03))}%` }} /></div>
        </div>
      )}

      {r && (
        <>
          <div className={`cmp-cards n${r.companies.length}`}>
            {r.companies.map((c, i) => (
              <button key={c.ticker} className={`card cmp-card s${i}`} onClick={() => openCompany(c, r.job_ids[c.ticker])} title={`Open ${c.name}`}>
                <CompanyLogo ticker={c.ticker} size={44} />
                <div className="cmp-main">
                  <b>{c.ticker}</b><span className="muted small">{c.name}</span>
                  <span className="muted tiny">{c.latest} ({c.calendar_quarter}) · {c.form} filed {c.filed}</span>
                </div>
                <div className="cmp-score">
                  <span className={`pill ${c.verdict?.startsWith("Improving") ? "up" : c.verdict?.startsWith("Deteriorating") ? "down" : ""}`}>{c.verdict}</span>
                  <b>{c.health == null ? "–" : Math.round(c.health)}</b><span className="muted tiny">health</span>
                </div>
              </button>
            ))}
          </div>

          {r.notes.map((n, i) => <div key={i} className="callout"><Icon name="guide" size={16} /> {n}</div>)}

          <div className="card">
            <div className="card-head"><h3>Head to head · latest quarter</h3><span className="muted small">★ marks the strongest value in each row</span></div>
            <table className="table cmp-table">
              <thead><tr><th>Measure</th>{r.companies.map((c, i) => <th key={c.ticker} className={`num s${i}`}>{c.ticker}</th>)}</tr></thead>
              <tbody>
                {r.table.map((row) => (
                  <tr key={row.key}>
                    <td>{row.label}{!row.higher_is_better && <span className="muted tiny"> (lower is better)</span>}</td>
                    {row.values.map((v, i) => <td key={i} className={`num${v.best ? " best" : ""}`}>{v.text}{v.best && <span className="star"> ★</span>}</td>)}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <div className="grid two">
            {ORDER.filter((k) => r.charts[k]).map((k) => (
              <ChartCard key={k} fig={r.charts[k]} guideKey={CHART_GUIDE[k]} guide={guide} openGuide={openGuide} />
            ))}
          </div>
          <p className="muted small">Each company keeps the quarters and tone model of its most recent analysis. Click a company card to open its full dashboard.</p>
        </>
      )}
    </div>
  );
}
