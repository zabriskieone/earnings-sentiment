import { useCallback, useEffect, useRef, useState } from "react";
import { alertText, api, notify, waitForEngine, type Alert, type Guide, type Settings, type WatchResponse } from "./api";
import Analyze, { type OpenRequest } from "./Analyze";
import PortfolioPage from "./Portfolio";
import ComparePage from "./Compare";
import Models from "./Models";
import { GuidePage, SettingsPage } from "./Pages";
import { AppMark, Icon } from "./components";

type Page = "analyze" | "portfolio" | "compare" | "models" | "guide" | "settings";

const NAV: { id: Page; label: string; icon: string }[] = [
  { id: "analyze", label: "Analyze", icon: "analyze" },
  { id: "portfolio", label: "Portfolio", icon: "star" },
  { id: "models", label: "Models", icon: "models" },
  { id: "guide", label: "Guide", icon: "guide" },
  { id: "settings", label: "Settings", icon: "settings" },
];

function systemTheme(): "light" | "dark" {
  return window.matchMedia?.("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}

export default function App() {
  const [ready, setReady] = useState(false);
  const [bootError, setBootError] = useState("");
  const [bootSecs, setBootSecs] = useState(0);
  const [page, setPage] = useState<Page>("analyze");
  const [settings, setSettings] = useState<Settings | null>(null);
  const [guide, setGuide] = useState<Guide | null>(null);
  const [guideTarget, setGuideTarget] = useState<string | null>(null);
  const openGuide = useCallback((key: string) => { setGuideTarget(key); setPage("guide"); }, []);
  const clearGuideTarget = useCallback(() => setGuideTarget(null), []);
  const [watch, setWatch] = useState<WatchResponse | null>(null);
  const [alerts, setAlerts] = useState<Alert[]>([]);
  const [openReq, setOpenReq] = useState<OpenRequest | null>(null);
  const notified = useRef<Set<string>>(new Set());
  const startedAt = useRef(Date.now() / 1000);
  const [themePref, setThemePref] = useState<Settings["theme"]>("system");
  const [sysTheme, setSysTheme] = useState(systemTheme());
  const theme = themePref === "system" ? sysTheme : themePref;

  useEffect(() => {
    const mq = window.matchMedia?.("(prefers-color-scheme: dark)");
    const fn = () => setSysTheme(systemTheme());
    mq?.addEventListener("change", fn);
    return () => mq?.removeEventListener("change", fn);
  }, []);
  useEffect(() => { document.documentElement.dataset.theme = theme; }, [theme]);

  const loadSettings = useCallback(async () => {
    const s = await api<Settings>("/api/settings");
    setSettings(s);
    setThemePref(s.theme);
    if (!s.sec_user_agent_valid) setPage("settings");
  }, []);

  useEffect(() => {
    waitForEngine((s) => setBootSecs(s))
      .then(async () => {
        await loadSettings();
        setGuide(await api<Guide>("/api/guide"));
        setReady(true);
      })
      .catch((e) => setBootError(String(e.message || e)));
  }, [loadSettings]);

  // watchlist + alerts: the engine checks SEC; we poll it and turn new alerts into notifications
  const loadWatch = useCallback(async () => {
    const [w, a] = await Promise.all([api<WatchResponse>("/api/watchlist"), api<Alert[]>("/api/alerts")]);
    setWatch(w); setAlerts(a);
    for (const x of a) {
      if (x.read || notified.current.has(x.id)) continue;
      notified.current.add(x.id);
      if (x.created_at >= startedAt.current - 5) notify(x.kind === "results" ? `${x.ticker}: results are out` : `${x.ticker}: new ${x.form}`,
        alertText(x) + (x.kind === "report" ? " Analysing it now; open Portfolio to see it." : ""));
    }
  }, []);
  useEffect(() => {
    if (!ready) return;
    loadWatch().catch(() => {});
    const t = window.setInterval(() => loadWatch().catch(() => {}), 20000);
    return () => window.clearInterval(t);
  }, [ready, loadWatch]);
  const watched = new Set((watch?.items ?? []).map((i) => i.ticker));
  const toggleWatch = async (ticker: string) => {
    if (watched.has(ticker)) await api(`/api/watchlist/${encodeURIComponent(ticker)}`, { method: "DELETE" });
    else await api("/api/watchlist", { method: "POST", body: JSON.stringify({ ticker }) });
    await loadWatch();
  };
  const openCompany = (c: { ticker: string; name: string }, jobId?: string | null) => {
    setOpenReq({ company: { ticker: c.ticker, name: c.name, cik: "" }, jobId: jobId ?? undefined, at: Date.now() });
    setPage("analyze");
  };
  const [compareSet, setCompareSet] = useState<string[]>([]);
  const [compareFrom, setCompareFrom] = useState<Page>("portfolio");
  const startCompare = (tickers: string[]) => { setCompareFrom(page); setCompareSet(tickers); setPage("compare"); };
  const unread = alerts.filter((a) => !a.read).length;

  const changeTheme = async (t: Settings["theme"]) => {
    setThemePref(t);
    try { await api("/api/settings", { method: "PUT", body: JSON.stringify({ theme: t }) }); } catch { /* keep local choice */ }
  };

  if (!ready) {
    return (
      <div className="boot">
        <AppMark size={84} />
        <h1>EarningsPulse</h1>
        {bootError ? <p className="error">{bootError} Please quit and reopen the app. If it keeps happening, check the engine log in
          ~/Library/Application Support/EarningsPulse/logs.</p>
          : <p className="muted">{bootSecs < 3 ? "Starting…" : "Starting the analysis engine (the first launch takes a little longer)…"}</p>}
        {!bootError && <div className="bar slim"><div className="indeterminate" /></div>}
      </div>
    );
  }

  return (
    <div className="shell">
      {/* The whole sidebar background (not its buttons) and the strip above each page move the window */}
      <aside className="sidebar" data-tauri-drag-region>
        <div className="drag-region" data-tauri-drag-region />
        <div className="brand" data-tauri-drag-region><AppMark size={34} /><div data-tauri-drag-region><b data-tauri-drag-region>EarningsPulse</b><span data-tauri-drag-region>Sentiment &amp; health from every quarterly result</span></div></div>
        <nav>
          {NAV.map((n) => (
            <button key={n.id} className={page === n.id || (page === "compare" && n.id === "portfolio") ? "nav on" : "nav"} onClick={() => setPage(n.id)}>
              <Icon name={n.icon} /> {n.label}
              {n.id === "portfolio" && unread > 0 && <span className="count" aria-label={`${unread} new alerts`}>{unread}</span>}
              {n.id === "settings" && settings && !settings.sec_user_agent_valid && <span className="dot-alert" />}
            </button>
          ))}
        </nav>
        <div className="sidebar-fill" data-tauri-drag-region />
        <div className="sidebar-foot">
          <button className="theme-toggle" onClick={() => changeTheme(theme === "dark" ? "light" : "dark")} title="Switch light / dark">
            <Icon name={theme === "dark" ? "sun" : "moon"} /> {theme === "dark" ? "Light mode" : "Dark mode"}
          </button>
          <p>Not investment advice. Runs locally on your Mac.</p>
        </div>
      </aside>
      <main className="main">
        <div className="drag-region top" data-tauri-drag-region />
        {page === "analyze" && <Analyze theme={theme} guide={guide} secOk={!!settings?.sec_user_agent_valid}
          goSettings={() => setPage("settings")} goModels={() => setPage("models")} openGuide={openGuide}
          openReq={openReq} watched={watched} toggleWatch={toggleWatch} portfolio={watch?.items ?? []} startCompare={startCompare} />}
        {page === "compare" && <ComparePage tickers={compareSet} theme={theme} guide={guide} openGuide={openGuide}
          back={() => setPage(compareFrom)} openCompany={openCompany} />}
        {page === "portfolio" && <PortfolioPage watch={watch} alerts={alerts} secOk={!!settings?.sec_user_agent_valid} reload={loadWatch}
          open={openCompany} goSettings={() => setPage("settings")} startCompare={startCompare} />}
        {page === "models" && <Models />}
        {page === "guide" && <GuidePage guide={guide} target={guideTarget} clearTarget={clearGuideTarget} />}
        {page === "settings" && <SettingsPage settings={settings} onSaved={(s) => setSettings(s)} theme={themePref} setTheme={changeTheme}
          goModels={() => setPage("models")} />}
      </main>
    </div>
  );
}
