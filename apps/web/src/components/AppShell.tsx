import { createContext, useCallback, useContext, useEffect, useId, useState, type ReactNode } from "react";
import { NavLink, Outlet, useLocation, useNavigate } from "react-router-dom";
import { Bell, Building2, FolderKanban, Home, LayoutGrid, LogOut, MailWarning, MessageCircle, PlusCircle, Settings2, ShieldCheck, Store, Truck } from "lucide-react";
import { api, auth, type Me } from "../lib/api";
import { LANGS, setLang, useT, type Lang } from "../i18n";

/** Renovara mark: an «R» whose counter is a doorway into a room (brand board). `tile` = app-icon variant on charcoal. */
export function Logo({ size = 28, tile = true }: { size?: number; tile?: boolean }) {
  const id = useId().replace(/:/g, "");
  return (
    <svg width={size} height={size} viewBox="0 0 64 64" aria-hidden style={{ flex: "none" }}>
      <defs>
        <linearGradient id={`${id}t`} x1="0" y1="0" x2="1" y2="1"><stop offset="0" stopColor="#f3e2d1" /><stop offset=".45" stopColor="#d49a7c" /><stop offset="1" stopColor="#a8573a" /></linearGradient>
        <linearGradient id={`${id}s`} x1="0" y1="0" x2="0" y2="1"><stop offset="0" stopColor="#77866a" /><stop offset="1" stopColor="#98a787" /></linearGradient>
        <linearGradient id={`${id}w`} x1="0" y1="0" x2="0" y2="1"><stop offset="0" stopColor="#fffaf3" /><stop offset="1" stopColor="#ecdccb" /></linearGradient>
        <linearGradient id={`${id}f`} x1="0" y1="0" x2="0" y2="1"><stop offset="0" stopColor="#e6d3be" /><stop offset="1" stopColor="#f6ebde" /></linearGradient>
      </defs>
      {tile && <rect width="64" height="64" rx="15" fill="#2e2e2e" />}
      <g transform={tile ? "translate(10 10) scale(.44)" : "translate(2 2) scale(.6)"}>
        <path d="M0 0H58C82 0 98 15 97 34C96 49 86 58 72 61L100 100H0Z" fill={`url(#${id}t)`} />
        <path d="M0 0L22 13V88L0 100Z" fill={`url(#${id}s)`} />
        <path d="M22 13H56C61 28 60 43 55 54L82 88H22Z" fill={`url(#${id}w)`} />
        <path d="M31 55L49 48V88H31Z" fill="#cdb9a3" />
        <path d="M0 100L22 88H82L100 100Z" fill={`url(#${id}f)`} />
      </g>
    </svg>
  );
}

export const BRAND = "Renovara";

/** Horizontal logo: mark + wordmark + tagline (brand board). */
export function BrandLockup({ size = 30, tagline = false }: { size?: number; tagline?: boolean }) {
  const { t } = useT();
  return (
    <div className="brand-lockup">
      <Logo size={size} />
      <div className="col"><BrandName />{tagline && <span className="brand-tagline">{t("brand.tagline")}</span>}</div>
    </div>
  );
}

interface Cfg { brand_name: string; aps_enabled: boolean; external_fetch_live: boolean; ai: Record<string, boolean> }
const MeCtx = createContext<{ me: Me | null; cfg: Cfg | null; reload: () => Promise<void> }>({ me: null, cfg: null, reload: async () => {} });
export const useMe = () => useContext(MeCtx);

export function BrandName({ className = "" }: { className?: string }) {
  const { cfg } = useMe();
  return <span className={`wordmark ${className}`}>{cfg?.brand_name || BRAND}</span>;
}

export function LangSwitch({ compact = false }: { compact?: boolean }) {
  const { t, lang } = useT();
  return (
    <div className="row gap-4" role="group" aria-label={t("common.language")}>
      {LANGS.map((l) => (
        <button key={l.code} className={`chip ${lang === l.code ? "on" : ""}`} style={{ height: compact ? 28 : 32, padding: "0 10px" }} onClick={() => setLang(l.code as Lang)} aria-pressed={lang === l.code}>{l.label}</button>
      ))}
    </div>
  );
}

export function Protected({ children }: { children: ReactNode }) {
  const [me, setMe] = useState<Me | null>(null);
  const [cfg, setCfg] = useState<Cfg | null>(null);
  const nav = useNavigate();
  const loc = useLocation();
  const reload = useCallback(async () => {
    const m = await api<Me>("/auth/me");
    auth.signedIn = true;
    // the profile language wins on a new device; local choice is used before the first save
    if (m.locale && ["hy", "ru", "en"].includes(m.locale)) setLang(m.locale as Lang, { persistRemote: false });
    setMe(m);
  }, []);
  useEffect(() => {
    reload().catch(() => nav(`/login?next=${encodeURIComponent(location.pathname)}`));
    api<Cfg>("/config").then(setCfg).catch(() => {});
  }, [nav, reload]);
  useEffect(() => {
    if (me && me.mfa_enrollment_required && loc.pathname !== "/app/account") nav("/app/account#mfa");  // the API refuses everything else
    else if (me && !me.onboarded && !me.mfa_enrollment_required && loc.pathname !== "/app/onboarding") nav("/app/onboarding");
  }, [me, loc.pathname, nav]);
  if (!me) return <div className="empty"><span className="spinner" /></div>;
  return <MeCtx.Provider value={{ me, cfg, reload }}>{children}</MeCtx.Provider>;
}

export default function AppShell() {
  const { me } = useMe();
  const { t } = useT();
  const loc = useLocation();
  const nav = useNavigate();
  const roles = new Set(me?.roles || []);
  const isPlatform = roles.has("platform_admin") || roles.has("platform_ops");
  const isSupplier = roles.has("supplier_admin") || roles.has("supplier_catalog");
  const isBureau = roles.has("bureau_admin") || roles.has("designer");
  const section = loc.pathname.split("/").filter(Boolean)[1];
  return (
    <div className="shell">
      <aside className="sidebar">
        <div className="brand"><BrandLockup tagline /></div>
        <nav className="nav col gap-4">
          <NavLink to="/app" end><Home size={18} /> {t("nav.home")}</NavLink>
          <NavLink to="/app/projects"><FolderKanban size={18} /> {t("nav.projects")}</NavLink>
          {!isSupplier && <NavLink to="/app/new"><PlusCircle size={18} /> {t("nav.new")}</NavLink>}
          <NavLink to="/app/catalog"><LayoutGrid size={18} /> {t("nav.catalog")}</NavLink>
          <NavLink to="/app/suppliers"><Truck size={18} /> {t("nav.suppliers")}</NavLink>
          {(isBureau || isPlatform) && <><div className="section">{t("nav.cabinets")}</div><NavLink to="/app/bureau"><Building2 size={18} /> {t("nav.bureau")}</NavLink></>}
          {(isSupplier || isPlatform) && <NavLink to="/app/supplier"><Store size={18} /> {t("nav.supplier")}</NavLink>}
          {isPlatform && <><div className="section">{t("nav.administration")}</div>
            <NavLink to="/app/admin"><ShieldCheck size={18} /> {t("nav.admin")}</NavLink>
            <NavLink to="/app/pim"><Settings2 size={18} /> {t("nav.pim")}</NavLink></>}
        </nav>
        <div className="help-card">
          <div className="row between"><b>{t("nav.help_title")}</b><MessageCircle size={18} /></div>
          <p className="muted small mt-8">{t("nav.help_text")}</p>
        </div>
      </aside>
      <div className="main">
        <header className="topbar">
          <div className="crumbs grow hide-sm">{t("common.workspace")}{section ? <> / <b>{t(`nav.section.${section}`)}</b></> : null}</div>
          <LangSwitch compact />
          <button className="icon-btn" aria-label={t("common.notifications")}><Bell size={18} /></button>
          <NavLink to="/app/account" className="row gap-6" title={t("nav.account")} style={{ color: "inherit" }}>
            <div className="avatar">{me?.name.split(" ").map((s) => s[0]).slice(0, 2).join("")}</div>
            <div className="hide-sm"><div style={{ fontWeight: 700, fontSize: 13 }}>{me?.name}</div><div className="tiny muted">{me?.memberships[0]?.org_name}</div></div>
          </NavLink>
          <button className="icon-btn" onClick={async () => { await api("/auth/logout", { method: "POST" }).catch(() => {}); auth.signedIn = false; nav("/login"); }} aria-label={t("nav.logout")} title={t("nav.logout")}><LogOut size={17} /></button>
        </header>
        {me && !me.email_verified && <div className="alert warn small" role="status" style={{ margin: "12px 24px 0" }}><MailWarning size={16} /> {t("banner.verify")} <NavLink to="/app/account">{t("acc.resend")}</NavLink></div>}
        <main className="content"><Outlet /></main>
      </div>
    </div>
  );
}
