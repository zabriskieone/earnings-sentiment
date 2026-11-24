import { useEffect, useMemo, useState } from "react";
import { api, openExternal, type ChangeItem, type ChangesResponse } from "./api";
import { Icon } from "./components";

// "What changed in the words": new, reworded and dropped sentences vs an earlier filing.

const TAG_LABEL: Record<string, string> = {
  negative: "Negative", uncertainty: "Uncertain", litigious: "Legal", constraining: "Constraining", positive: "Positive",
};
type List = "added" | "reworded" | "removed";
const PAGE = 40;

export default function ChangesTab({ jobId, latest, modelName, openGuide }: { jobId: string; latest: string; modelName: string | null; openGuide: (k: string) => void }) {
  const [quarter, setQuarter] = useState(latest);
  const [vs, setVs] = useState<"yoy" | "prev">("yoy");
  const [section, setSection] = useState<"mdna" | "risk">("mdna");
  const [data, setData] = useState<ChangesResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [list, setList] = useState<List>("added");
  const [notableOnly, setNotableOnly] = useState(false);
  const [showMinor, setShowMinor] = useState(false);
  const [limit, setLimit] = useState(PAGE);

  useEffect(() => {
    let live = true;
    setLoading(true); setError("");
    api<ChangesResponse>(`/api/analyses/${jobId}/changes?quarter=${encodeURIComponent(quarter)}&vs=${vs}&section=${section}`)
      .then((d) => { if (live) { setData(d); setLimit(PAGE); } })
      .catch((e) => live && setError(String(e.message || e)))
      .finally(() => live && setLoading(false));
    return () => { live = false; };
  }, [jobId, quarter, vs, section]);

  const opt = data?.options.find((o) => o.quarter === quarter);
  const items = useMemo(() => {
    if (!data?.available) return [];
    let xs: ChangeItem[] = data[list];
    if (list === "reworded" && !showMinor) xs = xs.filter((x) => !x.minor);
    if (notableOnly) xs = xs.filter((x) => x.notable);
    return xs;
  }, [data, list, notableOnly, showMinor]);

  const c = data?.available ? data.counts : null;
  const substantive = c ? c.reworded - c.minor : 0;
  const pct = (n: number) => (c && c.new_total ? (100 * n) / c.new_total : 0);

  return (
    <div className="card changes">
      <div className="card-head wrap">
        <div>
          <h3>What changed in the words</h3>
          <p className="muted small">Sentence by sentence, against an earlier report. Figures and dates are ignored, so only wording changes count.{" "}
            <button className="link-btn" onClick={() => openGuide("changes")}>How to read this</button></p>
        </div>
        <div className="changes-controls">
          <select aria-label="Quarter" value={quarter} onChange={(e) => setQuarter(e.target.value)}>
            {(data?.options ?? [{ quarter: latest }]).map((o) => <option key={o.quarter}>{o.quarter}</option>)}
          </select>
          <div className="segmented compact" role="radiogroup" aria-label="Compare with">
            <button role="radio" aria-checked={vs === "yoy"} className={vs === "yoy" ? "on" : ""} onClick={() => setVs("yoy")}
              title={opt?.yoy ? `${opt.yoy} ${opt.yoy_form}` : "Not in this analysis"}>vs a year ago</button>
            <button role="radio" aria-checked={vs === "prev"} className={vs === "prev" ? "on" : ""} onClick={() => setVs("prev")}
              title={opt?.prev ? `${opt.prev} ${opt.prev_form}` : "Not in this analysis"}>vs last quarter</button>
          </div>
          <div className="segmented compact" role="radiogroup" aria-label="Section">
            <button role="radio" aria-checked={section === "mdna"} className={section === "mdna" ? "on" : ""} onClick={() => setSection("mdna")}>MD&amp;A</button>
            <button role="radio" aria-checked={section === "risk"} className={section === "risk" ? "on" : ""} onClick={() => setSection("risk")}>Risk factors</button>
          </div>
        </div>
      </div>

      {error && <p className="error">{error}</p>}
      {loading && !data && <div className="bar slim"><div className="indeterminate" /></div>}

      {data && !data.available && <div className="callout"><Icon name="guide" size={16} /> {data.note}</div>}

      {data?.available && c && (
        <div className={loading ? "changes-body dim" : "changes-body"}>
          <div className="compare-line">
            <button className="link-btn" onClick={() => openExternal(data.new_filing.url)}>{data.new_filing.label} {data.new_filing.form} <Icon name="external" size={12} /></button>
            <span className="muted">compared with</span>
            <button className="link-btn" onClick={() => openExternal(data.old_filing!.url)}>{data.old_filing!.label} {data.old_filing!.form} <Icon name="external" size={12} /></button>
            <span className="muted">· {data.section_name}</span>
          </div>

          <div className="change-stats">
            <div className="stat"><b>{Math.round(100 * c.share_changed)}%</b><span>new or reworded</span></div>
            <div className="stat add"><b>+{c.added}</b><span>new sentences</span></div>
            <div className="stat rew"><b>{substantive}</b><span>reworded{c.minor ? ` (+${c.minor} minor)` : ""}</span></div>
            <div className="stat rem"><b>−{c.removed}</b><span>dropped</span></div>
            <div className="stat"><b>{c.new_total}</b><span>sentences now, {c.old_total} before</span></div>
          </div>
          <div className="change-bar" aria-hidden>
            <span className="same" style={{ width: `${pct(c.unchanged + c.minor)}%` }} />
            <span className="rew" style={{ width: `${pct(substantive)}%` }} />
            <span className="add" style={{ width: `${pct(c.added)}%` }} />
          </div>
          <div className="legend small muted"><i className="same" /> carried over <i className="rew" /> reworded <i className="add" /> new</div>

          <p className="change-summary">{data.summary}</p>
          {data.notes.map((n, i) => <div key={i} className="callout"><Icon name="guide" size={16} /> {n}</div>)}

          <div className="row between list-head">
            <div className="tabs small" role="tablist">
              {(["added", "reworded", "removed"] as List[]).map((l) => (
                <button key={l} role="tab" aria-selected={list === l} className={list === l ? "tab on" : "tab"} onClick={() => { setList(l); setLimit(PAGE); }}>
                  {l === "added" ? `New ${c.added}` : l === "reworded" ? `Reworded ${showMinor ? c.reworded : substantive}` : `Dropped ${c.removed}`}
                </button>
              ))}
            </div>
            <div className="row gap">
              <label className="check"><input type="checkbox" checked={notableOnly} onChange={(e) => setNotableOnly(e.target.checked)} /> Notable only</label>
              {list === "reworded" && <label className="check"><input type="checkbox" checked={showMinor} onChange={(e) => setShowMinor(e.target.checked)} /> Show minor edits</label>}
            </div>
          </div>

          {items.length === 0 && <p className="muted">Nothing here{notableOnly ? " that is notable" : ""}.</p>}
          <ul className="change-list">
            {items.slice(0, limit).map((x, i) => <ChangeRow key={i} x={x} kind={list} modelName={modelName} />)}
          </ul>
          {items.length > limit && <button className="btn ghost" onClick={() => setLimit((n) => n + PAGE * 2)}>Show more ({items.length - limit} left)</button>}

          <p className="muted small foot">
            <b>Notable</b> = uses negative, uncertain, legal or constraining words (Loughran-McDonald dictionary){data.model_name ? `, or ${data.model_name} reads it as clearly positive or negative` : ""}.
            Why it matters: Cohen, Malloy &amp; Nguyen, “Lazy Prices” (Journal of Finance, 2020) found that companies which change their 10-K/10-Q wording a lot tend to underperform afterwards.{" "}
            <button className="link-btn" onClick={() => openExternal("https://doi.org/10.1111/jofi.12885")}>Read the paper <Icon name="external" size={12} /></button>
          </p>
        </div>
      )}
    </div>
  );
}

function ChangeRow({ x, kind, modelName }: { x: ChangeItem; kind: List; modelName: string | null }) {
  const [open, setOpen] = useState(false);
  const tags = kind === "reworded" ? x.new_tags ?? [] : x.tags;
  return (
    <li className={`change ${kind}${x.notable ? " notable" : ""}`}>
      <div className="change-text">
        {kind === "reworded" && x.ops
          ? x.ops.map(([op, t], i) => op === "=" ? <span key={i}>{t} </span> : op === "+" ? <ins key={i}>{t}</ins> : <del key={i}>{t}</del>)
          : x.text}
      </div>
      <div className="change-meta">
        {tags.filter((t) => t !== "positive" || kind !== "reworded").map((t) => <span key={t} className={`tag ${t}`} title="Loughran-McDonald word category found in this sentence">{kind === "reworded" ? "+ " : ""}{TAG_LABEL[t] ?? t}</span>)}
        {x.tone != null && modelName && Math.abs(x.tone) >= 0.5 && (
          <span className={`tone ${x.tone > 0 ? "pos" : "neg"}`} title={`${modelName} reads this sentence as ${x.tone > 0 ? "positive" : "negative"} (scale −1 to +1)`}>
            {x.tone > 0 ? "▲" : "▼"} Tone {x.tone > 0 ? "+" : "−"}{Math.abs(x.tone).toFixed(2)}
          </span>
        )}
        {kind === "reworded" && <button className="link-btn small" onClick={() => setOpen((o) => !o)}>{open ? "Hide" : "Show"} both versions</button>}
      </div>
      {open && x.before && (
        <div className="versions">
          <div><span className="muted small">Before</span><p>{x.before}</p></div>
          <div><span className="muted small">Now</span><p>{x.text}</p></div>
        </div>
      )}
    </li>
  );
}
