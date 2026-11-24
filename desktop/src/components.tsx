import { useEffect, useRef, useState, type ReactNode } from "react";
import { logoUrl, type Guide } from "./api";

// ---------------------------------------------------------------- Plotly chart (figure JSON from the engine)
type Figure = { data: unknown[]; layout: Record<string, unknown> };

let plotlyPromise: Promise<any> | null = null;
const loadPlotly = () => (plotlyPromise ??= import("plotly.js-dist-min").then((m: any) => m.default ?? m));

export function Chart({ fig, height }: { fig: Figure; height?: number }) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    let alive = true;
    const el = ref.current;
    loadPlotly().then((Plotly) => {
      if (!alive || !el) return;
      const layout = { ...fig.layout, autosize: true, ...(height ? { height } : {}) };
      delete (layout as any).width;
      Plotly.react(el, fig.data, layout, { displayModeBar: false, responsive: true });
    });
    const ro = new ResizeObserver(() => loadPlotly().then((P) => el && P.Plots.resize(el)));
    if (el) ro.observe(el);
    return () => {
      alive = false;
      ro.disconnect();
      loadPlotly().then((P) => el && P.purge(el));
    };
  }, [fig, height]);
  return <div ref={ref} className="chart" />;
}

// ---------------------------------------------------------------- sparkline for KPI cards
export function Sparkline({ values }: { values: number[] }) {
  if (!values || values.length < 2) return null;
  const w = 160, h = 40, pad = 3;
  const min = Math.min(...values), max = Math.max(...values);
  const span = max - min || 1;
  const pts = values.map((v, i) => [pad + (i * (w - 2 * pad)) / (values.length - 1), h - pad - ((v - min) / span) * (h - 2 * pad)]);
  const line = pts.map((p, i) => `${i ? "L" : "M"}${p[0].toFixed(1)} ${p[1].toFixed(1)}`).join(" ");
  const area = `${line} L${pts[pts.length - 1][0]} ${h} L${pts[0][0]} ${h} Z`;
  const last = pts[pts.length - 1];
  return (
    <svg className="spark" viewBox={`0 0 ${w} ${h}`} preserveAspectRatio="none" aria-hidden>
      <defs>
        <linearGradient id="sg" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor="var(--accent)" stopOpacity="0.28" />
          <stop offset="1" stopColor="var(--accent)" stopOpacity="0" />
        </linearGradient>
      </defs>
      <path d={area} fill="url(#sg)" />
      <path d={line} fill="none" stroke="var(--accent)" strokeWidth="2" vectorEffect="non-scaling-stroke" />
      <circle cx={last[0]} cy={last[1]} r="3" fill="var(--accent)" />
    </svg>
  );
}

// ---------------------------------------------------------------- "How to read this chart"
export function HowTo({ guideKey, guide }: { guideKey: string; guide: Guide | null }) {
  const [open, setOpen] = useState(false);
  const g = guide?.charts[guideKey];
  if (!g) return null;
  return (
    <div className="howto">
      <button className="link-btn" onClick={() => setOpen((o) => !o)} aria-expanded={open}>
        <Icon name="help" size={14} /> How to read this chart <span className={open ? "chev up" : "chev"}>⌄</span>
      </button>
      {open && (
        <div className="howto-body">
          <p><b>What it shows.</b> {g.what}</p>
          <p><b>How to read it.</b> {g.read}</p>
          <p><b>What good looks like.</b> {g.good}</p>
          {g.terms && g.terms.length > 0 && (
            <dl>
              {g.terms.filter((t) => guide?.glossary[t]).map((t) => (
                <div key={t}><dt>{t}</dt><dd>{guide!.glossary[t]}</dd></div>
              ))}
            </dl>
          )}
        </div>
      )}
    </div>
  );
}

export function ChartCard({ fig, guideKey, guide, height }: { fig?: Figure; guideKey: string; guide: Guide | null; height?: number }) {
  if (!fig) return null;
  return (
    <div className="card chart-card">
      <Chart fig={fig} height={height} />
      <HowTo guideKey={guideKey} guide={guide} />
    </div>
  );
}

// ---------------------------------------------------------------- company logo (or monogram)
export function CompanyLogo({ ticker, size = 64 }: { ticker: string; size?: number }) {
  const [src, setSrc] = useState<string | null>(null);
  const [failed, setFailed] = useState(false);
  useEffect(() => {
    let url: string | null = null;
    setSrc(null);
    setFailed(false);
    logoUrl(ticker).then((u) => {
      url = u;
      if (u) setSrc(u);
      else setFailed(true);
    });
    return () => {
      if (url) URL.revokeObjectURL(url);
    };
  }, [ticker]);
  const style = { width: size, height: size, borderRadius: size * 0.28 };
  if (src) return <div className="logo-tile" style={style}><img src={src} alt={`${ticker} logo`} /></div>;
  return (
    <div className="logo-tile monogram" style={{ ...style, fontSize: size * 0.36 }}>
      {failed ? ticker.replace(/[^A-Z]/gi, "").slice(0, 2) : ""}
    </div>
  );
}

// ---------------------------------------------------------------- icons (simple line icons)
const PATHS: Record<string, ReactNode> = {
  analyze: <><path d="M4 19V10M10 19V5M16 19v-7M22 19H2" /></>,
  models: <><rect x="4" y="4" width="16" height="16" rx="3" /><path d="M9 9h6v6H9zM9 2v2M15 2v2M9 20v2M15 20v2M2 9h2M2 15h2M20 9h2M20 15h2" /></>,
  guide: <><path d="M4 5a2 2 0 0 1 2-2h13v16H6a2 2 0 0 0-2 2z" /><path d="M4 19V5M8 7h7M8 11h7" /></>,
  settings: <><circle cx="12" cy="12" r="3" /><path d="M19.4 15a1.7 1.7 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-1.8-.3 1.7 1.7 0 0 0-1 1.5V21a2 2 0 1 1-4 0v-.1a1.7 1.7 0 0 0-1.1-1.5 1.7 1.7 0 0 0-1.8.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.7 1.7 0 0 0 .3-1.8 1.7 1.7 0 0 0-1.5-1H3a2 2 0 1 1 0-4h.1a1.7 1.7 0 0 0 1.5-1.1 1.7 1.7 0 0 0-.3-1.8l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.7 1.7 0 0 0 1.8.3H9a1.7 1.7 0 0 0 1-1.5V3a2 2 0 1 1 4 0v.1a1.7 1.7 0 0 0 1 1.5 1.7 1.7 0 0 0 1.8-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.7 1.7 0 0 0-.3 1.8V9a1.7 1.7 0 0 0 1.5 1H21a2 2 0 1 1 0 4h-.1a1.7 1.7 0 0 0-1.5 1z" /></>,
  sun: <><circle cx="12" cy="12" r="4" /><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4" /></>,
  moon: <><path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z" /></>,
  search: <><circle cx="11" cy="11" r="7" /><path d="m20 20-3.5-3.5" /></>,
  download: <><path d="M12 3v12M7 10l5 5 5-5M4 21h16" /></>,
  check: <><path d="m5 12 5 5 9-10" /></>,
  trash: <><path d="M3 6h18M8 6V4h8v2M6 6l1 14h10l1-14" /></>,
  help: <><circle cx="12" cy="12" r="9" /><path d="M9.5 9a2.5 2.5 0 1 1 3.5 2.3c-.6.3-1 .9-1 1.6V14M12 17.5v.01" /></>,
  external: <><path d="M14 4h6v6M20 4l-9 9M18 14v5a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V7a1 1 0 0 1 1-1h5" /></>,
  file: <><path d="M14 3H6a1 1 0 0 0-1 1v16a1 1 0 0 0 1 1h12a1 1 0 0 0 1-1V8z" /><path d="M14 3v5h5" /></>,
  spark: <><path d="M12 3l1.8 5.4L19 10l-5.2 1.6L12 17l-1.8-5.4L5 10l5.2-1.6z" /></>,
  bolt: <><path d="M13 2 4 14h7l-1 8 9-12h-7z" /></>,
  x: <><path d="M6 6l12 12M18 6 6 18" /></>,
};

export function Icon({ name, size = 18 }: { name: keyof typeof PATHS | string; size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8"
      strokeLinecap="round" strokeLinejoin="round" aria-hidden className="icon">
      {PATHS[name]}
    </svg>
  );
}

export function AppMark({ size = 36 }: { size?: number }) {
  return <img src="/icon.svg" width={size} height={size} alt="" className="app-mark" />;
}

export function fmtBytes(n: number): string {
  if (!n) return "0 MB";
  if (n >= 1e9) return `${(n / 1e9).toFixed(1)} GB`;
  return `${Math.round(n / 1e6)} MB`;
}

export function fmtEta(sec: number | null): string {
  if (sec == null || !isFinite(sec)) return "";
  if (sec < 60) return `${Math.max(1, Math.round(sec))}s left`;
  return `${Math.floor(sec / 60)}m ${String(Math.round(sec % 60)).padStart(2, "0")}s left`;
}
