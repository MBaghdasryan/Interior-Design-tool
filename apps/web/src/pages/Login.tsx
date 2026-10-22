import { useEffect, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { ArrowRight } from "lucide-react";
import { api, auth } from "../lib/api";
import { roleName } from "../lib/format";
import { useT } from "../i18n";
import { BrandLockup, LangSwitch } from "../components/AppShell";

interface Demo { email: string; name: string; role: string; password: string }

export default function Login() {
  const { t } = useT();
  const [email, setEmail] = useState("designer@forma.local");
  const [password, setPassword] = useState("");
  const [err, setErr] = useState("");
  const [demo, setDemo] = useState<Demo[]>([]);
  const [mfaToken, setMfaToken] = useState("");
  const [code, setCode] = useState("");
  const [useBackup, setUseBackup] = useState(false);
  const nav = useNavigate();
  const [q] = useSearchParams();
  useEffect(() => { api<Demo[]>("/auth/demo-accounts").then(setDemo).catch(() => {}); }, []);
  const submit = async (e?: React.FormEvent, em = email, pw = password) => {
    e?.preventDefault();
    setErr("");
    try {
      const r = await api<{ mfa_required?: boolean; mfa_token?: string }>("/auth/login", { method: "POST", json: { email: em, password: pw } });
      if (r.mfa_required && r.mfa_token) { setMfaToken(r.mfa_token); return; }
      done();
    } catch (x) { setErr((x as Error).message); }
  };
  function done() {
    auth.signedIn = true;
    const next = q.get("next");
    nav(next && next.startsWith("/app") ? next : "/app");
  }
  const verify = async (e: React.FormEvent) => {
    e.preventDefault();
    setErr("");
    try {
      await api("/auth/mfa/verify", { method: "POST", json: { mfa_token: mfaToken, ...(useBackup ? { backup_code: code } : { code }) } });
      done();
    } catch (x) { setErr((x as Error).message); }
  };
  if (mfaToken) return (
    <div style={{ minHeight: "100%", display: "grid", placeItems: "center", padding: 16 }}>
      <form className="card col gap-16" style={{ width: "min(440px, 100%)", padding: 32 }} onSubmit={verify}>
        <div className="row between"><div className="brand" style={{ padding: 0 }}><BrandLockup size={32} tagline /></div><LangSwitch compact /></div>
        <div><h2>{t("login.mfa_title")}</h2><p className="muted mt-8">{useBackup ? t("login.mfa_backup_ph") : t("login.mfa_hint")}</p></div>
        <input id="mfa-code" className="input" autoFocus autoComplete="one-time-code" inputMode={useBackup ? "text" : "numeric"} value={code}
          aria-label={useBackup ? t("login.mfa_backup_ph") : t("login.mfa_title")} onChange={(e) => setCode(e.target.value.trim())} />
        {err && <div className="alert danger" role="alert">{err}</div>}
        <button className="btn primary lg">{t("login.mfa_submit")} <ArrowRight size={18} /></button>
        <button type="button" className="btn ghost sm" onClick={() => { setUseBackup(!useBackup); setCode(""); }}>{useBackup ? t("login.mfa_use_totp") : t("login.mfa_use_backup")}</button>
      </form>
    </div>
  );
  return (
    <div style={{ minHeight: "100%", display: "grid", placeItems: "center", padding: 16 }}>
      <div className="card" style={{ width: "min(960px, 100%)", display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(300px, 1fr))", overflow: "hidden" }}>
        <form className="col gap-16" style={{ padding: 36 }} onSubmit={submit}>
          <div className="row between"><div className="brand" style={{ padding: 0 }}><BrandLockup size={34} tagline /></div><LangSwitch compact /></div>
          <div><h2>{t("login.title")}</h2><p className="muted mt-8">{t("login.lead")}</p></div>
          <div className="field"><label htmlFor="em">{t("login.email")}</label><input id="em" className="input" value={email} onChange={(e) => setEmail(e.target.value)} autoComplete="username" /></div>
          <div className="field"><label htmlFor="pw">{t("login.password")}</label><input id="pw" className="input" type="password" value={password} onChange={(e) => setPassword(e.target.value)} autoComplete="current-password" /></div>
          {err && <div className="alert danger" role="alert">{err}</div>}
          <button className="btn primary lg">{t("login.submit")} <ArrowRight size={18} /></button>
          <div className="row between small wrap"><span className="muted">{t("login.no_account")} <Link to="/register">{t("login.register")}</Link></span><Link to="/forgot-password">{t("login.forgot")}</Link></div>
        </form>
        <div style={{ background: "var(--bg-2)", padding: 28 }} className="col">
          <h3>{t("login.demo")}</h3>
          <p className="muted small">{t("login.demo_hint")} <code>demo1234</code></p>
          <div className="col gap-6 mt-8">
            {demo.map((d) => (
              <button key={d.email} className="btn" style={{ justifyContent: "space-between", height: "auto", padding: "10px 14px" }} onClick={() => submit(undefined, d.email, d.password)}>
                <span style={{ textAlign: "left" }}><b>{roleName(d.role)}</b><div className="tiny muted">{d.email}</div></span><ArrowRight size={16} />
              </button>
            ))}
            {!demo.length && <p className="muted small">{t("login.demo_off")}</p>}
          </div>
        </div>
      </div>
    </div>
  );
}
