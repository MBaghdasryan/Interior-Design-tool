import { useCallback, useEffect, useState } from "react";
import { CreditCard, KeyRound, RefreshCw, RotateCcw, Save, XCircle } from "lucide-react";
import { api, type Schemas } from "../lib/api";
import { amd, dt } from "../lib/format";
import { useT } from "../i18n";
import { Badge, Empty, Loading, Switch, useToast } from "./ui";

type Tariffs = Schemas["Tariffs"];
type Plan = Schemas["Plan"];
interface Vpos { client_id: string; username: string; password_set: boolean; mode: string; base_url: string; effective_base: string; order_id_offset: number; configured: boolean }
interface Pay { id: string; org_name: string; purpose: string; item_key: string; interval: string; amount_amd: number; status: string; order_id: number | null; card: string | null;
  refunded_amd: number; created_at: string; paid_at: string | null }
interface Org { id: string; name: string; kind: string; plan: string | null }
interface App { id: string; company: string; contact_name: string; email: string; phone: string; website: string; city: string; kind: string; sku_count: number | null;
  categories: string[]; message: string; status: string; note: string; created_at: string }
export const PAY_TONE: Record<string, string> = { paid: "sage", redirected: "warn", created: "", declined: "danger", error: "danger", refunded: "info", cancelled: "" };

function useRun(reload?: () => void) {
  const { t } = useT();
  const toast = useToast();
  return async (fn: () => Promise<unknown>, ok?: string) => { try { await fn(); toast(ok || t("fin.saved")); reload?.(); } catch (x) { toast((x as Error).message, true); } };
}

/** Platform → Tariffs & payments: Ameriabank vPOS credentials, the price catalogue, plans of organisations, card payments. */
export default function BillingAdmin() {
  return <div className="col gap-16"><VposCard /><PaymentsCard /><PricingCard /></div>;
}

function VposCard() {
  const { t } = useT();
  const [v, setV] = useState<Vpos | null>(null);
  const [pw, setPw] = useState("");
  const load = useCallback(() => api<Vpos>("/admin/billing/vpos").then(setV).catch(() => {}), []);
  useEffect(() => { load(); }, [load]);
  const run = useRun(load);
  if (!v) return <Loading />;
  const save = () => run(async () => { await api("/admin/billing/vpos", { method: "PUT", json: { client_id: v.client_id, username: v.username, password: pw || null, mode: v.mode, base_url: v.base_url, order_id_offset: v.order_id_offset } }); setPw(""); });
  return (
    <section className="card pad col gap-10" aria-labelledby="vpos-h">
      <div className="row between wrap"><h3 id="vpos-h" className="row gap-6"><CreditCard size={18} /> {t("bil.vpos_title")}</h3>
        <Badge tone={v.configured ? "sage" : "warn"}>{v.configured ? t("bil.vpos_on") : t("bil.vpos_off")}</Badge></div>
      <p className="tiny muted">{t("bil.vpos_lead")}</p>
      <div className="grid g3">
        <label className="field"><span>Client ID</span><input className="input mono" autoComplete="off" value={v.client_id} onChange={(e) => setV({ ...v, client_id: e.target.value })} /></label>
        <label className="field"><span>Username</span><input className="input mono" autoComplete="off" value={v.username} onChange={(e) => setV({ ...v, username: e.target.value })} /></label>
        <label className="field"><span>Password</span><input className="input mono" type="password" autoComplete="new-password" placeholder={v.password_set ? t("bil.pw_kept") : ""} value={pw} onChange={(e) => setPw(e.target.value)} /></label>
        <label className="field"><span>{t("bil.mode")}</span><select className="select input" value={v.mode} onChange={(e) => setV({ ...v, mode: e.target.value })}>
          <option value="test">{t("bil.mode_test")}</option><option value="live">{t("bil.mode_live")}</option></select></label>
        <label className="field"><span>{t("bil.order_offset")}</span><input className="input" inputMode="numeric" value={v.order_id_offset} onChange={(e) => setV({ ...v, order_id_offset: Number(e.target.value) || 0 })} /></label>
        <label className="field"><span>{t("bil.base_url")}</span><input className="input mono" placeholder={v.effective_base} value={v.base_url} onChange={(e) => setV({ ...v, base_url: e.target.value })} /></label>
      </div>
      <div className="tiny muted">{t("bil.back_url")} <code>{location.origin}/api/v1/billing/vpos/return</code></div>
      <div><button className="btn primary" disabled={!v.client_id || !v.username || (!pw && !v.password_set)} onClick={save}><KeyRound size={15} /> {t("common.save")}</button></div>
    </section>
  );
}

function PaymentsCard() {
  const { t } = useT();
  const [rows, setRows] = useState<Pay[] | null>(null);
  const load = useCallback(() => api<Pay[]>("/admin/billing/payments").then(setRows).catch(() => setRows([])), []);
  useEffect(() => { load(); }, [load]);
  const run = useRun(load);
  const refund = (p: Pay) => {
    const left = p.amount_amd - p.refunded_amd;
    const a = prompt(t("bil.refund_prompt", { max: left }), String(left));
    if (!a) return;
    const reason = prompt(t("bil.reason_prompt"));
    if (!reason || reason.length < 3) return;
    run(() => api(`/admin/billing/payments/${p.id}/refund`, { method: "POST", json: { amount_amd: Number(a), reason } }));
  };
  const cancel = (p: Pay) => { const reason = prompt(t("bil.reason_prompt")); if (reason && reason.length >= 3) run(() => api(`/admin/billing/payments/${p.id}/cancel`, { method: "POST", json: { reason } })); };
  return (
    <section className="card col" aria-labelledby="bpay-h">
      <div className="row between" style={{ padding: 16 }}><h3 id="bpay-h">{t("bil.payments")}</h3><button className="btn sm ghost" onClick={load}><RefreshCw size={14} /> {t("bil.reload")}</button></div>
      {!rows ? <Loading /> : !rows.length ? <Empty>{t("bil.no_payments")}</Empty> : <div style={{ overflow: "auto" }}>
        <table className="table compact"><thead><tr><th>{t("bil.col.date")}</th><th>{t("mg.col.org")}</th><th>{t("bil.col.item")}</th><th className="right">{t("bil.col.amount")}</th><th>{t("common.status")}</th><th>{t("bil.col.card")}</th><th /></tr></thead>
          <tbody>{rows.map((p) => <tr key={p.id}>
            <td className="tiny">{dt(p.created_at)}<div className="muted">#{p.order_id ?? "—"}</div></td><td className="small">{p.org_name}</td>
            <td className="small">{t(`bil.purpose.${p.purpose}`)} · {p.item_key}{p.interval ? ` · ${t(`bil.interval.${p.interval}`)}` : ""}</td>
            <td className="right mono small">{amd(p.amount_amd)}{p.refunded_amd ? <div className="tiny muted">−{amd(p.refunded_amd)}</div> : null}</td>
            <td><Badge tone={PAY_TONE[p.status]}>{t(`bil.status.${p.status}`)}</Badge></td><td className="tiny mono">{p.card || "—"}</td>
            <td><div className="row gap-4">
              {p.status === "redirected" && <button className="icon-btn" title={t("bil.sync")} aria-label={t("bil.sync")} onClick={() => run(() => api(`/billing/payments/${p.id}/sync`, { method: "POST" }))}><RefreshCw size={14} /></button>}
              {p.status === "paid" && <button className="icon-btn" title={t("bil.refund")} aria-label={t("bil.refund")} onClick={() => refund(p)}><RotateCcw size={14} /></button>}
              {(p.status === "paid" || p.status === "redirected") && <button className="icon-btn" title={t("bil.cancel")} aria-label={t("bil.cancel")} onClick={() => cancel(p)}><XCircle size={14} /></button>}
            </div></td></tr>)}</tbody></table></div>}
    </section>
  );
}

const PLAN_NUM: [keyof Plan, string][] = [["price_amd_month", "bil.f.month"], ["price_amd_year", "bil.f.year"], ["max_projects", "bil.f.projects"], ["seats", "bil.f.seats"],
  ["storage_gb", "bil.f.storage"], ["ai_credits_month", "bil.f.credits"], ["sku_limit", "bil.f.skus"], ["commission_pct", "bil.f.commission"]];

function PricingCard() {
  const { t } = useT();
  const [tar, setTar] = useState<Tariffs | null>(null);
  const [orgs, setOrgs] = useState<Org[]>([]);
  const [list, setList] = useState<"bureau_plans" | "supplier_plans">("bureau_plans");
  const load = useCallback(() => { api<Tariffs>("/admin/tariffs").then(setTar).catch(() => {}); api<Org[]>("/admin/orgs").then((o) => setOrgs(o.filter((x) => x.kind !== "platform"))).catch(() => {}); }, []);
  useEffect(() => { load(); }, [load]);
  const run = useRun(load);
  if (!tar) return <Loading />;
  const plans = (tar[list] || []) as Plan[];
  const setPlan = (i: number, patch: Partial<Plan>) => setTar({ ...tar, [list]: plans.map((p, j) => (j === i ? { ...p, ...patch } : p)) });
  const num = (v: string) => (v === "" ? null : Number(v));
  const save = () => run(() => api("/admin/tariffs", { method: "PUT", json: tar }));
  const grant = (o: Org) => {
    const n = Number(prompt(t("bil.grant_prompt", { org: o.name })) || 0);
    if (!n) return;
    const reason = prompt(t("bil.reason_prompt"));
    if (reason && reason.length >= 3) run(() => api(`/admin/orgs/${o.id}/credits`, { method: "POST", json: { credits: n, reason } }));
  };
  return (
    <>
      <section className="card pad col gap-10" aria-labelledby="pricing-h">
        <div className="row between wrap"><h3 id="pricing-h">{t("bil.catalogue")} <Badge>{tar.version}</Badge></h3><button className="btn sm primary" onClick={save}><Save size={14} /> {t("common.save")}</button></div>
        <p className="tiny muted">{t("bil.catalogue_lead")}</p>
        <div className="row gap-4">{(["bureau_plans", "supplier_plans"] as const).map((k) => <button key={k} className={`chip ${list === k ? "on" : ""}`} aria-pressed={list === k} onClick={() => setList(k)}>{t(`bil.list.${k}`)}</button>)}</div>
        <div style={{ overflow: "auto" }}>
          <table className="table compact"><thead><tr><th>{t("fin.plan_name")}</th>{PLAN_NUM.map(([, k]) => <th key={k}>{t(k)}</th>)}<th>{t("bil.f.custom")}</th></tr></thead>
            <tbody>{plans.map((p, i) => <tr key={p.key}>
              <td><input className="input" style={{ width: 150 }} aria-label={t("fin.plan_name")} value={p.name} onChange={(e) => setPlan(i, { name: e.target.value })} /><div className="tiny muted mono">{p.key}</div></td>
              {PLAN_NUM.map(([f, k]) => <td key={f}><input className="input" style={{ width: 92 }} inputMode="decimal" aria-label={`${p.name}: ${t(k)}`} placeholder="—" value={(p[f] as number | null | undefined) ?? ""}
                onChange={(e) => setPlan(i, { [f]: f === "price_amd_month" || f === "ai_credits_month" ? Number(e.target.value) || 0 : num(e.target.value) } as Partial<Plan>)} /></td>)}
              <td><Switch on={!!p.custom} label={t("bil.f.custom")} onChange={(v) => setPlan(i, { custom: v })} /></td></tr>)}</tbody></table>
        </div>
        <b className="small">{t("bil.packs")}</b>
        <div className="row gap-8 wrap">{tar.credit_packs?.map((c, i) => <label key={c.key} className="col gap-4"><span className="tiny muted">{t("bil.pack_n", { n: c.credits })}</span>
          <input className="input" style={{ width: 110 }} inputMode="numeric" value={c.price_amd} onChange={(e) => setTar({ ...tar, credit_packs: tar.credit_packs!.map((x, j) => (j === i ? { ...x, price_amd: Number(e.target.value) || 0 } : x)) })} /></label>)}</div>
        <div className="divider" />
        <div className="row gap-16 wrap small" style={{ alignItems: "end" }}>
          <label className="row gap-6"><Switch on={!!tar.credits_enforced} label={t("bil.enforce")} onChange={(v) => setTar({ ...tar, credits_enforced: v })} /> {t("bil.enforce")}</label>
          <label className="col gap-4"><span className="tiny muted">{t("bil.default_plan")}</span><select className="select input" value={tar.default_plan || ""} onChange={(e) => setTar({ ...tar, default_plan: e.target.value || null })}>
            <option value="">{t("bil.pilot")}</option>{[...(tar.bureau_plans || []), ...(tar.supplier_plans || [])].filter((p) => !p.custom).map((p) => <option key={p.key} value={p.key}>{p.name}</option>)}</select></label>
          <label className="col gap-4"><span className="tiny muted">{t("bil.trial_days")}</span><input className="input" style={{ width: 80 }} inputMode="numeric" value={tar.trial?.days ?? 14} onChange={(e) => setTar({ ...tar, trial: { ...tar.trial!, days: Number(e.target.value) || 0 } })} /></label>
          <label className="col gap-4"><span className="tiny muted">{t("bil.trial_credits")}</span><input className="input" style={{ width: 80 }} inputMode="numeric" value={tar.trial?.credits ?? 50} onChange={(e) => setTar({ ...tar, trial: { ...tar.trial!, credits: Number(e.target.value) || 0 } })} /></label>
          <label className="col gap-4"><span className="tiny muted">{t("fin.lead_fee")}</span><input className="input" style={{ width: 110 }} inputMode="numeric" value={tar.lead_fee_amd ?? 0} onChange={(e) => setTar({ ...tar, lead_fee_amd: Number(e.target.value) || 0 })} /></label>
        </div>
        <p className="tiny muted">{t("bil.enforce_hint")}</p>
      </section>
      <section className="card pad col gap-8" aria-labelledby="orgplans-h">
        <h3 id="orgplans-h">{t("bil.org_plans")}</h3>
        <p className="tiny muted">{t("bil.org_plans_hint")}</p>
        {orgs.map((o) => {
          const opts = (o.kind === "supplier" ? tar.supplier_plans : tar.bureau_plans) || [];
          return <div key={o.id} className="row between small wrap gap-6"><span>{o.name} <span className="muted">· {t(`mg.kind.${o.kind}`)}</span></span>
            <div className="row gap-6">
              <select className="select input" style={{ width: 200 }} aria-label={`${o.name}: ${t("bil.plan")}`} value={o.plan || ""} onChange={(e) => run(() => api(`/admin/orgs/${o.id}/plan`, { method: "PUT", json: { plan: e.target.value || null } }))}>
                <option value="">{t("bil.pilot")}</option>{opts.map((p) => <option key={p.key} value={p.key}>{p.name}</option>)}</select>
              {o.kind === "bureau" && <button className="btn sm ghost" onClick={() => grant(o)}>{t("bil.grant")}</button>}
            </div></div>;
        })}
      </section>
    </>
  );
}

/** «Become a supplier» applications from the public site. Approval creates the organisation and invites the contact. */
export function ApplicationsAdmin() {
  const { t } = useT();
  const [rows, setRows] = useState<App[] | null>(null);
  const [status, setStatus] = useState("new");
  const load = useCallback(() => api<App[]>(`/admin/supplier-applications?status=${status}`).then(setRows).catch(() => setRows([])), [status]);
  useEffect(() => { load(); }, [load]);
  const run = useRun(load);
  return (
    <div className="col gap-10">
      <div className="row gap-4">{["new", "approved", "rejected"].map((s) => <button key={s} className={`chip ${status === s ? "on" : ""}`} aria-pressed={status === s} onClick={() => setStatus(s)}>{t(`app.status.${s}`)}</button>)}</div>
      {!rows ? <Loading /> : !rows.length ? <Empty>{t("app.empty")}</Empty> : rows.map((a) => (
        <article key={a.id} className="card pad col gap-6">
          <div className="row between wrap"><b>{a.company}</b><span className="tiny muted">{dt(a.created_at)}</span></div>
          <div className="small">{a.contact_name} · <a href={`mailto:${a.email}`}>{a.email}</a>{a.phone ? ` · ${a.phone}` : ""}</div>
          <div className="tiny muted">{[t(`sob.kind.${a.kind}`), a.city, a.website, a.sku_count != null ? t("app.skus", { n: a.sku_count }) : ""].filter(Boolean).join(" · ")}</div>
          {a.message && <p className="small" style={{ margin: 0 }}>{a.message}</p>}
          {a.status === "new" ? <div className="row gap-6">
            <button className="btn sm primary" onClick={() => confirm(t("app.confirm_approve", { name: a.company })) && run(() => api(`/admin/supplier-applications/${a.id}/decision`, { method: "POST", json: { decision: "approved" } }), t("app.approved"))}>{t("app.approve")}</button>
            <button className="btn sm" onClick={() => { const note = prompt(t("app.reject_note")); if (note !== null) run(() => api(`/admin/supplier-applications/${a.id}/decision`, { method: "POST", json: { decision: "rejected", note } })); }}>{t("app.reject")}</button>
          </div> : <Badge tone={a.status === "approved" ? "sage" : "danger"}>{t(`app.status.${a.status}`)}</Badge>}
        </article>))}
    </div>
  );
}
