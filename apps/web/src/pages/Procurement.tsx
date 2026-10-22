import { useCallback, useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { ArrowLeft, Send, ShoppingCart, Store } from "lucide-react";
import { api, type Project, type Variant } from "../lib/api";
import { amd, dt, variantTitle } from "../lib/format";
import { useT } from "../i18n";
import { Badge, Empty, Loading, PriceStatus, useToast } from "../components/ui";

interface Rfq { id: string; supplier_name: string; status: string; items: { name: string; sku: string; qty: number; unit: string; unit_price: number | null; price_status: string }[]; message: string; quote: { total_amd?: number; comment?: string }; created_at: string }
interface Order { id: string; supplier_name: string; status: string; payment_status: string; next: string[]; items: { name: string; qty: number; unit: string; total: number | null; price_status: string; lead_days?: number; unit_price?: number | null; rechecked_price?: number | null }[];
  totals: { goods: number; delivery: number; installation: number; quote_required: number; commission_platform: number; quoted?: number }; delivery: { days_min?: number; days_max?: number };
  quote: { total_amd: number; valid_until: string; note: string } | null; history: { at: string; from: string; to: string; by: string; note: string }[] }
interface CartInfo { cart: { id: string; status: string; rechecked_at: string | null; recheck: { changed?: { name: string; was: number; now: number }[]; unavailable?: string[]; stale?: string[]; delta_amd?: number }; recheck_max_age_h: number } | null; payments: { provider: string; status: string } }
const RFQ_TONE: Record<string, string> = { draft: "", sent: "info", quoted: "sage", declined: "danger", expired: "warn" };
const ORD_TONE: Record<string, string> = { cart: "", requested: "info", confirmed: "sage", in_production: "info", delivering: "terra", installing: "terra", installed: "dark", closed: "dark", cancelled: "danger", disputed: "warn", refunded: "warn" };
const BUREAU_MOVES = ["cancelled", "disputed", "closed"];

export default function Procurement() {
  const { t } = useT();
  const { pid } = useParams();
  const toast = useToast();
  const [p, setP] = useState<Project | null>(null);
  const [variant, setVariant] = useState<Variant | null>(null);
  const [rfqs, setRfqs] = useState<Rfq[]>([]);
  const [orders, setOrders] = useState<Order[]>([]);
  const [cart, setCart] = useState<CartInfo | null>(null);
  const load = useCallback(async () => {
    const pr = await api<Project>(`/projects/${pid}`);
    setP(pr);
    const vs: Variant[] = pr.variants || [];
    setVariant(vs.find((v) => v.status === "approved") || vs.find((v) => v.status === "selected") || vs[0] || null);
    setRfqs(await api<Rfq[]>(`/projects/${pid}/rfqs`));
    setOrders(await api<Order[]>(`/projects/${pid}/orders`));
    setCart(await api<CartInfo>(`/projects/${pid}/cart`));
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
          {cart?.cart && cart.cart.status === "open" && orders.some((o) => o.status === "cart") && <div className="alert info small col gap-6">
            <div className="row between wrap"><span>{cart.cart.rechecked_at ? t("pr.rechecked_at", { at: dt(cart.cart.rechecked_at), h: cart.cart.recheck_max_age_h }) : t("pr.recheck_needed")}</span>
              <button className="btn sm" onClick={() => act(() => api(`/projects/${pid}/cart/recheck`, { method: "POST" }), t("pr.recheck_done"))}>{t("pr.recheck")}</button></div>
            {(cart.cart.recheck.changed || []).map((c) => <div key={c.name} className="tiny">{t("pr.price_changed", { name: c.name, was: amd(c.was), now: amd(c.now) })}</div>)}
            {(cart.cart.recheck.unavailable || []).length > 0 && <div className="tiny" style={{ color: "var(--danger)" }}>{t("pr.unavailable", { names: cart.cart.recheck.unavailable!.join(", ") })}</div>}
            {(cart.cart.recheck.stale || []).length > 0 && <div className="tiny">{t("pr.stale_prices", { n: cart.cart.recheck.stale!.length })}</div>}
          </div>}
          {orders.map((o) => (
            <div key={o.id} className="card flat pad col gap-6">
              <div className="row between wrap"><b>{o.supplier_name}</b><div className="row gap-4"><Badge tone={ORD_TONE[o.status]}>{t(`enum.order.${o.status}`)}</Badge>
                {o.payment_status !== "none" && <Badge tone={o.payment_status === "paid" ? "sage" : "warn"}>{t(`pr.pay.${o.payment_status}`)}</Badge>}</div></div>
              <div className="grid g3 small"><div><div className="muted">{t("pr.goods")}</div><b className="mono">{amd(o.totals.goods)}</b></div><div><div className="muted">{t("pr.delivery")}</div><b className="mono">{amd(o.totals.delivery)}</b></div><div><div className="muted">{t("pr.install")}</div><b className="mono">{amd(o.totals.installation)}</b></div></div>
              <div className="tiny muted">{t("pr.cart_meta", { n: o.items.length, q: o.totals.quote_required, a: o.delivery.days_min ?? "?", b: o.delivery.days_max ?? "?", c: amd(o.totals.commission_platform) })}</div>
              {o.quote && <div className="alert sage small">{t("pr.confirmed_total", { v: amd(o.quote.total_amd), until: dt(o.quote.valid_until) })}{o.quote.note ? ` · ${o.quote.note}` : ""}</div>}
              <div className="row gap-6 wrap">
                {o.status === "cart" && <button className="btn sm primary" onClick={() => act(() => api(`/projects/${pid}/orders/${o.id}/request`, { method: "POST", headers: { "Idempotency-Key": `req-${o.id}` } }), t("pr.requested"))}>{t("pr.request")}</button>}
                {o.next.filter((n) => BUREAU_MOVES.includes(n)).map((n) => <button key={n} className="btn sm ghost" onClick={() => act(() => api(`/projects/${pid}/orders/${o.id}/transition`, { method: "POST", json: { to: n } }), t(`enum.order.${n}`))}>{t(`pr.move.${n}`)}</button>)}
                {o.quote && o.payment_status === "none" && !["cancelled", "refunded"].includes(o.status) && (cart?.payments.status === "configured"
                  ? <button className="btn sm" onClick={() => act(async () => { const r = await api<{ redirect_url: string | null }>(`/projects/${pid}/orders/${o.id}/pay`, { method: "POST", headers: { "Idempotency-Key": `pay-${o.id}-${o.quote!.total_amd}` } }); if (r.redirect_url) location.href = r.redirect_url; }, t("pr.pay.started"))}>{t("pr.pay.button")}</button>
                  : <Badge tone="warn">{t("pr.pay.integration_pending")}</Badge>)}
              </div>
              {o.history.length > 0 && <details className="tiny muted"><summary>{t("pr.history", { n: o.history.length })}</summary>
                {o.history.map((h) => <div key={h.at + h.to}>{dt(h.at)} · {t(`enum.order.${h.from}`)} → {t(`enum.order.${h.to}`)}{h.note ? ` · ${h.note}` : ""}</div>)}</details>}
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
