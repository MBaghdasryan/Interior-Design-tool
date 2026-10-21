import { useEffect, useState } from "react";
import { CheckCircle2, Circle, ShieldCheck } from "lucide-react";
import { api } from "../lib/api";
import { useT } from "../i18n";
import { AccuracyBadge, Badge, useToast } from "./ui";

interface Trust { level: string; next: string | null; checklist: { code: string; ok: boolean }[]; exports: Record<string, string>; limitations: string[];
  provenance: { photos: number; plans: number; lidar: boolean; control_dimensions: number; measurements: number }; signoffs: { created_at: string }[] }

/** Concept Estimate → Verified Design → Production Ready: checklist, limits, exports, sign-off. */
export default function TrustPanel({ pid, onChange }: { pid: string; onChange?: () => void }) {
  const { t } = useT();
  const toast = useToast();
  const [d, setD] = useState<Trust | null>(null);
  const load = () => api<Trust>(`/projects/${pid}/trust`).then(setD).catch(() => {});
  useEffect(() => { load(); }, [pid]);  // eslint-disable-line react-hooks/exhaustive-deps
  if (!d) return null;
  const act = async (path: string, ok: string) => {
    try { await api(`/projects/${pid}/trust/${path}`, { method: "POST", json: {} }); toast(ok); load(); onChange?.(); }
    catch (x) { toast((x as Error).message, true); }
  };
  const p = d.provenance;
  return (
    <div className="card pad col gap-10">
      <div className="row"><ShieldCheck size={18} /><h3 className="grow">{t("trust.title")}</h3></div>
      <AccuracyBadge level={d.level} />
      <div className="small muted">{t(`enum.accuracy_hint.${d.level}`)}</div>
      {d.next && <>
        <b className="small">{t("trust.next", { level: t(`enum.accuracy.${d.next}`) })}</b>
        {d.checklist.map((c) => <div key={c.code} className="row small gap-6">{c.ok ? <CheckCircle2 size={15} color="var(--sage-ink)" /> : <Circle size={15} color="var(--ink-3)" />}{t(`trust.check.${c.code}`)}</div>)}
        <div className="row wrap">
          <button className="btn sm" disabled={!d.checklist.every((c) => c.ok)} onClick={() => act("advance", t("trust.next", { level: t(`enum.accuracy.${d.next}`) }))}>{t("trust.advance")}</button>
          <button className="btn sm ghost" onClick={() => act("signoff", t("trust.signed"))}>{t("trust.signoff")}</button>
        </div>
      </>}
      <b className="small">{t("trust.limitations")}</b>
      <ul className="small" style={{ margin: 0, paddingLeft: 18 }}>{d.limitations.map((l) => <li key={l}>{t(`trust.lim.${l}`)}</li>)}</ul>
      <b className="small">{t("trust.exports")}</b>
      <div className="row wrap">{Object.entries(d.exports).map(([k, v]) => <Badge key={k} tone={v === "allowed" ? "sage" : v === "blocked" ? "danger" : "warn"}>{t(`trust.export.${k}`)}: {t(`trust.export.${v}`)}</Badge>)}</div>
      <div className="tiny muted">{t("trust.provenance")}: {t("trust.prov_line", { photos: p.photos, plans: p.plans, lidar: p.lidar ? t("common.yes") : t("common.no"), dims: p.control_dimensions, meas: p.measurements })}</div>
    </div>
  );
}
