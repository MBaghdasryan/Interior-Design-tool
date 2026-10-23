import { useEffect, useRef, useState, type FormEvent, type ReactNode } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { ArrowRight, CheckCircle2, MailCheck } from "lucide-react";
import { api, auth } from "../lib/api";
import { getLang, useT } from "../i18n";
import { BrandLockup, LangSwitch } from "../components/AppShell";

/** Shared card for the public auth screens (register, confirm e-mail, forgot / reset password). */
export function AuthCard({ title, lead, children }: { title: string; lead?: string; children: ReactNode }) {
  return (
    <div style={{ minHeight: "100%", display: "grid", placeItems: "center", padding: 16 }}>
      <div className="card col gap-16" style={{ width: "min(480px, 100%)", padding: 32 }}>
        <div className="row between"><div className="brand" style={{ padding: 0 }}><BrandLockup size={32} tagline /></div><LangSwitch compact /></div>
        <div><h2>{title}</h2>{lead && <p className="muted mt-8">{lead}</p>}</div>
        {children}
      </div>
    </div>
  );
}

export function Register() {
  const { t } = useT();
  const nav = useNavigate();
  const [f, setF] = useState({ name: "", email: "", password: "", org_name: "", org_kind: "bureau", accept_terms: false });
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);
  const set = (k: string, v: string | boolean) => setF((x) => ({ ...x, [k]: v }));
  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setErr(""); setBusy(true);
    try {
      await api("/auth/register", { method: "POST", json: { ...f, locale: getLang(), ref: (() => { try { return localStorage.getItem("forma.ref") || ""; } catch { return ""; } })() } });
      auth.signedIn = true;
      nav("/app/onboarding");
    } catch (x) { setErr((x as Error).message); } finally { setBusy(false); }
  };
  return (
    <AuthCard title={t("reg.title")} lead={t("reg.lead")}>
      <form className="col gap-12" onSubmit={submit}>
        <div className="field"><label>{t("reg.org_kind")}</label>
          <div className="row gap-6 wrap">{(["bureau", "supplier"] as const).map((k) => (
            <button type="button" key={k} className={`chip ${f.org_kind === k ? "on" : ""}`} aria-pressed={f.org_kind === k} onClick={() => set("org_kind", k)}>{t(`reg.kind.${k}`)}</button>
          ))}</div>
        </div>
        <div className="field"><label htmlFor="r-org">{t("reg.org_name")}</label><input id="r-org" className="input" required value={f.org_name} onChange={(e) => set("org_name", e.target.value)} autoComplete="organization" /></div>
        <div className="field"><label htmlFor="r-name">{t("reg.name")}</label><input id="r-name" className="input" required value={f.name} onChange={(e) => set("name", e.target.value)} autoComplete="name" /></div>
        <div className="field"><label htmlFor="r-email">{t("login.email")}</label><input id="r-email" className="input" type="email" required value={f.email} onChange={(e) => set("email", e.target.value)} autoComplete="email" /></div>
        <div className="field"><label htmlFor="r-pw">{t("login.password")}</label><input id="r-pw" className="input" type="password" required minLength={10} value={f.password} onChange={(e) => set("password", e.target.value)} autoComplete="new-password" />
          <span className="tiny muted">{t("reg.password_hint")}</span></div>
        <label className="row small gap-6" style={{ alignItems: "flex-start" }}><input type="checkbox" checked={f.accept_terms} onChange={(e) => set("accept_terms", e.target.checked)} style={{ marginTop: 3 }} /> {t("reg.terms")}</label>
        {err && <div className="alert danger" role="alert">{err}</div>}
        <button className="btn primary lg" disabled={busy || !f.accept_terms}>{t("reg.submit")} <ArrowRight size={18} /></button>
        <div className="small muted">{t("reg.have_account")} <Link to="/login">{t("login.to_login")}</Link></div>
      </form>
    </AuthCard>
  );
}

export function VerifyEmail() {
  const { t } = useT();
  const [q] = useSearchParams();
  const [state, setState] = useState<"checking" | "ok" | "error">("checking");
  const [err, setErr] = useState("");
  const once = useRef(false);  // StrictMode double effect must not consume the one-time token twice
  useEffect(() => {
    if (once.current) return;
    once.current = true;
    api("/auth/verify-email", { method: "POST", json: { token: q.get("token") || "" } })
      .then(() => setState("ok")).catch((x) => { setErr((x as Error).message); setState("error"); });
  }, [q]);
  return (
    <AuthCard title={t("verify.title")}>
      {state === "checking" && <div className="row gap-6"><span className="spinner" /> {t("verify.checking")}</div>}
      {state === "ok" && <><div className="alert sage"><MailCheck size={18} /> {t("verify.ok")}</div><Link className="btn primary" to="/app">{t("verify.continue")} <ArrowRight size={16} /></Link></>}
      {state === "error" && <><div className="alert danger" role="alert">{err}</div><Link className="btn" to="/app/account">{t("acc.resend")}</Link></>}
    </AuthCard>
  );
}

export function ForgotPassword() {
  const { t } = useT();
  const [email, setEmail] = useState("");
  const [sent, setSent] = useState(false);
  const [err, setErr] = useState("");
  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setErr("");
    try { await api("/auth/password/forgot", { method: "POST", json: { email } }); setSent(true); } catch (x) { setErr((x as Error).message); }
  };
  return (
    <AuthCard title={t("forgot.title")} lead={t("forgot.lead")}>
      {sent ? <div className="alert sage" role="status"><MailCheck size={18} /> {t("forgot.sent")}</div> : (
        <form className="col gap-12" onSubmit={submit}>
          <div className="field"><label htmlFor="f-email">{t("login.email")}</label><input id="f-email" className="input" type="email" required value={email} onChange={(e) => setEmail(e.target.value)} autoComplete="email" /></div>
          {err && <div className="alert danger" role="alert">{err}</div>}
          <button className="btn primary lg">{t("forgot.submit")}</button>
        </form>
      )}
      <Link className="small" to="/login">{t("login.to_login")}</Link>
    </AuthCard>
  );
}

export function ResetPassword() {
  const { t } = useT();
  const [q] = useSearchParams();
  const [pw, setPw] = useState("");
  const [pw2, setPw2] = useState("");
  const [done, setDone] = useState(false);
  const [err, setErr] = useState("");
  const submit = async (e: FormEvent) => {
    e.preventDefault();
    if (pw !== pw2) { setErr(t("reset.mismatch")); return; }
    setErr("");
    try { await api("/auth/password/reset", { method: "POST", json: { token: q.get("token") || "", password: pw } }); setDone(true); } catch (x) { setErr((x as Error).message); }
  };
  return (
    <AuthCard title={t("reset.title")}>
      {done ? <><div className="alert sage" role="status"><CheckCircle2 size={18} /> {t("reset.ok")}</div><Link className="btn primary" to="/login">{t("login.to_login")}</Link></> : (
        <form className="col gap-12" onSubmit={submit}>
          <div className="field"><label htmlFor="n-pw">{t("reset.password")}</label><input id="n-pw" className="input" type="password" required minLength={10} value={pw} onChange={(e) => setPw(e.target.value)} autoComplete="new-password" />
            <span className="tiny muted">{t("reg.password_hint")}</span></div>
          <div className="field"><label htmlFor="n-pw2">{t("reset.repeat")}</label><input id="n-pw2" className="input" type="password" required value={pw2} onChange={(e) => setPw2(e.target.value)} autoComplete="new-password" /></div>
          {err && <div className="alert danger" role="alert">{err}</div>}
          <button className="btn primary lg">{t("reset.submit")}</button>
        </form>
      )}
    </AuthCard>
  );
}
