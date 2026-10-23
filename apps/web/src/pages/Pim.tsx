import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { CheckCircle2, ExternalLink, FileUp, XCircle } from "lucide-react";
import { api } from "../lib/api";
import { amd, catName, pct } from "../lib/format";
import { useT } from "../i18n";
import { Badge, Empty, useToast } from "../components/ui";

interface Preview { headers: string[]; mapping: Record<string, string | null>; rows_total: number; valid_in_preview: number; preview: { row: Record<string, any>; errors: string[] }[] }
interface Rev { id: string; source: string; url: string; name: string; price_amd: number | null; category: string | null; confidence: number; warnings: string[]; disputed: Record<string, unknown> }
const FIELDS = ["sku", "name", "category", "brand", "price", "currency", "unit", "width_mm", "depth_mm", "height_mm", "color", "material", "stock", "lead_time_days", "url", "image_url", "package_coverage_m2", "tier", "style"];

export default function Pim() {
  const { t } = useT();
  const toast = useToast();
  const [file, setFile] = useState<File | null>(null);
  const [pv, setPv] = useState<Preview | null>(null);
  const [mapping, setMapping] = useState<Record<string, string | null>>({});
  const [sp] = useSearchParams();
  const [supplier, setSupplier] = useState(sp.get("supplier_name") || "");  // opened from a supplier cabinet
  const [review, setReview] = useState<Rev[]>([]);
  const loadReview = () => api<Rev[]>("/catalog/external/review").then(setReview).catch(() => {});
  useEffect(() => { loadReview(); }, []);
  const preview = async (f: File) => {
    setFile(f);
    const fd = new FormData(); fd.append("file", f);
    try { const r = await api<Preview>("/catalog/import/preview", { method: "POST", body: fd }); setPv(r); setMapping(r.mapping); } catch (x) { toast((x as Error).message, true); }
  };
  const commit = async () => {
    if (!file || !supplier) { toast(t("pim.need_supplier"), true); return; }
    const fd = new FormData(); fd.append("file", file); fd.append("supplier_name", supplier); if (sp.get("supplier_id")) fd.append("supplier_id", sp.get("supplier_id")!); fd.append("mapping", JSON.stringify(mapping));
    try { const r = await api<{ created: number; updated: number; rejected: number }>("/catalog/import/commit", { method: "POST", body: fd }); toast(t("pim.result", r)); setPv(null); setFile(null); }
    catch (x) { toast((x as Error).message, true); }
  };
  const decide = async (id: string, decision: "approved" | "rejected") => { await api(`/catalog/external/review/${id}`, { method: "POST", json: { decision } }); loadReview(); };
  return (
    <div className="col gap-16">
      <div><h1>{t("pim.title")}</h1><p className="muted">{t("pim.lead")}</p></div>
      <div className="card pad col gap-10">
        <h3><FileUp size={18} /> {t("pim.import")}</h3>
        <div className="row wrap"><input className="input" style={{ maxWidth: 320 }} aria-label={t("pim.supplier_ph")} placeholder={t("pim.supplier_ph")} value={supplier} disabled={!!sp.get("supplier_id")} onChange={(e) => setSupplier(e.target.value)} />
          <input type="file" accept=".csv,.xlsx" aria-label={t("pim.import")} onChange={(e) => e.target.files?.[0] && preview(e.target.files[0])} /></div>
        {pv && <>
          <div className="small">{t("pim.rows", { total: pv.rows_total, valid: pv.valid_in_preview, shown: Math.min(200, pv.rows_total) })}</div>
          <div className="grid g4">{FIELDS.map((f) => (
            <div key={f} className="field"><label>{f}</label><select className="select input" aria-label={f} value={mapping[f] || ""} onChange={(e) => setMapping({ ...mapping, [f]: e.target.value || null })}><option value="">—</option>{pv.headers.map((h) => <option key={h}>{h}</option>)}</select></div>
          ))}</div>
          <div className="card flat" style={{ overflow: "auto", maxHeight: 320 }}><table className="table compact"><thead><tr><th /><th>{t("common.sku")}</th><th>{t("common.name")}</th><th>{t("common.category")}</th><th>{t("common.price")}</th><th>{t("common.dims")}</th><th>{t("pim.errors")}</th></tr></thead>
            <tbody>{pv.preview.map((r, i) => <tr key={i}><td>{r.errors.length ? <XCircle size={15} color="var(--danger)" /> : <CheckCircle2 size={15} color="var(--sage-ink)" />}</td><td className="small">{r.row.sku}</td><td className="small">{r.row.name}</td><td className="small">{r.row.category ? catName(r.row.category) : "—"}</td><td className="small mono">{amd(r.row.price, "")} {r.row.currency}</td><td className="small">{[r.row.width_mm, r.row.depth_mm, r.row.height_mm].filter(Boolean).join("×")}</td><td className="tiny" style={{ color: "var(--danger)" }}>{r.errors.join(", ")}</td></tr>)}</tbody></table></div>
          <div className="row"><button className="btn primary" onClick={commit}>{t("pim.do_import")}</button><span className="small muted">{t("pim.guard")}</span></div>
        </>}
      </div>
      <div className="card pad col gap-10">
        <h3>{t("pim.review", { n: review.length })}</h3>
        {!review.length && <Empty>{t("pim.review_empty")}</Empty>}
        {review.map((r) => (
          <div key={r.id} className="card flat pad row top">
            <div className="grow col gap-4"><b>{r.name}</b><div className="small muted">{r.source} · {r.category ? catName(r.category) : t("pim.no_category")} · {t("pim.confidence", { v: pct(r.confidence) })}</div>
              {r.warnings.length > 0 && <div className="tiny" style={{ color: "#8a5d00" }}>⚠ {t("estimate.has_warnings", { n: r.warnings.length })}</div>}
              {Object.keys(r.disputed).length > 0 && <Badge tone="danger">{t("pim.disputed", { f: Object.keys(r.disputed).join(", ") })}</Badge>}</div>
            <div className="col" style={{ alignItems: "flex-end" }}><b className="mono">{amd(r.price_amd)}</b><a className="small" href={r.url} target="_blank" rel="noreferrer">{t("pim.source")} <ExternalLink size={11} /></a>
              <div className="row"><button className="btn sm" onClick={() => decide(r.id, "approved")}>{t("pim.confirm")}</button><button className="btn sm ghost" onClick={() => decide(r.id, "rejected")}>{t("pim.reject")}</button></div></div>
          </div>
        ))}
      </div>
    </div>
  );
}
