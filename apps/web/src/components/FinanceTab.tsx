import { useCallback, useEffect, useState } from "react";
import { Download } from "lucide-react";
import { api } from "../lib/api";
import { amd } from "../lib/format";
import { useT } from "../i18n";
import { Badge, useToast } from "./ui";

interface Ledger { balances: Record<string, number>; reconcile: { balanced: boolean; transactions: number; payments_match_cash: boolean; captured_amd: number; cash_received_amd: number; refunded_amd: number };
  revenue: Record<string, number>; payments: { provider: string; configured: boolean } }
interface Revenue { streams: string[]; totals: Record<string, number>; by_month: Record<string, Record<string, number>> }
const MANUAL_STREAMS = ["subscription", "credits", "procurement", "manufacturer", "leads", "white_label", "exports"];

/** Platform finance: immutable ledger with reconciliation and export, revenue by stream, tariffs and commission/tax rules. */
export default function FinanceTab() {
  const { t } = useT();
  const toast = useToast();
  const [lg, setLg] = useState<Ledger | null>(null);
  const [rev, setRev] = useState<Revenue | null>(null);
  const [cs, setCs] = useState<{ tax_rate_pct: number; designer_commission_pct: number } | null>(null);
  const [manual, setManual] = useState({ stream: "subscription", amount_amd: "", reference: "" });
  const load = useCallback(() => {
    api<Ledger>("/admin/ledger").then(setLg).catch(() => {});
    api<Revenue>("/admin/revenue").then(setRev).catch(() => {});
    api("/admin/commerce-settings").then(setCs).catch(() => {});
  }, []);
  useEffect(() => { load(); }, [load]);
  const run = async (fn: () => Promise<unknown>) => { try { await fn(); toast(t("fin.saved")); load(); } catch (x) { toast((x as Error).message, true); } };
  if (!lg || !cs) return null;
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


      <div className="grid g2" style={{ alignItems: "start" }}>
        <section className="card pad col gap-8" aria-labelledby="fin-rules">
          <div className="row between"><h3 id="fin-rules">{t("fin.rules")}</h3><button className="btn sm" onClick={() => run(() => api("/admin/commerce-settings", { method: "PUT", json: cs }))}>{t("common.save")}</button></div>
          <label className="row between small"><span>{t("fin.tax_rate")}</span><input className="input" style={{ width: 90 }} inputMode="decimal" value={cs.tax_rate_pct} onChange={(e) => setCs({ ...cs, tax_rate_pct: Number(e.target.value) || 0 })} /></label>
          <label className="row between small"><span>{t("fin.designer_pct")}</span><input className="input" style={{ width: 90 }} inputMode="decimal" value={cs.designer_commission_pct} onChange={(e) => setCs({ ...cs, designer_commission_pct: Number(e.target.value) || 0 })} /></label>
        </section>
      </div>
    </div>
  );
}
