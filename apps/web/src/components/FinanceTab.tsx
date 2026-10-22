import { useCallback, useEffect, useState } from "react";
import { Download, Plus, Trash2 } from "lucide-react";
import { api, type Schemas } from "../lib/api";
import { amd } from "../lib/format";
import { useT } from "../i18n";
import { Badge, useToast } from "./ui";

interface Ledger { balances: Record<string, number>; reconcile: { balanced: boolean; transactions: number; payments_match_cash: boolean; captured_amd: number; cash_received_amd: number; refunded_amd: number };
  revenue: Record<string, number>; payments: { provider: string; configured: boolean } }
interface Revenue { streams: string[]; totals: Record<string, number>; by_month: Record<string, Record<string, number>> }
interface Org { id: string; name: string; kind: string; plan: string | null }
type Tariffs = Schemas["Tariffs"];
type Plan = Schemas["Plan"];
const MANUAL_STREAMS = ["subscription", "credits", "procurement", "manufacturer", "leads", "white_label", "exports"];

/** Platform finance: immutable ledger with reconciliation and export, revenue by stream, tariffs and commission/tax rules. */
export default function FinanceTab() {
  const { t } = useT();
  const toast = useToast();
  const [lg, setLg] = useState<Ledger | null>(null);
  const [rev, setRev] = useState<Revenue | null>(null);
  const [tar, setTar] = useState<Tariffs | null>(null);
  const [cs, setCs] = useState<{ tax_rate_pct: number; designer_commission_pct: number } | null>(null);
  const [orgs, setOrgs] = useState<Org[]>([]);
  const [manual, setManual] = useState({ stream: "subscription", amount_amd: "", reference: "" });
  const load = useCallback(() => {
    api<Ledger>("/admin/ledger").then(setLg).catch(() => {});
    api<Revenue>("/admin/revenue").then(setRev).catch(() => {});
    api<Tariffs>("/admin/tariffs").then(setTar).catch(() => {});
    api("/admin/commerce-settings").then(setCs).catch(() => {});
    api<Org[]>("/admin/orgs").then((o) => setOrgs(o.filter((x) => x.kind === "bureau"))).catch(() => {});
  }, []);
  useEffect(() => { load(); }, [load]);
  const run = async (fn: () => Promise<unknown>) => { try { await fn(); toast(t("fin.saved")); load(); } catch (x) { toast((x as Error).message, true); } };
  if (!lg || !tar || !cs) return null;
  const plans = tar.bureau_plans || [];
  const setPlan = (i: number, patch: Partial<Plan>) => setTar({ ...tar, bureau_plans: plans.map((p, j) => (j === i ? { ...p, ...patch } : p)) });
  const num = (v: string) => (v === "" ? null : Number(v));
  return (
    <div className="col gap-12">
      <div className="grid g2" style={{ alignItems: "start" }}>
        <section className="card pad col gap-8" aria-labelledby="fin-ledger">
          <div className="row between wrap"><h3 id="fin-ledger">{t("fin.ledger")}</h3>
            <div className="row gap-6"><a className="btn sm" href="/api/v1/admin/ledger/export.csv"><Download size={14} /> CSV</a><a className="btn sm" href="/api/v1/admin/ledger/export.xlsx"><Download size={14} /> XLSX</a></div></div>
          <div className="row gap-6 wrap">
            <Badge tone={lg.reconcile.balanced ? "sage" : "danger"}>{lg.reconcile.balanced ? t("fin.balanced") : t("fin.unbalanced")}</Badge>
            <Badge tone={lg.reconcile.payments_match_cash ? "sage" : "danger"}>{lg.reconcile.payments_match_cash ? t("fin.payments_match") : t("fin.payments_mismatch")}</Badge>
            <Badge tone={lg.payments.configured ? "sage" : "warn"}>{lg.payments.configured ? t("fin.provider", { p: lg.payments.provider }) : t("pr.pay.integration_pending")}</Badge>
          </div>
          <div className="tiny muted">{t("fin.txns", { n: lg.reconcile.transactions })}</div>
          <table className="table compact"><thead><tr><th>{t("fin.account")}</th><th className="right">{t("fin.balance")}</th></tr></thead>
            <tbody>{Object.entries(lg.balances).map(([a, b]) => <tr key={a}><td className="small mono">{a}</td><td className="right mono small">{amd(b)}</td></tr>)}</tbody></table>
          {!Object.keys(lg.balances).length && <div className="small muted">{t("fin.empty")}</div>}
        </section>
        <section className="card pad col gap-8" aria-labelledby="fin-rev">
          <h3 id="fin-rev">{t("fin.revenue")}</h3>
          {rev && <table className="table compact"><tbody>{rev.streams.map((s) => <tr key={s}><td className="small">{t(`fin.stream.${s}`)}</td><td className="right mono small">{amd(rev.totals[s] || 0)}</td></tr>)}</tbody></table>}
          {rev && Object.keys(rev.by_month).length > 0 && <div className="tiny muted">{Object.entries(rev.by_month).map(([mth, v]) => `${mth}: ${amd(Object.values(v).reduce((a, b) => a + b, 0))}`).join(" · ")}</div>}
          <b className="small">{t("fin.manual")}</b>
          <p className="tiny muted">{t("fin.manual_hint")}</p>
          <div className="row gap-6 wrap">
            <select className="select input" aria-label={t("fin.stream_label")} value={manual.stream} onChange={(e) => setManual({ ...manual, stream: e.target.value })}>{MANUAL_STREAMS.map((s) => <option key={s} value={s}>{t(`fin.stream.${s}`)}</option>)}</select>
            <input className="input" style={{ width: 130 }} inputMode="numeric" aria-label={t("fin.amount")} placeholder={t("fin.amount")} value={manual.amount_amd} onChange={(e) => setManual({ ...manual, amount_amd: e.target.value })} />
            <input className="input grow" aria-label={t("fin.reference")} placeholder={t("fin.reference")} value={manual.reference} onChange={(e) => setManual({ ...manual, reference: e.target.value })} />
            <button className="btn sm" disabled={!manual.amount_amd || manual.reference.length < 3} onClick={() => run(async () => { await api("/admin/revenue/manual", { method: "POST", json: { ...manual, amount_amd: Number(manual.amount_amd) } }); setManual({ ...manual, amount_amd: "", reference: "" }); })}>{t("fin.record")}</button>
          </div>
        </section>
      </div>

      <section className="card pad col gap-8" aria-labelledby="fin-tariffs">
        <div className="row between wrap"><h3 id="fin-tariffs">{t("fin.tariffs")}</h3><button className="btn sm primary" onClick={() => run(() => api("/admin/tariffs", { method: "PUT", json: tar }))}>{t("common.save")}</button></div>
        <p className="tiny muted">{t("fin.tariffs_hint")}</p>
        <table className="table compact"><thead><tr><th>{t("fin.plan_key")}</th><th>{t("fin.plan_name")}</th><th>{t("fin.plan_price")}</th><th>{t("fin.plan_projects")}</th><th>{t("fin.plan_credits")}</th><th /></tr></thead>
          <tbody>{plans.map((p, i) => <tr key={i}>
            <td><input className="input" style={{ width: 90 }} aria-label={t("fin.plan_key")} value={p.key} onChange={(e) => setPlan(i, { key: e.target.value })} /></td>
            <td><input className="input" aria-label={t("fin.plan_name")} value={p.name} onChange={(e) => setPlan(i, { name: e.target.value })} /></td>
            <td><input className="input" style={{ width: 110 }} inputMode="numeric" aria-label={t("fin.plan_price")} value={p.price_amd_month} onChange={(e) => setPlan(i, { price_amd_month: Number(e.target.value) || 0 })} /></td>
            <td><input className="input" style={{ width: 80 }} inputMode="numeric" aria-label={t("fin.plan_projects")} placeholder="∞" value={p.max_projects ?? ""} onChange={(e) => setPlan(i, { max_projects: num(e.target.value) })} /></td>
            <td><input className="input" style={{ width: 90 }} inputMode="numeric" aria-label={t("fin.plan_credits")} value={p.ai_credits_month ?? 0} onChange={(e) => setPlan(i, { ai_credits_month: Number(e.target.value) || 0 })} /></td>
            <td><button className="icon-btn" aria-label={t("common.delete")} onClick={() => setTar({ ...tar, bureau_plans: plans.filter((_, j) => j !== i) })}><Trash2 size={15} /></button></td></tr>)}</tbody></table>
        <div><button className="btn sm ghost" onClick={() => setTar({ ...tar, bureau_plans: [...plans, { key: `plan_${plans.length + 1}`, name: "", price_amd_month: 0, max_projects: null, ai_credits_month: 0 }] })}><Plus size={14} /> {t("fin.add_plan")}</button></div>
        <div className="row gap-12 wrap small">
          <label className="col gap-4"><span className="tiny muted">{t("fin.procurement_fee")}</span><div className="row gap-4">
            <select className="select input" aria-label={t("fin.procurement_fee")} value={tar.procurement_fee?.mode || "off"} onChange={(e) => setTar({ ...tar, procurement_fee: { ...tar.procurement_fee, mode: e.target.value as "pct" | "fixed" | "off" } })}>{["off", "pct", "fixed"].map((x) => <option key={x} value={x}>{t(`fin.mode.${x}`)}</option>)}</select>
            <input className="input" style={{ width: 90 }} inputMode="decimal" aria-label={t("fin.value")} value={tar.procurement_fee?.value ?? 0} onChange={(e) => setTar({ ...tar, procurement_fee: { ...tar.procurement_fee, value: Number(e.target.value) || 0 } })} /></div></label>
          <label className="col gap-4"><span className="tiny muted">{t("fin.lead_fee")}</span><input className="input" style={{ width: 110 }} inputMode="numeric" value={tar.lead_fee_amd ?? 0} onChange={(e) => setTar({ ...tar, lead_fee_amd: Number(e.target.value) || 0 })} /></label>
          <label className="col gap-4"><span className="tiny muted">{t("fin.wl_setup")}</span><input className="input" style={{ width: 120 }} inputMode="numeric" value={tar.white_label_setup_amd ?? 0} onChange={(e) => setTar({ ...tar, white_label_setup_amd: Number(e.target.value) || 0 })} /></label>
          <label className="col gap-4"><span className="tiny muted">{t("fin.wl_license")}</span><input className="input" style={{ width: 120 }} inputMode="numeric" value={tar.white_label_license_amd_month ?? 0} onChange={(e) => setTar({ ...tar, white_label_license_amd_month: Number(e.target.value) || 0 })} /></label>
          {["album_pdf", "dwg", "ifc"].map((k) => <label key={k} className="col gap-4"><span className="tiny muted">{t("fin.export_price", { k: k.toUpperCase() })}</span>
            <input className="input" style={{ width: 100 }} inputMode="numeric" value={(tar.export_prices_amd || {})[k] ?? ""} onChange={(e) => setTar({ ...tar, export_prices_amd: { ...(tar.export_prices_amd || {}), [k]: Number(e.target.value) || 0 } })} /></label>)}
        </div>
      </section>

      <div className="grid g2" style={{ alignItems: "start" }}>
        <section className="card pad col gap-8" aria-labelledby="fin-rules">
          <div className="row between"><h3 id="fin-rules">{t("fin.rules")}</h3><button className="btn sm" onClick={() => run(() => api("/admin/commerce-settings", { method: "PUT", json: cs }))}>{t("common.save")}</button></div>
          <label className="row between small"><span>{t("fin.tax_rate")}</span><input className="input" style={{ width: 90 }} inputMode="decimal" value={cs.tax_rate_pct} onChange={(e) => setCs({ ...cs, tax_rate_pct: Number(e.target.value) || 0 })} /></label>
          <label className="row between small"><span>{t("fin.designer_pct")}</span><input className="input" style={{ width: 90 }} inputMode="decimal" value={cs.designer_commission_pct} onChange={(e) => setCs({ ...cs, designer_commission_pct: Number(e.target.value) || 0 })} /></label>
        </section>
        <section className="card pad col gap-8" aria-labelledby="fin-orgs">
          <h3 id="fin-orgs">{t("fin.org_plans")}</h3>
          {orgs.map((o) => <label key={o.id} className="row between small"><span>{o.name}</span>
            <select className="select input" style={{ width: 180 }} value={o.plan || ""} onChange={(e) => run(() => api(`/admin/orgs/${o.id}/plan`, { method: "PUT", json: { plan: e.target.value || null } }))}>
              <option value="">{t("fin.no_plan")}</option>{plans.map((p) => <option key={p.key} value={p.key}>{p.name || p.key}</option>)}</select></label>)}
        </section>
      </div>
    </div>
  );
}
