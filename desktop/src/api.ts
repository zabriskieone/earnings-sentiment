// Talks to the local EarningsPulse engine (Python, bundled inside the app).
// In the Mac app, Tauri tells us the engine's address and per-launch token.
// For development in a normal browser, pass ?engine=http://127.0.0.1:8765&token=...

export type Engine = { url: string; token: string; data_dir?: string; default_data_dir?: string; log_file?: string };

export const isTauri = () => typeof window !== "undefined" && "__TAURI_INTERNALS__" in window;

let engine: Engine | null = null;

export async function getEngine(): Promise<Engine> {
  if (engine) return engine;
  if (isTauri()) {
    const { invoke } = await import("@tauri-apps/api/core");
    engine = await invoke<Engine>("engine_info");
  } else {
    const p = new URLSearchParams(window.location.search);
    engine = {
      url: p.get("engine") || import.meta.env.VITE_ENGINE_URL || "http://127.0.0.1:8765",
      token: p.get("token") || import.meta.env.VITE_ENGINE_TOKEN || "",
    };
  }
  return engine;
}

export class ApiError extends Error {
  status: number;
  constructor(message: string, status: number) {
    super(message);
    this.status = status;
  }
}

export async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  const e = await getEngine();
  const res = await fetch(e.url + path, {
    ...init,
    headers: { "X-EP-Token": e.token, "Content-Type": "application/json", ...(init.headers || {}) },
  });
  if (!res.ok) {
    let msg = `${res.status} ${res.statusText}`;
    try {
      const body = await res.json();
      msg = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail ?? body);
    } catch {
      /* not JSON */
    }
    throw new ApiError(msg, res.status);
  }
  return (await res.json()) as T;
}

/** Wait until the engine answers (it takes a moment to start after launch). */
export async function waitForEngine(onTick?: (secs: number) => void, timeoutSec = 90): Promise<void> {
  const e = await getEngine();
  const start = Date.now();
  for (;;) {
    try {
      const r = await fetch(e.url + "/api/health");
      if (r.ok) return;
    } catch {
      /* not up yet */
    }
    const secs = (Date.now() - start) / 1000;
    if (secs > timeoutSec) throw new Error("The analysis engine did not start.");
    onTick?.(secs);
    await new Promise((r) => setTimeout(r, 400));
  }
}

export async function logoUrl(ticker: string): Promise<string | null> {
  const e = await getEngine();
  const res = await fetch(`${e.url}/api/logo/${encodeURIComponent(ticker)}`, { headers: { "X-EP-Token": e.token } });
  if (!res.ok) return null;
  return URL.createObjectURL(await res.blob());
}

export async function openExternal(url: string) {
  if (isTauri()) {
    const { openUrl } = await import("@tauri-apps/plugin-opener");
    await openUrl(url);
  } else {
    window.open(url, "_blank", "noopener");
  }
}

/** Native folder picker (desktop app only). Returns null if cancelled. */
export async function pickFolder(title: string): Promise<string | null> {
  if (!isTauri()) return window.prompt(title + " (full path)") || null;
  const { open } = await import("@tauri-apps/plugin-dialog");
  const r = await open({ directory: true, multiple: false, title });
  return typeof r === "string" ? r : null;
}

/** Switch the app to a data folder (already populated by the engine) and restart. */
export async function useDataDir(path: string) {
  if (!isTauri()) return;
  const { invoke } = await import("@tauri-apps/api/core");
  await invoke("use_data_dir", { path });
}

export async function revealFile(path: string) {
  if (isTauri()) {
    const { revealItemInDir } = await import("@tauri-apps/plugin-opener");
    await revealItemInDir(path);
  }
}

// ---------------------------------------------------------------- types
export type Settings = {
  sec_user_agent: string;
  sec_user_agent_valid: boolean;
  sec_name: string;
  sec_email: string;
  theme: "light" | "dark" | "system";
  active_model: string | null;
  data_dir: string;
};

export type Company = { ticker: string; name: string; cik: string };

export type DownloadStatus = {
  status: "queued" | "downloading" | "verifying" | "installing" | "done" | "error" | "cancelled";
  progress: number;
  done: number;
  total: number;
  bytes_per_sec: number;
  eta_sec: number | null;
  error: string;
};

export type ModelInfo = {
  id: string;
  name: string;
  repo: string;
  tagline: string;
  best_for: string;
  description: string;
  license: string;
  paper: string;
  recommended: boolean;
  size_bytes: number;
  sentences_per_sec_ref: number;
  installed: boolean;
  active: boolean;
  disk_bytes: number;
  download: DownloadStatus | null;
};

export type ModelsResponse = { models: ModelInfo[]; active: string | null; active_name: string };

export type JobStatus = { job_id: string; status: "running" | "done" | "error"; progress: number; message: string; error: string };

export type Insight = { area: string; text: string; signal: "positive" | "negative" | "neutral" };
export type Kpi = { name: string; value: string; delta: string; note?: string; help: string };
export type EvidenceDoc = {
  section: string;
  label: string;
  n_sentences: number;
  lm: Record<string, number | null>;
  model_score: number | null;
  top_positive: { text: string; score: number }[];
  top_negative: { text: string; score: number }[];
  source_url: string;
};

export type Result = {
  company: Company;
  latest: { label: string; period_end: string; form: string; filed: string };
  quarters: number;
  method: { model_id: string | null; model_name: string; used_model: boolean; dictionary_source: string };
  generated_at: string;
  kpis: Kpi[];
  sparks: Record<string, number[]>;
  verdict: { label: string; detail: string };
  insights: Insight[];
  charts: Record<string, { data: unknown[]; layout: Record<string, unknown> }>;
  table: Record<string, string>[];
  scorecard: { metric: string; value: string; score: number | null }[];
  fscore: { score: number; available: number; signals: { group: string; signal: string; pass: boolean | null }[] } | null;
  evidence: { quarter: string; docs: EvidenceDoc[] }[];
  sources: { what: string; url: string }[];
  warnings: string[];
};

export type ChangeItem = {
  text: string; tags: string[]; tone: number | null; notable: boolean;
  before?: string; similarity?: number; ops?: [string, string][]; new_tags?: string[]; minor?: boolean;
};

export type ChangeOption = { quarter: string; form?: string; prev?: string | null; prev_form?: string | null; yoy?: string | null; yoy_form?: string | null };
type FilingRef = { label: string; form: string; filed: string; url: string };

export type ChangesResponse = {
  quarter: string; vs: "prev" | "yoy"; section: "mdna" | "risk"; section_name: string;
  available: boolean; note?: string; options: ChangeOption[];
  new_filing: FilingRef; old_filing?: FilingRef;
  counts: { new_total: number; old_total: number; unchanged: number; added: number; removed: number; reworded: number; minor: number; share_changed: number };
  summary: string; notes: string[]; model_name: string | null;
  added: ChangeItem[]; removed: ChangeItem[]; reworded: ChangeItem[];
};

export type Guide = {
  charts: Record<string, { title: string; what: string; read: string; good: string; terms?: string[] }>;
  glossary: Record<string, string>;
  kpi_help: Record<string, string>;
};

export type HistoryItem = {
  ticker: string; name: string; quarters: number; model_id: string | null; model_name: string; latest: string;
  verdict: string; health: number | null; tone: number | null; analysed_at: number;
};

export type Storage = { data_dir: string; sizes: { filings: number; models: number; summaries: number; logs: number } };
