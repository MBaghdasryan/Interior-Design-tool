import { useEffect, useState } from "react";
import { ExternalLink, Search } from "lucide-react";
import { api } from "../lib/api";
import { amd, catName, dt, styleName, tierName } from "../lib/format";
import { useT } from "../i18n";
import { Badge, Empty, Loading, PriceStatus } from "../components/ui";

interface Item { ref: string; category: string; name: string; supplier_name: string; price_amd: number | null; price_status: string; unit: string; w: number; d: number; h: number; color_hex: string; styles: string[]; tier: string; stock: string; sku: string; url: string; checked_at: string | null; is_demo: boolean; source: string; dims_known: boolean; warnings: string[] }
interface Tax { categories: { key: string; group: string }[]; groups: { key: string }[]; styles: { key: string }[] }

export default function Catalog() {
  const { t } = useT();
  const [tax, setTax] = useState<Tax | null>(null);
  const [q, setQ] = useState("");
  const [f, setF] = useState({ group: "", category: "", tier: "", style: "", in_stock: false });
  const [items, setItems] = useState<Item[] | null>(null);
  useEffect(() => { api<Tax>("/catalog/taxonomy").then(setTax); }, []);
  useEffect(() => {
    const p = new URLSearchParams({ q, limit: "120" });
    Object.entries(f).forEach(([k, v]) => v && p.set(k, String(v)));
    setItems(null);
    const tm = setTimeout(() => api<{ items: Item[] }>(`/catalog/products?${p}`).then((r) => setItems(r.items)), 250);
    return () => clearTimeout(tm);
  }, [q, f]);
  const stock = (s: string) => (s === "in_stock" ? t("common.in_stock") : s === "to_order" ? t("common.to_order") : "?");
  return (
    <div className="col gap-16">
      <div><h1>{t("catalog.title")}</h1><p className="muted">{t("catalog.lead")}</p></div>
      <div className="card pad row wrap">
        <div className="row grow" style={{ minWidth: 240 }}><Search size={18} /><input className="input" placeholder={t("catalog.search_ph")} value={q} onChange={(e) => setQ(e.target.value)} aria-label={t("common.search")} /></div>
        <select className="select input" aria-label={t("catalog.all_groups")} style={{ width: 190 }} value={f.group} onChange={(e) => setF({ ...f, group: e.target.value, category: "" })}><option value="">{t("catalog.all_groups")}</option>{tax?.groups.map((g) => <option key={g.key} value={g.key}>{t(`enum.group.${g.key}`)}</option>)}</select>
        <select className="select input" aria-label={t("catalog.all_categories")} style={{ width: 210 }} value={f.category} onChange={(e) => setF({ ...f, category: e.target.value })}><option value="">{t("catalog.all_categories")}</option>{tax?.categories.filter((c) => !f.group || c.group === f.group).map((c) => <option key={c.key} value={c.key}>{catName(c.key)}</option>)}</select>
        <select className="select input" aria-label={t("catalog.tier")} style={{ width: 140 }} value={f.tier} onChange={(e) => setF({ ...f, tier: e.target.value })}><option value="">{t("catalog.tier")}</option>{["economy", "comfort", "business", "premium"].map((k) => <option key={k} value={k}>{tierName(k)}</option>)}</select>
        <select className="select input" aria-label={t("catalog.style")} style={{ width: 190 }} value={f.style} onChange={(e) => setF({ ...f, style: e.target.value })}><option value="">{t("catalog.style")}</option>{["warm_minimal", "modern_loft", "soft_scandi"].map((k) => <option key={k} value={k}>{styleName(k)}</option>)}</select>
        <label className="check"><input type="checkbox" checked={f.in_stock} onChange={(e) => setF({ ...f, in_stock: e.target.checked })} /> {t("catalog.in_stock")}</label>
      </div>
      {!items ? <Loading /> : !items.length ? <Empty>{t("common.nothing_found")}</Empty> : (
        <div className="grid g4">
          {items.map((it) => (
            <div key={it.ref} className="card col" style={{ overflow: "hidden" }}>
              <div style={{ height: 110, background: `linear-gradient(135deg, ${it.color_hex}, #f6f1ea)`, position: "relative" }}>
                <div style={{ position: "absolute", top: 10, left: 10 }} className="row gap-4"><PriceStatus s={it.price_status} />{it.source === "external" && <Badge tone="info">{t("catalog.external")}</Badge>}</div>
              </div>
              <div className="col gap-4" style={{ padding: 14 }}>
                <div className="tiny muted">{catName(it.category)} · {tierName(it.tier)}</div>
                <b className="small">{it.name}</b>
                <div className="tiny muted">{it.supplier_name} · {it.sku}</div>
                <div className="tiny muted">{it.w ? `${it.w}×${it.d}×${it.h} ${t("common.mm")}` : t("catalog.no_dims")}{!it.dims_known && it.w ? ` (${t("catalog.typical")})` : ""}</div>
                <div className="row between mt-8"><b className="mono">{it.price_amd === null ? t("common.on_request") : amd(it.price_amd)}<span className="tiny muted"> {t("catalog.per", { unit: t(`unit.${it.unit}`) })}</span></b>
                  <Badge tone={it.stock === "in_stock" ? "sage" : ""}>{stock(it.stock)}</Badge></div>
                <div className="row between tiny muted"><span>{t("catalog.checked", { when: dt(it.checked_at) })}</span>{it.url && <a href={it.url} target="_blank" rel="noreferrer">{t("alt.at_supplier")} <ExternalLink size={11} /></a>}</div>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
