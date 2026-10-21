import { useEffect, useState } from "react";
import { CheckCircle2, Circle, FlaskConical } from "lucide-react";
import { api } from "../lib/api";
import { pct } from "../lib/format";
import { useT } from "../i18n";
import { Badge, useToast } from "./ui";

interface Pilot { code: string; validated: boolean; progress: number; manifest: { code: string; auto: boolean; ok: boolean }[]; flow: { code: string; ok: boolean }[] }

/** N99 pilot: intake manifest + end-to-end validation checklist. Renders nothing for ordinary projects. */
export default function PilotPanel({ pid }: { pid: string }) {
  const { t } = useT();
  const toast = useToast();
  const [d, setD] = useState<Pilot | null>(null);
  useEffect(() => { api<Pilot>(`/projects/${pid}/pilot`).then(setD).catch(() => setD(null)); }, [pid]);
  if (!d) return null;
  const mark = async (code: string, ok: boolean) => {
    try { setD(await api<Pilot>(`/projects/${pid}/pilot/mark`, { method: "POST", json: { code, ok } })); } catch (x) { toast((x as Error).message, true); }
  };
  const Mark = ({ ok }: { ok: boolean }) => ok ? <CheckCircle2 size={15} color="var(--sage-ink)" /> : <Circle size={15} color="var(--ink-3)" />;
  return (
    <div className="card pad col gap-8">
      <div className="row"><FlaskConical size={18} /><h3 className="grow">{t("pilot.title", { code: d.code })}</h3>
        <Badge tone={d.validated ? "sage" : "warn"}>{d.validated ? t("pilot.validated") : t("pilot.not_validated")}</Badge></div>
      <div className="small muted">{t("pilot.hint")} · {pct(d.progress)}</div>
      <b className="small">{t("pilot.manifest")}</b>
      {d.manifest.map((i) => (
        <label key={i.code} className="row small gap-6">
          {i.auto ? <Mark ok={i.ok} /> : <input type="checkbox" checked={i.ok} onChange={(e) => mark(i.code, e.target.checked)} />}
          <span className="grow">{t(`pilot.item.${i.code}`)}</span>{i.auto && <span className="tiny muted">{t("pilot.auto")}</span>}
        </label>
      ))}
      <b className="small mt-8">{t("pilot.flow")}</b>
      {d.flow.map((s) => <div key={s.code} className="row small gap-6"><Mark ok={s.ok} />{t(`pilot.stage.${s.code}`)}</div>)}
    </div>
  );
}
