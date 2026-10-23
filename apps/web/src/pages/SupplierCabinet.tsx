import { useCallback, useEffect, useState, type ReactNode } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { BarChart3, Box, Boxes, FileText, Image, Plus, RefreshCw, Rss, Ruler, Tag, Truck } from "lucide-react";
import { api, ApiError, productBg, type Schemas } from "../lib/api";
import { amd, catName, dt } from "../lib/format";
import { useT } from "../i18n";
import { Badge, Empty, Kpi, Loading, Switch, useToast } from "../components/ui";
import { AssetsCard, CustomRatesCard, OnboardingCard, PartnerDataCard } from "../components/SupplierPartner";
import { SupplierPicker, SupplierProducts, TeamCard } from "../components/Management";
import { useMe } from "../components/AppShell";
import { ScopeCtx, useScope, withQs } from "../lib/scope";

interface Ov { supplier: { id: string; org_id?: string | null; name: string; is_demo: boolean; commission_pct: number; verification?: string }; products: number; with_price: number; with_dims: number; with_3d: number; in_stock: number; placements: number; variants_using: number; top: { sku: string; name: string; placements: number; image_url: string; category: string; price: number | null; color_hex: string }[]; attention?: { rfq_new: number; orders_to_confirm: number; stale_prices: number; no_dims: number }; active_orders?: number; rfqs: { id: string; status: string; items: number; created_at: string; message: string }[] }
interface P { id: string; product_id: string; sku: string; name: string; category: string; price: number | null; price_status: string; stock: string; dims: number[]; has_3d: boolean; color_hex: string }

export default function SupplierCabinet() {
  const { me } = useMe();
  const [sp, setSp] = useSearchParams();
  const isPlatform = !!me?.roles.some((r) => r === "platform_admin" || r === "platform_ops");
  const supplierId = isPlatform ? sp.get("supplier") || "" : "";
  const qs = supplierId ? `supplier_id=${encodeURIComponent(supplierId)}` : "";
  const picker = isPlatform && <SupplierPicker value={supplierId} onChange={(v) => setSp(v ? { supplier: v } : {})} />;
  return <ScopeCtx.Provider value={{ qs }}><Cabinet key={qs} picker={picker} /></ScopeCtx.Provider>;
}

function Cabinet({ picker }: { picker: ReactNode }) {
  const { t } = useT();
  const toast = useToast();
  const { me } = useMe();
  const { qs } = useScope();
  const [ov, setOv] = useState<Ov | null>(null);
  const [items, setItems] = useState<P[]>([]);
  const [err, setErr] = useState("");
  const [tab, setTab] = useState<"overview" | "products" | "catalog" | "company">("overview");
  const [add, setAdd] = useState(0);
  const nav = useNavigate();
  const load = useCallback(() => api<Ov>(withQs("/supplier/overview", qs)).then((o) => { setOv(o); setErr(""); }).catch((e: ApiError) => setErr(e.code)), [qs]);
  const loadItems = useCallback(() => api<P[]>(withQs("/supplier/products", qs)).then(setItems).catch(() => {}), [qs]);
  useEffect(() => { load(); loadItems(); }, [load, loadItems]);
  const isPlatform = !!me?.roles.some((r) => r === "platform_admin" || r === "platform_ops");
  const canTeam = !!me?.roles.includes("supplier_admin") || !!me?.roles.includes("platform_admin");
  const respond = async (id: string, status: "quoted" | "declined") => {
    const total = status === "quoted" ? Number(prompt(t("supc.quote_prompt")) || 0) : null;
    try { await api(withQs(`/supplier/rfqs/${id}/respond`, qs), { method: "POST", json: { status, total_amd: total, valid_days: 7 } }); toast(t("supc.sent")); load(); } catch (x) { toast((x as Error).message, true); }
  };
  // platform staff without a chosen supplier: pick one first
  if (err && isPlatform && !qs) return <div className="col gap-16"><h1>{t("supc.title")}</h1>{picker}<Empty>{t("mg.pick_supplier")}</Empty></div>;
  // a self-registered supplier starts with onboarding: there is no catalogue to show yet
  if (err) return <div className="col gap-16"><h1>{t("supc.title")}</h1>{picker}<OnboardingCard onChange={() => { load(); loadItems(); }} /></div>;
  if (!ov) return <Loading />;
  const q = (n: number) => (ov.products ? Math.round((n / ov.products) * 100) : 0);
  const quality: [string, number, typeof Tag][] = [["supc.q.price", ov.with_price, Tag], ["supc.q.dims", ov.with_dims, Ruler], ["supc.q.model", ov.with_3d, Box], ["supc.q.stock", ov.in_stock, Image]];
  const att = ov.attention || { rfq_new: 0, orders_to_confirm: 0, stale_prices: 0, no_dims: 0 };
  const reload = () => { load(); loadItems(); };
  const attention: [string, number, typeof Tag, () => void][] = [
    ["supc.att.rfq", att.rfq_new, FileText, () => nav(`/app/supplier/demand${qs ? `?supplier=${encodeURIComponent(ov.supplier.id)}` : ""}`)],
    ["supc.att.orders", att.orders_to_confirm, Truck, () => nav(`/app/supplier/demand${qs ? `?supplier=${encodeURIComponent(ov.supplier.id)}` : ""}`)],
    ["supc.att.prices", att.stale_prices, Tag, () => setTab("products")],
    ["supc.att.dims", att.no_dims, Ruler, () => setTab("products")],
  ];
  return (
    <div className="col gap-16">
      <div className="row between wrap gap-12">
        <div><h1>{t("supc.hello", { name: me?.name.split(" ")[0] || "" })}</h1><div className="muted">{ov.supplier.name} {ov.supplier.is_demo && <Badge tone="danger">DEMO</Badge>} · {t("supc.lead_n", { r: att.rfq_new, o: ov.active_orders ?? 0 })}</div></div>
        <div className="row gap-8 wrap">{picker}<button className="btn primary lg" onClick={() => { setTab("products"); setAdd((x) => x + 1); }}><Plus size={18} /> {t("mg.product_new")}</button></div>
      </div>
      {qs && <div className="alert info small">{t("mg.viewing_as_platform", { name: ov.supplier.name })}</div>}
      <div className="grid g4">
        <Kpi icon={<Boxes size={20} />} value={ov.products} label={t("supc.skus")} />
        <Kpi icon={<BarChart3 size={20} />} value={ov.placements} label={t("supc.placements", { n: ov.variants_using })} />
        <Kpi icon={<Truck size={20} />} value={ov.active_orders ?? 0} label={t("supc.k.orders")} />
        <Kpi icon={<Tag size={20} />} value={`${ov.supplier.commission_pct}%`} label={t("supc.commission")} />
      </div>
      <div className="tabs" role="tablist">{(["overview", "products", "catalog", "company"] as const).map((k) => <button key={k} role="tab" aria-selected={tab === k} className={`tab ${tab === k ? "on" : ""}`} onClick={() => setTab(k)}>{t(`supc.tab.${k}`)}</button>)}</div>
      {tab === "overview" && <>
        {ov.supplier.verification && ov.supplier.verification !== "verified" && <OnboardingCard onChange={load} />}
        <div className="dash-grid">
          <section className="card pad col gap-12" aria-labelledby="top-h">
            <div className="row between"><h3 id="top-h">{t("supc.top")}</h3><button className="btn sm ghost" onClick={() => setTab("products")}>{t("supc.all_products")}</button></div>
            {ov.top.length ? <div className="grid g4">{ov.top.slice(0, 4).map((x) => <article key={x.sku} className="card flat pcard">
              <div className="img" style={productBg(x.image_url, x.color_hex)} />
              <div className="bd"><b className="small">{x.name}</b><div className="tiny muted">{catName(x.category)} · {x.sku}</div>
                <div className="row between small"><span>{t("supc.used_n", { n: x.placements })}</span><b className="mono">{x.price ? amd(x.price) : ""}</b></div>
                <div className="bar"><i style={{ width: `${(x.placements / Math.max(1, ov.top[0].placements)) * 100}%` }} /></div></div></article>)}</div>
              : <div className="small muted">{t("supc.no_top")}</div>}
          </section>
          <aside className="card pad col gap-8 attention" aria-labelledby="att-h">
            <h3 id="att-h">{t("supc.att.title")}</h3>
            {attention.map(([k, n, I, go]) => <button key={k} className="att-row" onClick={go} disabled={!n}><span className="ico"><I size={16} /></span><span className="grow small">{t(k)}</span><b className={n ? "att-n" : "muted"}>{n}</b></button>)}
          </aside>
        </div>
        <div className="grid g2" style={{ alignItems: "start" }}>
          <section className="card pad col gap-10" aria-labelledby="inbox-h">
            <div className="row between"><h3 id="inbox-h">{t("supc.inbox")}</h3><Link className="small" to={`/app/supplier/demand${qs ? `?supplier=${encodeURIComponent(ov.supplier.id)}` : ""}`}>{t("supc.all_requests")}</Link></div>
            {!ov.rfqs.length && <div className="small muted">{t("supc.no_rfq")}</div>}
            {ov.rfqs.slice(0, 5).map((r) => <div key={r.id} className="card flat pad"><div className="row between"><b className="small">{t("supc.items", { n: r.items })}</b><Badge tone={r.status === "sent" ? "warn" : ""}>{t(`enum.rfq.${r.status}`)}</Badge></div><div className="tiny muted mt-8">{dt(r.created_at)}</div>
              {r.status === "sent" && <div className="row mt-8"><button className="btn sm primary" onClick={() => respond(r.id, "quoted")}>{t("supc.send_quote")}</button><button className="btn sm" onClick={() => respond(r.id, "declined")}>{t("supc.decline")}</button></div>}</div>)}
          </section>
          <section className="card pad col gap-10" aria-labelledby="quality-h">
            <h3 id="quality-h">{t("supc.quality")}</h3>
            <p className="small muted" style={{ margin: 0 }}>{t("supc.quality_lead")}</p>
            {quality.map(([k, n, I]) => (
              <div key={k} className="row"><span className="row gap-6" style={{ width: 200 }}><I size={15} /> {t(k)}</span><div className="grow bar"><i style={{ width: `${q(n)}%` }} /></div><b className="small mono">{q(n)}%</b></div>
            ))}
          </section>
        </div>
        <SupplierOrders />
      </>}
      {tab === "products" && <SupplierProducts supplierId={ov.supplier.id} supplierName={ov.supplier.name} items={items} onChange={reload} openNew={add} />}
      {tab === "catalog" && <><FeedCard /><AssetsCard products={items} />{ov.supplier.verification === "verified" && <OnboardingCard onChange={load} />}</>}
      {tab === "company" && <>{canTeam && (qs ? ov.supplier.org_id && <TeamCard orgId={ov.supplier.org_id} /> : <TeamCard />)}<PartnerDataCard /><CustomRatesCard /></>}
    </div>
  );
}

interface Feed { enabled: boolean; url: string; interval_h: number; max_price_change_pct: number; last_sync_at: string | null; last_status: string | null; history: { at: string; status: string; created?: number; updated?: number; rejected?: number; count?: number; error?: string }[] }

/** Scheduled price feed: an official CSV/XLSX URL synced every N hours through the same guarded import as a manual upload. */
function FeedCard() {
  const { t } = useT();
  const toast = useToast();
  const [f, setF] = useState<Feed | null>(null);
  const { qs } = useScope();
  useEffect(() => { api<Feed>(withQs("/supplier/feed", qs)).then(setF).catch(() => {}); }, [qs]);
  if (!f) return null;
  const save = async (next: Partial<Feed>) => {
    const body: Schemas["FeedIn"] = { enabled: f.enabled, url: f.url, interval_h: f.interval_h, max_price_change_pct: f.max_price_change_pct, ...next };
    try { setF(await api<Feed>(withQs("/supplier/feed", qs), { method: "PUT", json: body })); toast(t("supc.feed.saved")); }
    catch (x) { toast((x as Error).message, true); }
  };
  const sync = async () => {
    try { await api(withQs("/supplier/feed/sync", qs), { method: "POST" }); setF(await api<Feed>(withQs("/supplier/feed", qs))); toast(t("supc.feed.sync_started")); } catch (x) { toast((x as Error).message, true); }
  };
  const tone = (s: string) => (s === "ok" ? "sage" : s === "guard_blocked" || s === "error" ? "danger" : "warn");
  return (
    <section className="card pad col gap-10" aria-labelledby="feed-h">
      <div className="row between wrap"><h3 id="feed-h" className="row gap-6"><Rss size={18} /> {t("supc.feed.title")}</h3>
        <div className="row gap-6"><span className="small">{t("supc.feed.enabled")}</span><Switch on={f.enabled} label={t("supc.feed.enabled")} onChange={(v) => save({ enabled: v })} /></div></div>
      <p className="small muted">{t("supc.feed.lead")}</p>
      <div className="row gap-8 wrap">
        <label className="col gap-4 grow" style={{ minWidth: 260 }}><span className="tiny muted">{t("supc.feed.url")}</span>
          <input className="input" type="url" placeholder="https://…/price.csv" value={f.url} onChange={(e) => setF({ ...f, url: e.target.value })} /></label>
        <label className="col gap-4"><span className="tiny muted">{t("supc.feed.interval")}</span>
          <select className="input" value={f.interval_h} onChange={(e) => setF({ ...f, interval_h: Number(e.target.value) })}>
            {[6, 12, 24, 48, 168].map((h) => <option key={h} value={h}>{t("supc.feed.every_h", { n: h })}</option>)}</select></label>
        <label className="col gap-4"><span className="tiny muted">{t("supc.feed.guard")}</span>
          <input className="input" type="number" min={5} max={500} style={{ width: 110 }} value={f.max_price_change_pct} onChange={(e) => setF({ ...f, max_price_change_pct: Number(e.target.value) })} /></label>
      </div>
      <div className="row gap-6"><button className="btn primary" onClick={() => save({})}>{t("common.save")}</button>
        <button className="btn" disabled={!f.url} onClick={sync}><RefreshCw size={15} /> {t("supc.feed.sync_now")}</button></div>
      {f.last_sync_at && <div className="small">{t("supc.feed.last", { at: dt(f.last_sync_at) })} <Badge tone={tone(f.last_status || "")}>{t(`supc.feed.status.${f.last_status}`)}</Badge></div>}
      {f.history.map((h) => <div key={h.at} className="tiny muted">{dt(h.at)} · {t(`supc.feed.status.${h.status}`)}{h.status === "ok" ? ` · ${t("supc.feed.counts", { created: h.created ?? 0, updated: h.updated ?? 0, rejected: h.rejected ?? 0 })}` : h.count ? ` · ${t("supc.feed.guard_count", { n: h.count })}` : h.error ? ` · ${h.error}` : ""}</div>)}
    </section>
  );
}

interface SOrder { id: string; supplier_name: string; status: string; payment_status: string; next: string[]; created_at: string; items: { name: string; qty: number; unit: string; rechecked_price?: number | null; unit_price?: number | null }[];
  totals: { goods: number; delivery: number; installation: number; quoted?: number }; quote: { total_amd: number; valid_until: string } | null }
const SUPPLIER_MOVES = ["in_production", "delivering", "installing", "cancelled"];

/** Orders sent to this supplier: confirm with a binding total, then report production, delivery and installation. */
export function SupplierOrders() {
  const { t } = useT();
  const toast = useToast();
  const [rows, setRows] = useState<SOrder[]>([]);
  const [totals, setTotals] = useState<Record<string, string>>({});
  const { qs } = useScope();
  const load = () => api<SOrder[]>(withQs("/supplier/orders", qs)).then(setRows).catch(() => {});
  useEffect(() => { load(); }, [qs]);  // eslint-disable-line react-hooks/exhaustive-deps
  const run = async (fn: () => Promise<unknown>) => { try { await fn(); toast(t("supc.ord.saved")); load(); } catch (x) { toast((x as Error).message, true); } };
  return (
    <section className="card pad col gap-10" aria-labelledby="sord-h">
      <h3 id="sord-h">{t("supc.ord.title")}</h3>
      {!rows.length && <div className="small muted">{t("supc.ord.empty")}</div>}
      {rows.map((o) => {
        const suggested = o.totals.goods + o.totals.delivery + o.totals.installation;
        return (
          <div key={o.id} className="card flat pad col gap-6">
            <div className="row between wrap"><b className="small">{t("supc.items", { n: o.items.length })} · {dt(o.created_at)}</b>
              <div className="row gap-4"><Badge>{t(`enum.order.${o.status}`)}</Badge>{o.payment_status === "paid" && <Badge tone="sage">{t("pr.pay.paid")}</Badge>}</div></div>
            <div className="tiny muted">{o.items.slice(0, 3).map((i) => `${i.name} × ${i.qty}`).join("; ")}{o.items.length > 3 ? " …" : ""}</div>
            {o.quote && <div className="small">{t("supc.ord.quoted", { v: amd(o.quote.total_amd) })}</div>}
            {o.status === "requested" && <div className="row gap-6 wrap">
              <input className="input" style={{ width: 160 }} inputMode="numeric" aria-label={t("supc.ord.total")} placeholder={String(suggested)} value={totals[o.id] ?? ""} onChange={(e) => setTotals({ ...totals, [o.id]: e.target.value })} />
              <button className="btn sm primary" onClick={() => run(() => api(withQs(`/supplier/orders/${o.id}/confirm`, qs), { method: "POST", json: { total_amd: Number(totals[o.id] || suggested), valid_days: 7 } }))}>{t("supc.ord.confirm")}</button>
            </div>}
            <div className="row gap-6 wrap">{o.next.filter((n) => SUPPLIER_MOVES.includes(n)).map((n) => (
              <button key={n} className="btn sm ghost" onClick={() => run(() => api(withQs(`/supplier/orders/${o.id}/status`, qs), { method: "POST", json: { to: n } }))}>{t(`supc.ord.move.${n}`)}</button>))}</div>
          </div>
        );
      })}
    </section>
  );
}
