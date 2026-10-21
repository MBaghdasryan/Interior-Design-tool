import { useEffect, useState } from "react";
import { Globe2, Store } from "lucide-react";
import { api } from "../lib/api";
import { amd } from "../lib/format";
import { useT } from "../i18n";
import { Badge, Loading } from "../components/ui";

interface Sup { id: string; name: string; kind: string; is_demo: boolean; city: string; delivery: { fee_amd?: number; days_min?: number; days_max?: number }; commission_pct: number; products: number }
interface Src { key: string; name: string; domain: string; categories: string[]; method: string; status: string; note: string }
const TONE: Record<string, string> = { ok: "sage", needs_audit: "warn", needs_feed: "warn", rfq_only: "info", unreachable: "danger", blocked: "danger", disabled: "" };

export default function Suppliers() {
  const { t } = useT();
  const [sup, setSup] = useState<Sup[] | null>(null);
  const [src, setSrc] = useState<Src[]>([]);
  useEffect(() => { api<Sup[]>("/catalog/suppliers").then(setSup); api<Src[]>("/catalog/sources").then(setSrc); }, []);
  if (!sup) return <Loading />;
  return (
    <div className="col gap-24">
      <div><h1>{t("sup.title")}</h1><p className="muted">{t("sup.lead")}</p></div>
      <div>
        <h2><Store size={20} /> {t("sup.catalogs")}</h2>
        <div className="grid g3 mt-16">
          {sup.map((s) => (
            <div key={s.id} className="card pad col gap-6">
              <div className="row between"><b>{s.name}</b>{s.is_demo ? <Badge tone="danger">DEMO</Badge> : <Badge tone="sage">{t("sup.partner")}</Badge>}</div>
              <div className="small muted">{s.kind === "manufacturer" ? t("sup.manufacturer") : t("sup.store")} · {s.city} · {t("sup.products", { n: s.products })}</div>
              <div className="small">{t("sup.delivery", { fee: s.delivery.fee_amd !== undefined ? amd(s.delivery.fee_amd) : "—", min: s.delivery.days_min ?? "?", max: s.delivery.days_max ?? "?" })}</div>
              <div className="tiny muted">{t("sup.commission", { pct: s.commission_pct })}</div>
            </div>
          ))}
        </div>
      </div>
      <div>
        <h2><Globe2 size={20} /> {t("sup.external")}</h2>
        <p className="muted small mt-8">{t("sup.external_lead")}</p>
        <div className="grid g2 mt-16">
          {src.map((s) => (
            <div key={s.key} className="card pad col gap-6">
              <div className="row between"><b>{s.name}</b><Badge tone={TONE[s.status]}>{t(`enum.source_status.${s.status}`)}</Badge></div>
              <a className="small" href={s.domain} target="_blank" rel="noreferrer">{s.domain}</a>
              <div className="row wrap">{s.categories.map((c) => <Badge key={c}>{t(`enum.group.${c}`)}</Badge>)}<Badge tone="info">{s.method}</Badge></div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
