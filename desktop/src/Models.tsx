import { useCallback, useEffect, useState } from "react";
import { api, openExternal, type ModelInfo, type ModelsResponse } from "./api";
import { Icon, fmtBytes, fmtEta } from "./components";

export default function Models({ onChange }: { onChange?: () => void }) {
  const [data, setData] = useState<ModelsResponse | null>(null);
  const [error, setError] = useState("");

  const refresh = useCallback(() => api<ModelsResponse>("/api/models").then(setData).catch((e) => setError(e.message)), []);
  useEffect(() => { refresh(); }, [refresh]);

  // poll while anything is downloading
  const busy = data?.models.some((m) => m.download && ["queued", "downloading", "verifying", "installing"].includes(m.download.status));
  useEffect(() => {
    if (!busy) return;
    const t = window.setInterval(refresh, 500);
    return () => window.clearInterval(t);
  }, [busy, refresh]);

  const act = async (path: string, method = "POST") => {
    setError("");
    try {
      const r = await api<any>(path, { method });
      if (r && r.models) setData(r);
      else await refresh();
      onChange?.();
    } catch (e: any) {
      setError(e.message);
    }
  };

  const maxSpeed = Math.max(1, ...(data?.models.map((m) => m.sentences_per_sec_ref || 0) ?? [1]));

  return (
    <div className="page">
      <div className="page-head">
        <h2>Tone models</h2>
        <p className="muted">Models read every sentence of the MD&amp;A and press release and rate it positive, negative or neutral.
          They run entirely on your Mac; nothing you analyse leaves your computer. Download one or more, then choose your default.</p>
      </div>
      {error && <div className="card error">{error}</div>}

      <div className="models">
        <div className={`card model ${!data?.active ? "active" : ""}`}>
          <div className="model-top">
            <div className="model-icon dict"><Icon name="guide" /></div>
            <div className="model-title"><h3>Finance dictionary</h3><span className="muted">Loughran-McDonald word lists</span></div>
            {!data?.active ? <span className="badge on"><Icon name="check" size={13} /> Default</span> : <span className="badge">Built in</span>}
          </div>
          <p>Counts positive, negative, uncertain and legal words using lists built for financial filings. Always on: it powers the
            uncertainty and risk measures even when an AI model is selected.</p>
          <div className="model-meta"><span>No download</span><span>Instant</span></div>
          <div className="model-actions">
            {data?.active && <button className="btn" onClick={() => act("/api/models/dictionary/activate")}>Use dictionary only</button>}
          </div>
        </div>

        {data?.models.map((m) => <ModelCard key={m.id} m={m} maxSpeed={maxSpeed} act={act} />)}

        <div className="card model soon">
          <div className="model-top">
            <div className="model-icon"><Icon name="spark" /></div>
            <div className="model-title"><h3>Local AI summaries</h3><span className="muted">Coming next</span></div>
            <span className="badge">Phase 2</span>
          </div>
          <p>An optional local language model (2-5 GB) that writes a plain-English “what changed this quarter” summary, fully offline.</p>
        </div>
      </div>
      <p className="muted small" style={{ marginTop: 14 }}>* Speed measured on a standard 4-core CPU when the models were built;
        Apple silicon Macs are usually faster. Scores from different models are not directly comparable: compare each model with its own history.</p>
    </div>
  );
}

function ModelCard({ m, maxSpeed, act }: { m: ModelInfo; maxSpeed: number; act: (p: string, method?: string) => void }) {
  const d = m.download;
  const active = d && ["queued", "downloading", "verifying", "installing"].includes(d.status);
  const speedPct = Math.round(((m.sentences_per_sec_ref || 0) / maxSpeed) * 100);
  return (
    <div className={`card model ${m.active ? "active" : ""}`}>
      <div className="model-top">
        <div className="model-icon"><Icon name={m.id.startsWith("distil") ? "bolt" : "models"} /></div>
        <div className="model-title"><h3>{m.name}</h3><span className="muted">{m.tagline}</span></div>
        {m.active ? <span className="badge on"><Icon name="check" size={13} /> Default</span>
          : m.recommended && !m.installed ? <span className="badge rec">Recommended</span>
          : m.installed ? <span className="badge">Downloaded</span> : null}
      </div>
      <p>{m.description}</p>
      <div className="meter"><span>Speed</span><div className="track"><div style={{ width: `${speedPct}%` }} /></div><span className="muted">{Math.round(m.sentences_per_sec_ref)} sentences/s*</span></div>
      <div className="model-meta">
        <span><b>Best for:</b> {m.best_for}</span>
        <span>{fmtBytes(m.installed ? m.disk_bytes : m.size_bytes)}{m.installed ? " on disk" : " download"}</span>
        <button className="link-btn" onClick={() => openExternal(`https://huggingface.co/${m.repo}`)}>Model card <Icon name="external" size={12} /></button>
      </div>

      {active && d && (
        <div className="dl">
          <div className="progress-head">
            <span>{d.status === "downloading" ? `Downloading ${fmtBytes(d.done)} of ${fmtBytes(d.total)}` : d.status === "verifying" ? "Verifying checksum…" : d.status === "installing" ? "Installing…" : "Starting…"}</span>
            <span>{d.status === "downloading" ? `${(d.bytes_per_sec / 1e6).toFixed(1)} MB/s · ${fmtEta(d.eta_sec)}` : ""}</span>
          </div>
          <div className="bar"><div style={{ width: `${Math.max(2, d.progress * 100)}%` }} /></div>
        </div>
      )}
      {d?.status === "error" && <div className="error small">Download failed: {d.error}</div>}

      <div className="model-actions">
        {!m.installed && !active && <button className="btn primary" onClick={() => act(`/api/models/${m.id}/download`)}><Icon name="download" size={15} /> Download</button>}
        {active && <button className="btn" onClick={() => act(`/api/models/${m.id}/download`, "DELETE")}><Icon name="x" size={14} /> Cancel</button>}
        {m.installed && !m.active && <button className="btn primary" onClick={() => act(`/api/models/${m.id}/activate`)}>Make default</button>}
        {m.installed && <button className="btn ghost danger" onClick={() => act(`/api/models/${m.id}`, "DELETE")}><Icon name="trash" size={14} /> Delete</button>}
      </div>
    </div>
  );
}
