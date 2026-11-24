import { useCallback, useEffect, useState } from "react";
import { api, waitForEngine, type Guide, type Settings } from "./api";
import Analyze from "./Analyze";
import Models from "./Models";
import { GuidePage, SettingsPage } from "./Pages";
import { AppMark, Icon } from "./components";

type Page = "analyze" | "models" | "guide" | "settings";

const NAV: { id: Page; label: string; icon: string }[] = [
  { id: "analyze", label: "Analyze", icon: "analyze" },
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
      <aside className="sidebar">
        <div className="drag-region" data-tauri-drag-region />
        <div className="brand"><AppMark size={34} /><div><b>EarningsPulse</b><span>Sentiment &amp; health from every quarterly result</span></div></div>
        <nav>
          {NAV.map((n) => (
            <button key={n.id} className={page === n.id ? "nav on" : "nav"} onClick={() => setPage(n.id)}>
              <Icon name={n.icon} /> {n.label}
              {n.id === "settings" && settings && !settings.sec_user_agent_valid && <span className="dot-alert" />}
            </button>
          ))}
        </nav>
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
          goSettings={() => setPage("settings")} goModels={() => setPage("models")} />}
        {page === "models" && <Models />}
        {page === "guide" && <GuidePage guide={guide} />}
        {page === "settings" && <SettingsPage settings={settings} onSaved={(s) => setSettings(s)} theme={themePref} setTheme={changeTheme} />}
      </main>
    </div>
  );
}
