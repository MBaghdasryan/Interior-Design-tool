import { useEffect, useState } from "react";
import { Bell, Download, KeyRound, Laptop, LogOut, MailCheck, ShieldCheck, Trash2, UserRound } from "lucide-react";
import { api } from "../lib/api";
import { dt } from "../lib/format";
import { useT } from "../i18n";
import { useMe } from "../components/AppShell";
import { NOTIF_KINDS } from "../components/NotificationBell";
import { Badge, Switch, useToast } from "../components/ui";

interface Sess { id: string; user_agent: string; ip: string; created_at: string; last_seen_at: string; current: boolean }
interface Consent { granted: boolean; at: string }
interface NotifPrefs { kinds: Record<string, boolean>; email_digest: boolean }
interface Consents { terms?: { version: string; at: string }; marketing_emails?: Consent; product_analytics?: Consent }
const OPTIONAL_CONSENTS = ["marketing_emails", "product_analytics"] as const;

/** Profile, two-factor authentication, sessions, personal data (export, consents, deletion). */
export default function Account() {
  const { t } = useT();
  const { me, cfg, reload } = useMe();
  const toast = useToast();
  const [name, setName] = useState(me?.name || "");
  const [sessions, setSessions] = useState<Sess[]>([]);
  const [consents, setConsents] = useState<Consents>({});
  const [setup, setSetup] = useState<{ secret: string; qr_svg: string } | null>(null);
  const [code, setCode] = useState("");
  const [codes, setCodes] = useState<string[] | null>(null);
  const [prefs, setPrefs] = useState<NotifPrefs | null>(null);
  const [del, setDel] = useState({ open: false, password: "", code: "" });
  const load = () => { api<Sess[]>("/auth/sessions").then(setSessions).catch(() => {}); api<Consents>("/auth/me/consents").then(setConsents).catch(() => {}); api<NotifPrefs>("/auth/me/notification-prefs").then(setPrefs).catch(() => {}); };
  useEffect(() => { load(); }, []);
  const run = async (fn: () => Promise<unknown>, ok?: string) => { try { await fn(); if (ok) toast(ok); } catch (x) { toast((x as Error).message, true); } };
  const days = (cfg as unknown as { privacy_deletion_grace_days?: number })?.privacy_deletion_grace_days ?? 14;
  return (
    <div className="col gap-16" style={{ maxWidth: 820 }}>
      <h1>{t("acc.title")}</h1>
      {me?.mfa_enrollment_required && <div className="alert warn" role="alert"><ShieldCheck size={18} /> {t("mfa.enrol_required")}</div>}
      {me?.deletion_due_at && <div className="alert danger row between wrap" role="status"><span><Trash2 size={16} /> {t("priv.pending", { at: dt(me.deletion_due_at) })}</span>
        <button className="btn sm" onClick={() => run(async () => { await api("/auth/me/delete/cancel", { method: "POST" }); await reload(); }, t("priv.cancelled"))}>{t("priv.cancel")}</button></div>}

      <section className="card pad col gap-12" aria-labelledby="acc-profile">
        <h3 id="acc-profile" className="row gap-6"><UserRound size={18} /> {t("acc.profile")}</h3>
        <div className="row gap-6 wrap"><b>{t("acc.email_status")}:</b> {me?.email}
          {me?.email_verified ? <Badge tone="sage">{t("acc.verified")}</Badge> : <Badge tone="warn">{t("acc.not_verified")}</Badge>}
          {!me?.email_verified && <button className="btn sm" onClick={() => run(() => api("/auth/verify-email/resend", { method: "POST" }), t("acc.resent"))}><MailCheck size={15} /> {t("acc.resend")}</button>}
        </div>
        <div className="row gap-6"><input className="input grow" aria-label={t("reg.name")} value={name} onChange={(e) => setName(e.target.value)} />
          <button className="btn" onClick={() => run(async () => { await api("/auth/me", { method: "PATCH", json: { name } }); await reload(); }, t("acc.saved"))}>{t("common.save")}</button></div>
      </section>

      <section id="mfa" className="card pad col gap-12" aria-labelledby="acc-mfa">
        <div className="row between wrap"><h3 id="acc-mfa" className="row gap-6"><KeyRound size={18} /> {t("mfa.title")}</h3>
          <div className="row gap-6">{me?.mfa_required && <Badge tone="info">{t("mfa.required_note")}</Badge>}
            {me?.mfa_enabled ? <Badge tone="sage">{t("mfa.on")}</Badge> : <Badge tone="warn">{t("mfa.off")}</Badge>}</div></div>
        {codes && <div className="alert sage col gap-6" role="status"><b>{t("mfa.codes_title")}</b><span className="small">{t("mfa.codes_hint")}</span>
          <div className="grid g4 mono">{codes.map((c) => <code key={c}>{c}</code>)}</div></div>}
        {!me?.mfa_enabled && !setup && <div><button className="btn primary" onClick={() => run(async () => setSetup(await api("/auth/mfa/setup", { method: "POST" })))}>{t("mfa.start")}</button></div>}
        {!me?.mfa_enabled && setup && <div className="row gap-16 wrap" style={{ alignItems: "flex-start" }}>
          <div style={{ width: 180, background: "#fff", padding: 8, borderRadius: 8 }} aria-label="QR" dangerouslySetInnerHTML={{ __html: setup.qr_svg }} />
          <div className="col gap-8 grow" style={{ minWidth: 240 }}>
            <p className="small">{t("mfa.scan")}</p>
            <div className="tiny muted">{t("mfa.manual")} <code>{setup.secret}</code></div>
            <div className="row gap-6"><input className="input" inputMode="numeric" autoComplete="one-time-code" placeholder={t("mfa.code_ph")} aria-label={t("mfa.code_ph")} value={code} onChange={(e) => setCode(e.target.value.trim())} />
              <button className="btn primary" onClick={() => run(async () => { const r = await api<{ backup_codes: string[] }>("/auth/mfa/enable", { method: "POST", json: { code } }); setCodes(r.backup_codes); setSetup(null); setCode(""); await reload(); }, t("mfa.enabled_msg"))}>{t("mfa.confirm")}</button></div>
          </div>
        </div>}
        {me?.mfa_enabled && <div className="row gap-6 wrap">
          <input className="input" inputMode="numeric" autoComplete="one-time-code" placeholder={t("mfa.code_ph")} aria-label={t("mfa.code_ph")} value={code} onChange={(e) => setCode(e.target.value.trim())} style={{ width: 160 }} />
          <button className="btn" onClick={() => run(async () => { const r = await api<{ backup_codes: string[] }>("/auth/mfa/backup-codes", { method: "POST", json: { code } }); setCodes(r.backup_codes); setCode(""); })}>{t("mfa.regenerate")}</button>
          {!me?.mfa_required && <button className="btn ghost" onClick={() => run(async () => { await api("/auth/mfa/disable", { method: "POST", json: { code } }); setCode(""); setCodes(null); await reload(); }, t("mfa.disabled_msg"))}>{t("mfa.disable")}</button>}
        </div>}
      </section>

      <section className="card pad col gap-10" aria-labelledby="acc-sessions">
        <div className="row between wrap"><h3 id="acc-sessions" className="row gap-6"><ShieldCheck size={18} /> {t("acc.sessions")}</h3>
          <button className="btn sm" onClick={() => run(async () => { const r = await api<{ revoked: number }>("/auth/sessions/revoke-others", { method: "POST" }); toast(t("acc.revoked_n", { n: r.revoked })); load(); })}>{t("acc.revoke_others")}</button></div>
        {sessions.map((s) => (
          <div key={s.id} className="row gap-10 small" style={{ borderTop: "1px solid var(--line)", paddingTop: 10 }}>
            <Laptop size={18} />
            <div className="grow"><b>{s.user_agent ? s.user_agent.slice(0, 80) : t("acc.unknown_device")}</b> {s.current && <Badge tone="sage">{t("acc.current")}</Badge>}
              <div className="tiny muted">{s.ip} · {t("acc.last_seen", { at: dt(s.last_seen_at) })}</div></div>
            {!s.current && <button className="btn sm ghost" onClick={() => run(async () => { await api(`/auth/sessions/${s.id}`, { method: "DELETE" }); load(); }, t("acc.revoked"))}><LogOut size={15} /> {t("acc.revoke")}</button>}
          </div>
        ))}
      </section>

      {prefs && <section id="notifications" className="card pad col gap-10" aria-labelledby="acc-notif">
        <h3 id="acc-notif" className="row gap-6"><Bell size={18} /> {t("common.notifications")}</h3>
        <p className="small muted">{t("notif.prefs_hint")}</p>
        {NOTIF_KINDS.map((k) => (
          <div key={k} className="row between small"><span>{t(`notif.pref.${k}`)}</span>
            <Switch on={prefs.kinds[k] !== false} label={t(`notif.pref.${k}`)} onChange={(v) => run(async () => setPrefs(await api<NotifPrefs>("/auth/me/notification-prefs", { method: "PUT", json: { kinds: { [k]: v } } })))} /></div>
        ))}
        <div className="row between small" style={{ borderTop: "1px solid var(--line)", paddingTop: 10 }}><span>{t("notif.pref.email_digest")}</span>
          <Switch on={prefs.email_digest} label={t("notif.pref.email_digest")} onChange={(v) => run(async () => setPrefs(await api<NotifPrefs>("/auth/me/notification-prefs", { method: "PUT", json: { email_digest: v } })))} /></div>
      </section>}

      <section className="card pad col gap-12" aria-labelledby="acc-privacy">
        <h3 id="acc-privacy" className="row gap-6"><Download size={18} /> {t("priv.title")}</h3>
        <div className="row gap-10 wrap"><a className="btn" href="/api/v1/auth/me/export"><Download size={15} /> {t("priv.export")}</a><span className="small muted">{t("priv.export_hint")}</span></div>
        <b className="small">{t("priv.consents")}</b>
        {consents.terms && <div className="small muted">{t("priv.consent.terms", { v: consents.terms.version, at: dt(consents.terms.at) })}</div>}
        {OPTIONAL_CONSENTS.map((k) => (
          <div key={k} className="row between small"><span>{t(`priv.consent.${k}`)}</span>
            <Switch on={!!consents[k]?.granted} label={t(`priv.consent.${k}`)} onChange={(v) => run(async () => setConsents(await api<Consents>("/auth/me/consents", { method: "PUT", json: { [k]: v } })))} /></div>
        ))}
        {!me?.deletion_due_at && <div className="col gap-8" style={{ borderTop: "1px solid var(--line)", paddingTop: 12 }}>
          {!del.open ? <div><button className="btn ghost" style={{ color: "var(--danger)" }} onClick={() => setDel({ ...del, open: true })}><Trash2 size={15} /> {t("priv.delete")}</button></div> : <>
            <p className="small">{t("priv.delete_hint", { days })}</p>
            <div className="row gap-6 wrap">
              <input className="input" type="password" autoComplete="current-password" placeholder={t("login.password")} aria-label={t("login.password")} value={del.password} onChange={(e) => setDel({ ...del, password: e.target.value })} />
              {me?.mfa_enabled && <input className="input" inputMode="numeric" placeholder={t("mfa.code_ph")} aria-label={t("mfa.code_ph")} value={del.code} onChange={(e) => setDel({ ...del, code: e.target.value.trim() })} style={{ width: 150 }} />}
              <button className="btn" style={{ background: "var(--danger)", color: "#fff" }} onClick={() => run(async () => { await api("/auth/me/delete", { method: "POST", json: { password: del.password, code: del.code || null } }); setDel({ open: false, password: "", code: "" }); await reload(); })}>{t("priv.delete_confirm")}</button>
              <button className="btn ghost" onClick={() => setDel({ open: false, password: "", code: "" })}>{t("common.cancel")}</button>
            </div>
          </>}
        </div>}
      </section>
    </div>
  );
}
