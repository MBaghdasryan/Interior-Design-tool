import { useCallback, useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { FolderKanban, Inbox, PackageCheck } from "lucide-react";
import { api } from "../lib/api";
import { dt, m2 } from "../lib/format";
import { useT } from "../i18n";
import { Badge, Empty, Kpi, Loading, useToast } from "../components/ui";
import { SupplierOrders } from "./SupplierCabinet";
import { ScopeCtx, withQs } from "../lib/scope";

interface Ref { ref: string; bureau: string; city: string; area_m2: number | null }
interface Usage extends Ref { stage: "design" | "request" | "order"; updated_at: string | null; items: { sku: string; name: string; qty: number }[] }
interface Req extends Ref { id: string; status: string; created_at: string; message: string; items: { sku: string; name: string; qty: number; unit: string }[] }
interface Demand { usage: Usage[]; requests: Req[]; counts: { projects: number; requests: number; orders: number } }
const STAGE_TONE: Record<string, string> = { design: "", request: "warn", order: "sage" };

/** Supplier demand: projects that use the supplier's products, requests (interest) and orders — without client data. */
export default function SupplierDemand() {
  const { t } = useT();
  const [sp] = useSearchParams();
  const supplierId = sp.get("supplier") || "";
  const qs = supplierId ? `supplier_id=${encodeURIComponent(supplierId)}` : "";
  const [d, setD] = useState<Demand | null>(null);
  const [err, setErr] = useState("");
  const [tab, setTab] = useState<"requests" | "usage" | "orders">("requests");
  const toast = useToast();
  const [quote, setQuote] = useState<Record<string, string>>({});
  const respond = async (id: string, status: "quoted" | "declined") => {
    try {
      await api(withQs(`/supplier/rfqs/${id}/respond`, qs), { method: "POST", json: { status, total_amd: status === "quoted" ? Number(quote[id]) : null, valid_days: 7 } });
      toast(t("supc.sent")); load();
    } catch (x) { toast((x as Error).message, true); }
  };
  const load = useCallback(() => api<Demand>(withQs("/supplier/demand", qs)).then(setD).catch((e) => setErr((e as Error).message)), [qs]);
  useEffect(() => { load(); }, [load]);
  if (err) return <div className="alert danger">{err}</div>;
  if (!d) return <Loading />;
  const where = (r: Ref) => [r.bureau, r.city, r.area_m2 ? m2(r.area_m2) : ""].filter(Boolean).join(" · ");
  return (
    <ScopeCtx.Provider value={{ qs }}>
      <div className="col gap-16">
        <div><h1>{t("dem.title")}</h1><p className="muted">{t("dem.lead")}</p></div>
        <div className="grid g3">
          <Kpi icon={<Inbox size={20} />} value={d.counts.requests} label={t("dem.k.requests")} />
          <Kpi icon={<FolderKanban size={20} />} value={d.counts.projects} label={t("dem.k.projects")} />
          <Kpi icon={<PackageCheck size={20} />} value={d.counts.orders} label={t("dem.k.orders")} />
        </div>
        <div className="alert info small">{t("dem.privacy")}</div>
        <div className="tabs" role="tablist">{(["requests", "usage", "orders"] as const).map((k) => <button key={k} role="tab" aria-selected={tab === k} className={`tab ${tab === k ? "on" : ""}`} onClick={() => setTab(k)}>{t(`dem.tab.${k}`)}</button>)}</div>
        {tab === "requests" && (!d.requests.length ? <Empty>{t("dem.no_requests")}</Empty> : <div className="col gap-10">
          {d.requests.map((r) => <article key={r.id} className="card pad col gap-6">
            <div className="row between wrap"><b>{r.ref} · {where(r)}</b><div className="row gap-6"><Badge tone={r.status === "sent" ? "warn" : r.status === "quoted" ? "sage" : ""}>{t(`enum.rfq.${r.status}`)}</Badge><span className="tiny muted">{dt(r.created_at)}</span></div></div>
            {r.message && <p className="small" style={{ margin: 0 }}>{r.message}</p>}
            <table className="table compact"><thead><tr><th>{t("common.sku")}</th><th>{t("supc.col.name")}</th><th className="right">{t("dem.qty")}</th></tr></thead>
              <tbody>{r.items.map((it, i) => <tr key={i}><td className="mono small">{it.sku || "—"}</td><td className="small">{it.name}</td><td className="right small">{it.qty} {it.unit ? t(`unit.${it.unit}`) : ""}</td></tr>)}</tbody></table>
            {r.status === "sent" && <div className="row gap-6 wrap">
              <input className="input" style={{ width: 180 }} inputMode="numeric" aria-label={t("dem.quote_total")} placeholder={t("dem.quote_total")} value={quote[r.id] ?? ""} onChange={(e) => setQuote({ ...quote, [r.id]: e.target.value })} />
              <button className="btn sm primary" disabled={!Number(quote[r.id])} onClick={() => respond(r.id, "quoted")}>{t("supc.send_quote")}</button>
              <button className="btn sm" onClick={() => respond(r.id, "declined")}>{t("supc.decline")}</button></div>}
          </article>)}
        </div>)}
        {tab === "usage" && (!d.usage.length ? <Empty>{t("dem.no_usage")}</Empty> : <div className="card" style={{ overflow: "auto" }}>
          <table className="table compact"><thead><tr><th>{t("dem.col.project")}</th><th>{t("dem.col.stage")}</th><th>{t("dem.col.items")}</th><th>{t("dem.col.updated")}</th></tr></thead>
            <tbody>{d.usage.map((u) => <tr key={u.ref}>
              <td><b className="small">{u.ref}</b><div className="tiny muted">{where(u)}</div></td>
              <td><Badge tone={STAGE_TONE[u.stage]}>{t(`dem.stage.${u.stage}`)}</Badge></td>
              <td className="small">{u.items.slice(0, 4).map((it) => <div key={it.sku}>{it.name} <span className="muted mono">{it.sku}</span> × {it.qty}</div>)}{u.items.length > 4 && <div className="tiny muted">+{u.items.length - 4}</div>}</td>
              <td className="tiny muted">{u.updated_at ? dt(u.updated_at) : "—"}</td></tr>)}</tbody></table>
        </div>)}
        {tab === "orders" && <SupplierOrders />}
      </div>
    </ScopeCtx.Provider>
  );
}
