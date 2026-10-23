import { useCallback, useEffect, useRef, useState } from "react";
import { Camera, ExternalLink, Pencil, Plus, Search, Shuffle, X } from "lucide-react";
import { api } from "../lib/api";
import { amd, catName, dt, styleName, tierName } from "../lib/format";
import { useT } from "../i18n";
import { Badge, Empty, Loading, PriceStatus, useToast } from "../components/ui";
import { ProductEditor } from "../components/Management";
import { useMe } from "../components/AppShell";

interface Item { ref: string; category: string; name: string; supplier_name: string; price_amd: number | null; price_status: string; unit: string; w: number; d: number; h: number; color_hex: string; styles: string[]; tier: string; stock: string; sku: string; url: string; checked_at: string | null; is_demo: boolean; source: string; dims_known: boolean; warnings: string[] }
interface SearchStatus { text_provider: string; neural: boolean; indexed: { text: number; image: number } }
interface Analog { ref: string; name: string; supplier: string; price_amd: number | null; price_status: string; stock: string; lead_days: number | null; color_hex: string; is_demo: boolean; score: number; components: Record<string, number> }
interface Tax { categories: { key: string; group: string }[]; groups: { key: string }[]; styles: { key: string }[] }

export default function Catalog() {
  const { t } = useT();
  const [tax, setTax] = useState<Tax | null>(null);
  const [q, setQ] = useState("");
  const [f, setF] = useState({ group: "", category: "", tier: "", style: "", in_stock: false });
  const [items, setItems] = useState<Item[] | null>(null);
  const [mode, setMode] = useState<"keyword" | "smart" | "photo">("keyword");
  const [st, setSt] = useState<SearchStatus | null>(null);
  const [analogs, setAnalogs] = useState<{ base: string; items: Analog[] } | null>(null);
  const photo = useRef<HTMLInputElement>(null);
  const toast = useToast();
  const { me } = useMe();
  // manual catalogue editing: platform catalogue staff for any supplier, supplier staff for their own products (enforced server-side)
  const canWrite = !!me?.roles.some((r) => ["platform_admin", "platform_ops", "supplier_admin", "supplier_catalog"].includes(r));
  const isPlatform = !!me?.roles.some((r) => r === "platform_admin" || r === "platform_ops");
  const [sups, setSups] = useState<{ id: string; name: string; is_demo: boolean }[]>([]);
  const [newFor, setNewFor] = useState("");
  const [edit, setEdit] = useState<{ productId: string | null; supplierId: string } | null>(null);
  const [reload, setReload] = useState(0);
  useEffect(() => {
    if (!canWrite) return;
    if (isPlatform) api<{ id: string; name: string; is_demo: boolean }[]>("/catalog/suppliers").then((r) => { setSups(r); setNewFor(r.find((x) => !x.is_demo)?.id || r[0]?.id || ""); }).catch(() => {});
    else api<{ supplier: { id: string } }>("/supplier/overview").then((o) => setNewFor(o.supplier.id)).catch(() => {});
  }, [canWrite, isPlatform]);
  const openEdit = async (it: Item) => {
    try {
      const p = await api<{ id: string; supplier_id: string; can_edit: boolean }>(`/catalog/variants/${it.ref.slice(3)}/product`);
      if (!p.can_edit) { toast(t("mg.not_your_product"), true); return; }
      setEdit({ productId: p.id, supplierId: p.supplier_id });
    } catch (x) { toast((x as Error).message, true); }
  };
  const closeEdit = useCallback(() => setEdit(null), []);
  useEffect(() => { api<Tax>("/catalog/taxonomy").then(setTax); api<SearchStatus>("/catalog/search/status").then(setSt).catch(() => {}); }, []);
  const byPhoto = async (file: File) => {
    const fd = new FormData();
    fd.append("file", file);
    setMode("photo");
    setItems(null);
    try { setItems((await api<{ items: Item[] }>("/catalog/search/image", { method: "POST", body: fd })).items); } catch { setItems([]); }
  };
  const openAnalogs = async (it: Item) => setAnalogs({ base: it.name, items: (await api<{ items: Analog[] }>(`/catalog/analogs?ref=${encodeURIComponent(it.ref)}`)).items });
  useEffect(() => {
    if (mode === "photo") return;
    if (mode === "smart") {
      if (q.trim().length < 2) { setItems([]); return; }
      setItems(null);
      const tm = setTimeout(() => api<{ items: Item[] }>(`/catalog/search/semantic?${new URLSearchParams({ q, limit: "60" })}`).then((r) => setItems(r.items)).catch(() => setItems([])), 300);
      return () => clearTimeout(tm);
    }
    const p = new URLSearchParams({ q, limit: "120" });
    Object.entries(f).forEach(([k, v]) => v && p.set(k, String(v)));
    setItems(null);
    const tm = setTimeout(() => api<{ items: Item[] }>(`/catalog/products?${p}`).then((r) => setItems(r.items)), 250);
    return () => clearTimeout(tm);
  }, [q, f, mode, reload]);
  const stock = (s: string) => (s === "in_stock" ? t("common.in_stock") : s === "to_order" ? t("common.to_order") : "?");
  return (
    <div className="col gap-16">
      <div className="row between wrap gap-12"><div><h1>{t("catalog.title")}</h1><p className="muted">{t("catalog.lead")}</p></div>
        {canWrite && newFor && <div className="row gap-6">
          {isPlatform && <select className="select input" aria-label={t("mg.col.supplier")} value={newFor} onChange={(e) => setNewFor(e.target.value)}>{sups.map((x) => <option key={x.id} value={x.id}>{x.name}{x.is_demo ? " · DEMO" : ""}</option>)}</select>}
          <button className="btn primary" onClick={() => setEdit({ productId: null, supplierId: newFor })}><Plus size={16} /> {t("mg.product_new")}</button></div>}
      </div>
      <div className="card pad row wrap">
        <div className="row grow" style={{ minWidth: 240 }}><Search size={18} /><input className="input" placeholder={t("catalog.search_ph")} value={q} onChange={(e) => { setQ(e.target.value); if (mode === "photo") setMode("keyword"); }} aria-label={t("common.search")} /></div>
        <select className="select input" aria-label={t("catalog.all_groups")} style={{ width: 190 }} value={f.group} onChange={(e) => setF({ ...f, group: e.target.value, category: "" })}><option value="">{t("catalog.all_groups")}</option>{tax?.groups.map((g) => <option key={g.key} value={g.key}>{t(`enum.group.${g.key}`)}</option>)}</select>
        <select className="select input" aria-label={t("catalog.all_categories")} style={{ width: 210 }} value={f.category} onChange={(e) => setF({ ...f, category: e.target.value })}><option value="">{t("catalog.all_categories")}</option>{tax?.categories.filter((c) => !f.group || c.group === f.group).map((c) => <option key={c.key} value={c.key}>{catName(c.key)}</option>)}</select>
        <select className="select input" aria-label={t("catalog.tier")} style={{ width: 140 }} value={f.tier} onChange={(e) => setF({ ...f, tier: e.target.value })}><option value="">{t("catalog.tier")}</option>{["economy", "comfort", "business", "premium"].map((k) => <option key={k} value={k}>{tierName(k)}</option>)}</select>
        <select className="select input" aria-label={t("catalog.style")} style={{ width: 190 }} value={f.style} onChange={(e) => setF({ ...f, style: e.target.value })}><option value="">{t("catalog.style")}</option>{["warm_minimal", "modern_loft", "soft_scandi"].map((k) => <option key={k} value={k}>{styleName(k)}</option>)}</select>
        <label className="check"><input type="checkbox" checked={f.in_stock} onChange={(e) => setF({ ...f, in_stock: e.target.checked })} /> {t("catalog.in_stock")}</label>
        <div className="row gap-4" role="group" aria-label={t("srch.mode")}>
          {(["keyword", "smart"] as const).map((k) => <button key={k} className={`chip ${mode === k ? "on" : ""}`} aria-pressed={mode === k} onClick={() => setMode(k)}>{t(`srch.${k}`)}</button>)}
          <input ref={photo} type="file" hidden accept="image/*" aria-label={t("srch.photo")} onChange={(e) => e.target.files?.[0] && byPhoto(e.target.files[0])} />
          <button className={`chip ${mode === "photo" ? "on" : ""}`} onClick={() => photo.current?.click()}><Camera size={14} /> {t("srch.photo")}</button>
        </div>
      </div>
      {mode !== "keyword" && st && <div className="alert info small">{mode === "smart"
        ? t(st.neural ? "srch.neural" : "srch.lexical", { n: st.indexed.text, p: st.text_provider })
        : t("srch.visual", { n: st.indexed.image })}</div>}
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
                <div className="row gap-4 mt-8"><button className="btn sm ghost grow" onClick={() => openAnalogs(it)}><Shuffle size={14} /> {t("srch.analogs")}</button>
                  {canWrite && it.ref.startsWith("pv:") && <button className="btn sm" onClick={() => openEdit(it)} aria-label={`${t("mg.edit")}: ${it.name}`}><Pencil size={14} /> {t("mg.edit")}</button>}</div>
              </div>
            </div>
          ))}
        </div>
      )}
      <ProductEditor open={!!edit} supplierId={edit?.supplierId || ""} productId={edit?.productId || null} onClose={closeEdit} onSaved={() => setReload((x) => x + 1)} />
      {analogs && <div className="modal" role="dialog" aria-modal="true" aria-label={t("srch.analogs_for", { name: analogs.base })} onClick={() => setAnalogs(null)}>
        <div className="col gap-8" style={{ padding: 20 }} onClick={(e) => e.stopPropagation()}>
          <div className="row between"><b>{t("srch.analogs_for", { name: analogs.base })}</b><button className="icon-btn" aria-label={t("common.close")} onClick={() => setAnalogs(null)}><X size={16} /></button></div>
          <p className="tiny muted">{t("srch.analogs_hint")}</p>
          {!analogs.items.length && <Empty>{t("common.nothing_found")}</Empty>}
          {analogs.items.map((a) => <div key={a.ref} className="card flat pad col gap-4">
            <div className="row between"><b className="small"><span className="dot" style={{ background: a.color_hex, width: 12, height: 12 }} /> {a.name}</b><b className="mono small">{Math.round(a.score * 100)}%</b></div>
            <div className="tiny muted">{a.supplier} · {a.price_amd == null ? t("common.on_request") : amd(a.price_amd)}{a.is_demo ? " · DEMO" : ""}</div>
            <div className="row gap-4 wrap">{Object.entries(a.components).map(([k, v]) => <Badge key={k} tone={v >= 0.7 ? "sage" : v >= 0.4 ? "" : "warn"}>{t(`srch.c.${k}`)} {Math.round(v * 100)}%</Badge>)}</div>
          </div>)}
        </div></div>}
    </div>
  );
}
