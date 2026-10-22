import { useEffect, useRef, useState } from "react";
import { CheckCircle2, Circle, Download, FlaskConical, Paperclip } from "lucide-react";
import { api } from "../lib/api";
import { pct } from "../lib/format";
import { getLang, useT } from "../i18n";
import { Badge, useToast } from "./ui";

interface Pilot { code: string; validated: boolean; progress: number; manifest: { code: string; auto: boolean; ok: boolean; files: number }[]; flow: { code: string; ok: boolean }[] }

/** N99 pilot: intake manifest (with per-item uploads), end-to-end checklist, report export. Renders nothing for ordinary projects. */
export default function PilotPanel({ pid, onUpload }: { pid: string; onUpload?: () => void }) {
  const { t } = useT();
  const toast = useToast();
  const [d, setD] = useState<Pilot | null>(null);
  const fileInput = useRef<HTMLInputElement>(null);
  const [target, setTarget] = useState<string | null>(null);
  const load = () => api<Pilot>(`/projects/${pid}/pilot`).then(setD).catch(() => setD(null));
  useEffect(() => { load(); }, [pid]);  // eslint-disable-line react-hooks/exhaustive-deps
  if (!d) return null;
  const mark = async (code: string, ok: boolean) => {
    try { setD(await api<Pilot>(`/projects/${pid}/pilot/mark`, { method: "POST", json: { code, ok } })); } catch (x) { toast((x as Error).message, true); }
  };
  const upload = async (files: FileList | null) => {
    if (!files || !target) return;
    for (const f of Array.from(files)) {
      const fd = new FormData();
      fd.append("file", f);
      fd.append("manifest_item", target);
      try { await api(`/projects/${pid}/assets`, { method: "POST", body: fd }); toast(t("pilot.uploaded", { item: t(`pilot.item.${target}`) })); }
      catch (x) { toast(`${f.name}: ${(x as Error).message}`, true); }
    }
    setTarget(null);
    load();
    onUpload?.();
  };
  const pick = (code: string) => { setTarget(code); setTimeout(() => fileInput.current?.click(), 0); };
  const Mark = ({ ok }: { ok: boolean }) => ok ? <CheckCircle2 size={15} color="var(--sage-ink)" /> : <Circle size={15} color="var(--ink-3)" />;
  const report = `/api/v1/projects/${pid}/pilot/report`;
  return (
    <div className="card pad col gap-8">
      <div className="row"><FlaskConical size={18} /><h3 className="grow">{t("pilot.title", { code: d.code })}</h3>
        <Badge tone={d.validated ? "sage" : "warn"}>{d.validated ? t("pilot.validated") : t("pilot.not_validated")}</Badge></div>
      <div className="small muted">{t("pilot.hint")} · {pct(d.progress)}</div>
      <input ref={fileInput} type="file" multiple hidden onChange={(e) => { upload(e.target.files); e.target.value = ""; }} aria-hidden />
      <b className="small">{t("pilot.manifest")}</b>
      {d.manifest.map((i) => (
        <div key={i.code} className="row small gap-6">
          {i.auto ? <Mark ok={i.ok} /> : <input type="checkbox" checked={i.ok} aria-label={t(`pilot.item.${i.code}`)} onChange={(e) => mark(i.code, e.target.checked)} />}
          <span className="grow">{t(`pilot.item.${i.code}`)}{i.files ? <span className="tiny muted"> · {t("pilot.files", { n: i.files })}</span> : null}</span>
          {i.auto && <span className="tiny muted">{t("pilot.auto")}</span>}
          <button className="icon-btn" style={{ width: 28, height: 28 }} title={t("pilot.upload")} aria-label={`${t("pilot.upload")}: ${t(`pilot.item.${i.code}`)}`} onClick={() => pick(i.code)}><Paperclip size={14} /></button>
        </div>
      ))}
      <b className="small mt-8">{t("pilot.flow")}</b>
      {d.flow.map((s) => <div key={s.code} className="row small gap-6"><Mark ok={s.ok} />{t(`pilot.stage.${s.code}`)}</div>)}
      <div className="row gap-6 mt-8 wrap">
        <a className="btn sm" href={`${report}?format=pdf&lang=${getLang()}`}><Download size={14} /> {t("pilot.export_pdf")}</a>
        <a className="btn sm ghost" href={`${report}?format=json`} target="_blank" rel="noreferrer"><Download size={14} /> {t("pilot.export_json")}</a>
      </div>
    </div>
  );
}
