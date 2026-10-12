"use client";

import { FormEvent, useEffect, useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { Activity, Boxes, BrainCircuit, ChartNoAxesCombined, ClipboardList,
  Database, Gauge, KeyRound, Layers3, LogOut, Menu, Server, Settings2, ShieldCheck, ClipboardCheck, X } from "lucide-react";
import type { Principal } from "@/lib/api";

const NAV = [
  { path: "/dashboard", label: "Overview", icon: Gauge },
  { path: "/models", label: "Model registry", icon: BrainCircuit },
  { path: "/deployments", label: "Deployments", icon: Server },
  { path: "/datasets", label: "Datasets", icon: Database },
  { path: "/training", label: "Training jobs", icon: Layers3 },
  { path: "/evaluations", label: "Evaluations", icon: ChartNoAxesCombined },
  { path: "/approvals", label: "Release approvals", icon: ClipboardCheck },
  { path: "/audit", label: "Audit events", icon: ClipboardList },
  { path: "/settings", label: "Environment", icon: Settings2 },
];

function Login({ onLogin }: { onLogin: (p: Principal) => void }) {
  const [jwt, setJwt] = useState("");
  const [authMode, setAuthMode] = useState("unavailable");
  useEffect(() => {
    fetch("/api/auth/config", { cache: "no-store" }).then(r => r.json())
      .then(d => setAuthMode(d.mode === "oidc" ? "oidc" : d.mode === "development-token" ? "development-token" : "unavailable"))
      .catch(() => setAuthMode("oidc"));
  }, []);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true); setError("");
    try {
      const r = await fetch("/api/session", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ token: jwt }), credentials: "same-origin",
      });
      const result = await r.json();
      if (!r.ok) throw new Error(String(result.detail || "Token rejected"));
      setJwt("");
      onLogin(result.user as Principal);
    } catch (err) { setError(err instanceof Error ? err.message : "Login failed"); }
    finally { setBusy(false); }
  }
  return (
    <div className="login-stage">
      <section className="login-card">
        <div className="brand-badge"><Boxes size={19} /></div>
        <div className="eyebrow">MODEL INFRASTRUCTURE</div>
        <h1>ModelOps <span>Platform</span></h1>
        <p className="muted">One control plane for your model registry, deployments, training and operational evidence.</p>
        {authMode === "oidc" ? (
          <a href="/api/auth/start" className="primary-button wide">Continue with enterprise SSO</a>
        ) : authMode === "unavailable" ? (
          <p className="error-inline">Enterprise OIDC is required but not configured. Contact the platform administrator.</p>
        ) : <form onSubmit={submit}>
          <label htmlFor="token-input">OIDC or local development access token</label>
          <textarea id="token-input" rows={4} value={jwt}
            onChange={e => setJwt(e.target.value)}
            placeholder="Paste a short-lived token from your identity provider"
            required autoComplete="off" spellCheck={false}/>
          {error && <p role="alert" className="error-inline">{error}</p>}
          <button className="primary-button wide" disabled={busy || jwt.trim().length < 20}>
            <KeyRound size={16}/>{busy ? "Verifying…" : "Connect to workspace"}
          </button>
        </form>}
        <div className="login-foot"><ShieldCheck size={16}/>
          <span>Validated server-side. Session token stays in an HttpOnly cookie.</span></div>
        <div className="login-foot muted">Engineering Preview · Kubernetes is required for real deployments.</div>
      </section>
    </div>
  );
}

export default function Shell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const [me, setMe] = useState<Principal | null>(null);
  const [checking, setChecking] = useState(true);
  const [sidebar, setSidebar] = useState(false);

  useEffect(() => {
    let alive = true;
    fetch("/api/control/me", { cache: "no-store" })
      .then(async r => r.ok ? r.json() : null)
      .then(user => { if (alive) setMe(user as Principal | null); })
      .catch(() => { if (alive) setMe(null); })
      .finally(() => { if (alive) setChecking(false); });
    return () => { alive = false; };
  }, []);

  useEffect(() => { setSidebar(false); }, [pathname]);

  async function logout() {
    await fetch("/api/session/logout", { method: "POST", credentials: "same-origin" });
    setMe(null);
  }

  if (checking) return <div className="login-stage"><div className="loading-mark"><Boxes size={27}/> Connecting to ModelOps…</div></div>;
  if (!me) return <Login onLogin={setMe}/>;

  const current = NAV.find(n => n.path === pathname)?.label || "Overview";
  return (
    <div className="app-layout">
      <aside className={"sidebar" + (sidebar ? " open" : "")}>
        <div className="brand-row"><div className="brand-badge"><Boxes size={19}/></div>
          <div><div className="brand-title">ModelOps</div><div className="brand-caption">CONTROL PLANE</div></div>
          <button className="icon-button close-sidebar" aria-label="Close menu" onClick={() => setSidebar(false)}><X size={18}/></button>
        </div>
        <div className="nav-category">WORKSPACE</div>
        <nav aria-label="Platform navigation">
          {NAV.map(n => {
            const Icon = n.icon;
            return <Link key={n.path} href={n.path} className={"nav-link" + (pathname === n.path ? " selected" : "")}>
              <Icon size={18}/><span>{n.label}</span>
            </Link>;
          })}
        </nav>
        <div className="sidebar-bottom">
          <div className="preview-pill"><Activity size={14}/> Engineering Preview</div>
          <div className="sidebar-user"><div className="avatar">{me.subject.slice(0,1).toUpperCase()}</div>
            <div className="user-text"><strong title={me.subject}>{me.subject}</strong><span>{me.tenant} · {me.role}</span></div>
            <button className="icon-button" aria-label="Sign out" title="Sign out" onClick={logout}><LogOut size={17}/></button>
          </div>
        </div>
      </aside>
      {sidebar && <button className="sidebar-overlay" onClick={() => setSidebar(false)} aria-label="Close sidebar"/>}
      <div className="main-column">
        <header className="topbar">
          <div className="topbar-left">
            <button className="icon-button mobile-menu" aria-label="Open menu" onClick={() => setSidebar(true)}><Menu size={19}/></button>
            <div className="breadcrumbs"><span>Workspace</span><span className="breadcrumb-slash">/</span><strong>{current}</strong></div>
          </div>
          <div className="topbar-right"><span className="tenant-pill"><ShieldCheck size={14}/> {me.tenant}</span>
            <span className="env-pill"><span className="status-dot amber"/> LIVE STATE ONLY</span></div>
        </header>
        <main className="content">{children}</main>
      </div>
    </div>
  );
}
