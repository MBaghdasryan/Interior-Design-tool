import { useEffect, useState } from "react";
import { Laptop, LogOut, MailCheck, ShieldCheck } from "lucide-react";
import { api } from "../lib/api";
import { dt } from "../lib/format";
import { useT } from "../i18n";
import { useMe } from "../components/AppShell";
import { Badge, useToast } from "../components/ui";

interface Sess { id: string; user_agent: string; ip: string; created_at: string; last_seen_at: string; current: boolean }

/** Profile, e-mail confirmation and active sessions (revoke one / all others). */
export default function Account() {
  const { t } = useT();
  const { me, reload } = useMe();
  const toast = useToast();
  const [name, setName] = useState(me?.name || "");
  const [sessions, setSessions] = useState<Sess[]>([]);
  const load = () => api<Sess[]>("/auth/sessions").then(setSessions).catch(() => {});
  useEffect(() => { load(); }, []);
  const run = async (fn: () => Promise<unknown>, ok: string) => { try { await fn(); toast(ok); } catch (x) { toast((x as Error).message, true); } };
  return (
    <div className="col gap-16" style={{ maxWidth: 760 }}>
      <h1>{t("acc.title")}</h1>
      <div className="card pad col gap-12">
        <h3>{t("acc.profile")}</h3>
        <div className="row gap-6 wrap"><b>{t("acc.email_status")}:</b> {me?.email}
          {me?.email_verified ? <Badge tone="sage">{t("acc.verified")}</Badge> : <Badge tone="warn">{t("acc.not_verified")}</Badge>}
          {!me?.email_verified && <button className="btn sm" onClick={() => run(() => api("/auth/verify-email/resend", { method: "POST" }), t("acc.resent"))}><MailCheck size={15} /> {t("acc.resend")}</button>}
        </div>
        <div className="row gap-6"><input className="input grow" aria-label={t("reg.name")} value={name} onChange={(e) => setName(e.target.value)} />
          <button className="btn" onClick={() => run(async () => { await api("/auth/me", { method: "PATCH", json: { name } }); await reload(); }, t("acc.saved"))}>{t("common.save")}</button></div>
      </div>
      <div className="card pad col gap-10">
        <div className="row between wrap"><h3 className="row gap-6"><ShieldCheck size={18} /> {t("acc.sessions")}</h3>
          <button className="btn sm" onClick={() => run(async () => { const r = await api<{ revoked: number }>("/auth/sessions/revoke-others", { method: "POST" }); toast(t("acc.revoked_n", { n: r.revoked })); load(); }, t("acc.revoked"))}>{t("acc.revoke_others")}</button></div>
        {sessions.map((s) => (
          <div key={s.id} className="row gap-10 small" style={{ borderTop: "1px solid var(--line)", paddingTop: 10 }}>
            <Laptop size={18} />
            <div className="grow"><b>{s.user_agent ? s.user_agent.slice(0, 80) : t("acc.unknown_device")}</b> {s.current && <Badge tone="sage">{t("acc.current")}</Badge>}
              <div className="tiny muted">{s.ip} · {t("acc.last_seen", { at: dt(s.last_seen_at) })}</div></div>
            {!s.current && <button className="btn sm ghost" onClick={() => run(async () => { await api(`/auth/sessions/${s.id}`, { method: "DELETE" }); load(); }, t("acc.revoked"))}><LogOut size={15} /> {t("acc.revoke")}</button>}
          </div>
        ))}
      </div>
    </div>
  );
}
