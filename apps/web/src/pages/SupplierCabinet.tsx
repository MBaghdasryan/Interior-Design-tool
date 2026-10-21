import { useEffect, useState } from "react";
import { BarChart3, Box, Boxes, Image, Ruler, Tag } from "lucide-react";
import { api, ApiError } from "../lib/api";
import { amd, catName, dt } from "../lib/format";
import { useT } from "../i18n";
import { Badge, Empty, Loading, PriceStatus, useToast } from "../components/ui";

interface Ov { supplier: { name: string; is_demo: boolean; commission_pct: number }; products: number; with_price: number; with_dims: number; with_3d: number; in_stock: number; placements: number; variants_using: number; top: { sku: string; name: string; placements: number }[]; rfqs: { id: string; status: string; items: number; created_at: string; message: string }[] }
interface P { id: string; sku: string; name: string; category: string; price: number | null; price_status: string; stock: string; dims: number[]; has_3d: boolean; color_hex: string }

export default function SupplierCabinet() {
  const { t } = useT();
  const toast = useToast();
  const [ov, setOv] = useState<Ov | null>(null);
  const [items, setItems] = useState<P[]>([]);
  const [err, setErr] = useState("");
  const load = () => api<Ov>("/supplier/overview").then(setOv).catch((e: ApiError) => setErr(e.message));
  useEffect(() => { load(); api<P[]>("/supplier/products").then(setItems).catch(() => {}); }, []);
  const respond = async (id: string, status: "quoted" | "declined") => {
    const total = status === "quoted" ? Number(prompt(t("supc.quote_prompt")) || 0) : null;
    try { await api(`/supplier/rfqs/${id}/respond`, { method: "POST", json: { status, total_amd: total, valid_days: 7 } }); toast(t("supc.sent")); load(); } catch (x) { toast((x as Error).message, true); }
  };
  if (err) return <Empty>{err}</Empty>;
  if (!ov) return <Loading />;
  const q = (n: number) => (ov.products ? Math.round((n / ov.products) * 100) : 0);
  const quality: [string, number, typeof Tag][] = [["supc.q.price", ov.with_price, Tag], ["supc.q.dims", ov.with_dims, Ruler], ["supc.q.model", ov.with_3d, Box], ["supc.q.stock", ov.in_stock, Image]];
  return (
    <div className="col gap-16">
      <div className="row between wrap"><div><h1>{t("supc.title")}</h1><div className="muted">{ov.supplier.name} {ov.supplier.is_demo && <Badge tone="danger">DEMO</Badge>}</div></div><a className="btn primary" href="/app/pim">{t("supc.upload")}</a></div>
      <div className="grid g4">
        <div className="card kpi"><div className="ico"><Boxes size={22} /></div><div><div className="v">{ov.products}</div><div className="muted small">{t("supc.skus")}</div></div></div>
        <div className="card kpi"><div className="ico"><BarChart3 size={22} /></div><div><div className="v">{ov.placements}</div><div className="muted small">{t("supc.placements", { n: ov.variants_using })}</div></div></div>
        <div className="card kpi"><div className="ico"><Tag size={22} /></div><div><div className="v">{ov.rfqs.length}</div><div className="muted small">{t("supc.rfqs")}</div></div></div>
        <div className="card kpi"><div className="ico"><Box size={22} /></div><div><div className="v">{ov.supplier.commission_pct}%</div><div className="muted small">{t("supc.commission")}</div></div></div>
      </div>
      <div className="grid g2" style={{ alignItems: "start" }}>
        <div className="card pad col gap-10">
          <h3>{t("supc.quality")}</h3>
          <p className="small muted">{t("supc.quality_lead")}</p>
          {quality.map(([k, n, I]) => (
            <div key={k} className="row"><span className="row gap-6" style={{ width: 200 }}><I size={15} /> {t(k)}</span><div className="grow progress"><i style={{ width: `${q(n)}%` }} /></div><b className="small mono">{q(n)}%</b></div>
          ))}
          <div className="divider" />
          <b>{t("supc.top")}</b>
          {ov.top.length ? ov.top.map((x) => <div key={x.sku} className="row between small"><span>{x.name} <span className="muted">{x.sku}</span></span><b>{x.placements}</b></div>) : <div className="small muted">{t("supc.no_top")}</div>}
        </div>
        <div className="card pad col gap-10">
          <h3>{t("supc.inbox")}</h3>
          {!ov.rfqs.length && <div className="small muted">{t("supc.no_rfq")}</div>}
          {ov.rfqs.map((r) => <div key={r.id} className="card flat pad"><div className="row between"><b className="small">{t("supc.items", { n: r.items })}</b><Badge>{t(`enum.rfq.${r.status}`)}</Badge></div><div className="tiny muted mt-8">{dt(r.created_at)}</div>
            {r.status === "sent" && <div className="row mt-8"><button className="btn sm primary" onClick={() => respond(r.id, "quoted")}>{t("supc.send_quote")}</button><button className="btn sm" onClick={() => respond(r.id, "declined")}>{t("supc.decline")}</button></div>}</div>)}
        </div>
      </div>
      <div className="card" style={{ overflow: "auto", maxHeight: 520 }}>
        <table className="table compact"><thead><tr><th /><th>{t("common.sku")}</th><th>{t("supc.col.name")}</th><th>{t("common.category")}</th><th className="right">{t("common.price")}</th><th>{t("common.status")}</th><th>{t("common.in_stock")}</th><th>{t("common.dims")}</th><th>{t("supc.col.3d")}</th></tr></thead>
          <tbody>{items.map((p) => <tr key={p.id}><td><span className="dot" style={{ background: p.color_hex, width: 14, height: 14 }} /></td><td className="small mono">{p.sku}</td><td className="small">{p.name}</td><td className="small">{catName(p.category)}</td><td className="right mono small">{amd(p.price, "")}</td><td><PriceStatus s={p.price_status} /></td><td className="small">{p.stock === "in_stock" ? t("common.yes") : t("common.no")}</td><td className="small">{p.dims.join("×")}</td><td>{p.has_3d ? "✓" : "—"}</td></tr>)}</tbody></table>
      </div>
    </div>
  );
}
