import { useCallback, useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { ArrowLeft, Send, ShoppingCart, Store } from "lucide-react";
import { api, type Project, type Variant } from "../lib/api";
import { amd, dt, variantTitle } from "../lib/format";
import { useT } from "../i18n";
import { Badge, Empty, Loading, PriceStatus, useToast } from "../components/ui";

interface Rfq { id: string; supplier_name: string; status: string; items: { name: string; sku: string; qty: number; unit: string; unit_price: number | null; price_status: string }[]; message: string; quote: { total_amd?: number; comment?: string }; created_at: string }
interface Order { id: string; supplier_name: string; status: string; items: { name: string; qty: number; unit: string; total: number | null; price_status: string; lead_days?: number }[]; totals: { goods: number; delivery: number; installation: number; quote_required: number; commission_platform: number }; delivery: { days_min?: number; days_max?: number } }
const RFQ_TONE: Record<string, string> = { draft: "", sent: "info", quoted: "sage", declined: "danger", expired: "warn" };
const ORD_TONE: Record<string, string> = { cart: "", requested: "info", confirmed: "sage", delivering: "terra", installed: "dark", cancelled: "danger" };

export default function Procurement() {
  const { t } = useT();
  const { pid } = useParams();
  const toast = useToast();
  const [p, setP] = useState<Project | null>(null);
  const [variant, setVariant] = useState<Variant | null>(null);
  const [rfqs, setRfqs] = useState<Rfq[]>([]);
  const [orders, setOrders] = useState<Order[]>([]);
  const load = useCallback(async () => {
    const pr = await api<Project>(`/projects/${pid}`);
    setP(pr);
    const vs: Variant[] = pr.variants || [];
    setVariant(vs.find((v) => v.status === "approved") || vs.find((v) => v.status === "selected") || vs[0] || null);
    setRfqs(await api<Rfq[]>(`/projects/${pid}/rfqs`));
    setOrders(await api<Order[]>(`/projects/${pid}/orders`));
  }, [pid]);
  useEffect(() => { load(); }, [load]);
  const act = async (fn: () => Promise<unknown>, ok: string) => { try { await fn(); toast(ok); load(); } catch (x) { toast((x as Error).message, true); } };
  if (!p) return <Loading />;
  const approved = variant?.status === "approved";
  return (
    <div className="col gap-16">
      <div className="row"><Link to={`/app/p/${pid}`} className="icon-btn" aria-label={t("common.back")}><ArrowLeft size={18} /></Link><div><h1>{t("pr.title")}</h1><div className="muted">{variant ? variantTitle(variant) : ""} · {approved ? t("pr.approved") : t("pr.not_approved")}</div></div></div>
      <div className="alert info small">{t("pr.lead")}</div>
      <div className="grid g2" style={{ alignItems: "start" }}>
        <div className="card pad col gap-10">
          <div className="row between"><h3><Store size={18} /> {t("pr.rfqs")}</h3><button className="btn sm primary" disabled={!variant} onClick={() => act(() => api(`/projects/${pid}/rfqs`, { method: "POST", json: { variant_id: variant!.id } }), t("pr.rfq_done"))}>{t("pr.make_rfq")}</button></div>
          {!rfqs.length && <Empty>{t("pr.no_rfq")}</Empty>}
          {rfqs.map((r) => (
            <div key={r.id} className="card flat pad col gap-6">
              <div className="row between"><b>{r.supplier_name}</b><Badge tone={RFQ_TONE[r.status]}>{t(`enum.rfq.${r.status}`)}</Badge></div>
              <div className="small muted">{t("pr.items_when", { n: r.items.length, when: dt(r.created_at) })}</div>
              <div className="small">{r.items.slice(0, 4).map((i) => <div key={i.sku + i.name} className="row between"><span>{i.name} × {i.qty} {t(`unit.${i.unit}`)}</span><PriceStatus s={i.price_status} /></div>)}{r.items.length > 4 && <div className="muted">{t("pr.more", { n: r.items.length - 4 })}</div>}</div>
              {r.quote?.total_amd && <div className="alert sage small">{t("pr.quote", { v: amd(r.quote.total_amd) })}</div>}
              {r.status === "draft" && <button className="btn sm" onClick={() => act(() => api(`/projects/${pid}/rfqs/${r.id}/send`, { method: "POST" }), t("pr.sent_ok"))}><Send size={14} /> {t("common.send")}</button>}
            </div>
          ))}
        </div>
        <div className="card pad col gap-10">
          <div className="row between"><h3><ShoppingCart size={18} /> {t("pr.carts")}</h3><button className="btn sm primary" disabled={!approved} title={approved ? "" : t("pr.need_approval")} onClick={() => act(() => api(`/projects/${pid}/cart`, { method: "POST", json: { variant_id: variant!.id } }), t("pr.carts_done"))}>{t("pr.make_carts")}</button></div>
          {!orders.length && <Empty>{approved ? t("pr.no_carts") : t("pr.cart_after")}</Empty>}
          {orders.map((o) => (
            <div key={o.id} className="card flat pad col gap-6">
              <div className="row between"><b>{o.supplier_name}</b><Badge tone={ORD_TONE[o.status]}>{t(`enum.order.${o.status}`)}</Badge></div>
              <div className="grid g3 small"><div><div className="muted">{t("pr.goods")}</div><b className="mono">{amd(o.totals.goods)}</b></div><div><div className="muted">{t("pr.delivery")}</div><b className="mono">{amd(o.totals.delivery)}</b></div><div><div className="muted">{t("pr.install")}</div><b className="mono">{amd(o.totals.installation)}</b></div></div>
              <div className="tiny muted">{t("pr.cart_meta", { n: o.items.length, q: o.totals.quote_required, a: o.delivery.days_min ?? "?", b: o.delivery.days_max ?? "?", c: amd(o.totals.commission_platform) })}</div>
              {o.status === "cart" && <button className="btn sm" onClick={() => act(() => api(`/projects/${pid}/orders/${o.id}/request`, { method: "POST" }), t("pr.requested"))}>{t("pr.request")}</button>}
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
