import { useCallback, useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { CreditCard, Gift, Sparkles } from "lucide-react";
import { api } from "../lib/api";
import { amd, dt } from "../lib/format";
import { useT } from "../i18n";
import { Badge, Empty, Loading, useToast } from "../components/ui";
import { PlanCard, amdN, type CreditPack, type PricePlan } from "../components/Pricing";
import { PAY_TONE } from "../components/BillingAdmin";

interface Pay { id: string; purpose: string; item_key: string; interval: string; amount_amd: number; status: string; card: string | null; created_at: string; paid_at: string | null }
interface Bill {
  org: { id: string; name: string; kind: string }; can_pay: boolean; plan: PricePlan | null; seat_limit: number | null; interval: string | null; paid_until: string | null;
  trial_until: string | null; trial_used: boolean; assigned_by_platform: boolean;
  usage: { projects: number; seats: number; storage_bytes: number; credits: number; skus?: number };
  plans: PricePlan[]; credit_packs: CreditPack[]; credit_costs: Record<string, number>; trial: { days: number; credits: number; max_projects: number };
  credit_ledger: { at: string; delta: number; reason: string; operation: string }[]; payments: Pay[]; online_payments: boolean; credits_enforced: boolean;
}

function Meter({ label, used, limit, fmt = (n: number) => String(n) }: { label: string; used: number; limit?: number | null; fmt?: (n: number) => string }) {
  const { t } = useT();
  const pct = limit ? Math.min(100, (used / limit) * 100) : 0;
  return (
    <div className={`meter ${limit && used >= limit ? "over" : ""}`}>
      <div className="row between small"><span>{label}</span><b>{fmt(used)}{limit ? ` / ${fmt(limit)}` : ` · ${t("bill.unlimited")}`}</b></div>
      {limit ? <div className="bar"><i style={{ width: `${pct}%` }} /></div> : null}
    </div>
  );
}

/** Plan, usage and payments of the organisation; the head pays by card on Ameriabank's page. */
export default function Billing() {
  const { t, lang } = useT();
  const toast = useToast();
  const [sp, setSp] = useSearchParams();
  const [b, setB] = useState<Bill | null>(null);
  const [interval, setInterval] = useState<"month" | "year">("month");
  const [busy, setBusy] = useState("");
  const load = useCallback(() => api<Bill>("/billing").then(setB).catch((e) => toast((e as Error).message, true)), [toast]);
  useEffect(() => { load(); }, [load]);
  const returned = sp.get("status");
  const go = async (purpose: "plan" | "credits", key: string) => {
    const target = b?.plans.find((p) => p.key === key);
    // switching to a free plan introduces its limits at once — ask first
    if (purpose === "plan" && target && target.price_amd_month === 0 && !confirm(t("bill.confirm_free", { n: target.max_projects ?? 1 }))) return;
    setBusy(`${purpose}:${key}`);
    try {
      const r = await api<{ status: string; redirect_url: string | null }>("/billing/checkout", { method: "POST", json: { purpose, key, interval, lang } });
      if (r.redirect_url) { window.location.assign(r.redirect_url); return; }  // the bank's card page
      toast(t("bill.applied")); load();
    } catch (x) { toast((x as Error).message, true); } finally { setBusy(""); }
  };
  const trial = async () => { try { await api("/billing/trial", { method: "POST" }); toast(t("bill.trial_started")); load(); } catch (x) { toast((x as Error).message, true); } };
  if (!b) return <Loading />;
  const cur = b.plan;
  const supplier = b.org.kind === "supplier";
  const mb = (n: number) => (n >= 1e9 ? `${(n / 1e9).toFixed(1)} GB` : `${Math.round(n / 1e6)} MB`);
  const storageLimit = cur?.storage_gb ? cur.storage_gb * 1e9 : null;
  return (
    <div className="col gap-16">
      <div className="row between wrap gap-12"><div><h1>{t("bill.title")}</h1><p className="muted">{b.org.name}</p></div>
        <div className="seg" role="group" aria-label={t("bill.interval")}>{(["month", "year"] as const).map((k) => <button key={k} className={interval === k ? "on" : ""} aria-pressed={interval === k} onClick={() => setInterval(k)}>{t(`bil.interval.${k}`)}</button>)}</div></div>
      {returned && <div className={`alert ${returned === "paid" ? "sage" : returned === "redirected" ? "warn" : "danger"} small row between`} role="status">
        <span>{t(`bill.return.${["paid", "redirected", "declined"].includes(returned) ? returned : "other"}`)}</span><button className="btn sm ghost" onClick={() => { setSp({}); load(); }}>OK</button></div>}
      {!b.online_payments && <div className="alert info small">{t("bill.not_connected")}</div>}
      {!b.can_pay && <div className="alert info small">{t("bill.not_payer")}</div>}

      <section className="card pad col gap-12" aria-labelledby="cur-h">
        <div className="row between wrap"><h3 id="cur-h" className="row gap-6"><CreditCard size={18} /> {t("bill.current")}: {cur ? cur.name : t("bil.pilot")}</h3>
          <div className="row gap-6">{b.paid_until && <Badge tone="sage">{t("bill.paid_until", { d: dt(b.paid_until) })}</Badge>}
            {b.trial_until && new Date(b.trial_until) > new Date() && <Badge tone="warn">{t("bill.trial_until", { d: dt(b.trial_until) })}</Badge>}
            {b.assigned_by_platform && <Badge>{t("bill.assigned")}</Badge>}</div></div>
        {!cur && <p className="small muted" style={{ margin: 0 }}>{t("bill.pilot_hint")}</p>}
        <div className="grid g4">
          {supplier ? <Meter label={t("bill.m.skus")} used={b.usage.skus || 0} limit={cur?.sku_limit} /> : <Meter label={t("bill.m.projects")} used={b.usage.projects} limit={cur?.max_projects} />}
          <Meter label={t("bill.m.seats")} used={b.usage.seats} limit={b.seat_limit} />
          <Meter label={t("bill.m.storage")} used={b.usage.storage_bytes} limit={storageLimit} fmt={mb} />
          {!supplier && <Meter label={t("bill.m.credits")} used={b.usage.credits} />}
        </div>
        {!supplier && b.can_pay && !b.trial_used && cur?.key === "free" && <div><button className="btn" onClick={trial}><Gift size={15} /> {t("bill.trial_btn", { days: b.trial.days, credits: b.trial.credits })}</button></div>}
      </section>

      <section className="col gap-10" aria-labelledby="plans-h">
        <h2 id="plans-h">{t("bill.plans")}</h2>
        <div className="price-grid">
          {b.plans.map((p) => {
            const isCur = cur?.key === p.key;
            const yearOk = interval === "month" || p.price_amd_year != null;
            return <PlanCard key={p.key} plan={p} interval={interval} current={isCur} highlight={p.key === (supplier ? "supplier_growth" : "designer_pro")}
              action={p.custom ? <div className="small muted">{t("price.contact_hint")}</div>
                : <button className={`btn block ${isCur ? "" : "primary"}`} disabled={!b.can_pay || !yearOk || !!busy || (p.price_amd_month > 0 && !b.online_payments)}
                  onClick={() => go("plan", p.key)}>{busy === `plan:${p.key}` ? <span className="spinner" /> : isCur && p.price_amd_month > 0 ? t("bill.extend") : p.price_amd_month === 0 ? t("bill.choose_free") : t("bill.pay")}</button>} />;
          })}
        </div>
      </section>

      {!supplier && <section className="card pad col gap-10" aria-labelledby="packs-h">
        <h3 id="packs-h" className="row gap-6"><Sparkles size={18} /> {t("bill.packs")}</h3>
        <p className="tiny muted">{t("bill.packs_lead")}</p>
        <div className="price-grid">{b.credit_packs.map((c) => <div key={c.key} className="card flat pad col gap-6">
          <b>{t("bil.pack_n", { n: c.credits })}</b><div className="mono">{amdN(c.price_amd)}</div><div className="tiny muted">{t("bill.per_credit", { v: (c.price_amd / c.credits).toFixed(2) })} · {t("bill.valid", { n: c.validity_months ?? 12 })}</div>
          <button className="btn sm primary" disabled={!b.can_pay || !b.online_payments || !!busy} onClick={() => go("credits", c.key)}>{t("bill.buy")}</button></div>)}</div>
        <details className="small"><summary>{t("bill.costs")}</summary>
          <table className="table compact mt-8"><tbody>{Object.entries(b.credit_costs).map(([k, v]) => <tr key={k}><td>{t(`credit.op.${k}`)}</td><td className="right mono">{v}</td></tr>)}</tbody></table></details>
        {b.credit_ledger.length > 0 && <details className="small"><summary>{t("bill.ledger")}</summary>
          <table className="table compact mt-8"><tbody>{b.credit_ledger.map((e, i) => <tr key={i}><td className="tiny">{dt(e.at)}</td><td>{e.operation ? t(`credit.op.${e.operation}`) : t(`credit.reason.${e.reason}`)}</td>
            <td className="right mono" style={{ color: e.delta > 0 ? "var(--sage-ink)" : undefined }}>{e.delta > 0 ? `+${e.delta}` : e.delta}</td></tr>)}</tbody></table></details>}
      </section>}

      <section className="card col" aria-labelledby="hist-h">
        <h3 id="hist-h" style={{ padding: "16px 16px 0" }}>{t("bill.history")}</h3>
        {!b.payments.length ? <Empty>{t("bil.no_payments")}</Empty> : <table className="table compact"><thead><tr><th>{t("bil.col.date")}</th><th>{t("bil.col.item")}</th><th className="right">{t("bil.col.amount")}</th><th>{t("common.status")}</th><th>{t("bil.col.card")}</th></tr></thead>
          <tbody>{b.payments.map((p) => <tr key={p.id}><td className="tiny">{dt(p.created_at)}</td><td className="small">{t(`bil.purpose.${p.purpose}`)} · {p.item_key}{p.interval ? ` · ${t(`bil.interval.${p.interval}`)}` : ""}</td>
            <td className="right mono small">{amd(p.amount_amd)}</td><td><Badge tone={PAY_TONE[p.status]}>{t(`bil.status.${p.status}`)}</Badge></td><td className="tiny mono">{p.card || "—"}</td></tr>)}</tbody></table>}
      </section>
      <p className="tiny muted">{t("bill.legal")}</p>
    </div>
  );
}
