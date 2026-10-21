import { useEffect, useState } from "react";
import { ExternalLink, Repeat } from "lucide-react";
import { api } from "../lib/api";
import { amd, catName } from "../lib/format";
import { useT } from "../i18n";
import { Badge, Drawer, Loading, PriceStatus, useToast } from "./ui";

interface Cand { ref: string; name: string; supplier_name: string; price_amd: number | null; price_status: string; w: number; d: number; h: number; color_hex: string; stock: string; tier: string; url: string; delta_amd: number | null; current: boolean; fits: boolean; warnings: string[]; is_demo: boolean; dims_known: boolean }

export default function AlternativesDrawer({ pid, vid, objectId, onClose, onReplaced }: { pid: string; vid: string; objectId: string | null; onClose: () => void; onReplaced: () => void }) {
  const { t } = useT();
  const [data, setData] = useState<{ object: { code: string; category: string; name: string }; alternatives: Cand[] } | null>(null);
  const toast = useToast();
  useEffect(() => { setData(null); if (objectId) api(`/projects/${pid}/variants/${vid}/objects/${objectId}/alternatives`).then(setData).catch((e) => toast(e.message, true)); }, [pid, vid, objectId, toast]);
  const replace = async (ref: string) => {
    try { await api(`/projects/${pid}/variants/${vid}/objects/${objectId}/replace`, { method: "POST", json: { ref } }); toast(t("alt.replaced")); onReplaced(); onClose(); }
    catch (x) { toast((x as Error).message, true); }
  };
  const stock = (s: string) => (s === "in_stock" ? t("common.in_stock") : s === "to_order" ? t("common.to_order") : t("common.stock_unknown"));
  return (
    <Drawer open={!!objectId} onClose={onClose} title={data ? t("alt.title", { code: data.object.code, category: catName(data.object.category) }) : t("alt.title_short")}>
      {!data ? <Loading /> : (
        <div className="col gap-10">
          <p className="small muted">{t("alt.intro")}</p>
          {data.alternatives.map((c) => (
            <div key={c.ref} className="card flat pad row top" style={{ borderColor: c.current ? "var(--terra)" : undefined }}>
              <div className="thumb" style={{ background: c.color_hex }} />
              <div className="grow col gap-4">
                <b>{c.name}</b>
                <div className="small muted">{c.supplier_name} · {c.w}×{c.d}×{c.h} {t("common.mm")}{!c.dims_known && ` (${t("alt.typical_dims")})`}</div>
                <div className="row wrap"><PriceStatus s={c.price_status} /><Badge tone={c.stock === "in_stock" ? "sage" : ""}>{stock(c.stock)}</Badge>{!c.fits && <Badge tone="danger">{t("alt.does_not_fit")}</Badge>}</div>
                {c.warnings.length > 0 && <div className="tiny" style={{ color: "#8a5d00" }}>⚠ {t("estimate.has_warnings", { n: c.warnings.length })}</div>}
              </div>
              <div className="col" style={{ alignItems: "flex-end" }}>
                <b className="mono">{c.price_amd === null ? t("common.on_request") : amd(c.price_amd)}</b>
                {c.delta_amd !== null && !c.current && <span className="small mono" style={{ color: c.delta_amd <= 0 ? "var(--sage-ink)" : "var(--danger)" }}>{c.delta_amd > 0 ? "+" : ""}{amd(c.delta_amd)}</span>}
                {c.current ? <Badge tone="terra">{t("alt.selected")}</Badge> : <button className="btn sm" disabled={!c.fits} onClick={() => replace(c.ref)}><Repeat size={14} /> {t("alt.replace")}</button>}
                {c.url && <a href={c.url} target="_blank" rel="noreferrer" className="small row gap-4">{t("alt.at_supplier")} <ExternalLink size={12} /></a>}
              </div>
            </div>
          ))}
        </div>
      )}
    </Drawer>
  );
}
