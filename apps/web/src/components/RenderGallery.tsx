import { useCallback, useEffect, useState } from "react";
import { Camera, RefreshCw, Sparkles } from "lucide-react";
import { api, fileUrl, streamJob, type Job } from "../lib/api";
import { catName, pct } from "../lib/format";
import { stepDetail, stepTitle } from "../lib/messages";
import { useT } from "../i18n";
import { Badge, useToast } from "./ui";

export interface RenderItem { code: string; object_id: string; type: string; name: string; sku: string; supplier: string; url: string; color_hex: string; mode: string }
export interface Render {
  id: string; room_id: string; camera_id: string; url: string; width: number; height: number; model: string; created_at: string; parent_id?: string | null;
  grounding: { score: number | null; verified?: boolean; visual_analogs: string[]; extra_objects: string[]; items: Record<string, { score: number; note: string }> };
  manifest: RenderItem[];
}

/** Photoreal renders of one room: generate, check product grounding per item, regenerate a zone. */
export default function RenderGallery({ pid, vid, roomId, readOnly }: { pid: string; vid: string; roomId: string; readOnly?: boolean }) {
  const { t } = useT();
  const toast = useToast();
  const [all, setAll] = useState<Render[]>([]);
  const [job, setJob] = useState<Job | null>(null);
  const [pick, setPick] = useState<Set<string>>(new Set());
  const [instr, setInstr] = useState("");
  const load = useCallback(() => api<Render[]>(`/projects/${pid}/variants/${vid}/renders`).then(setAll).catch(() => {}), [pid, vid]);
  useEffect(() => { load(); }, [load]);
  const renders = all.filter((r) => r.room_id === roomId);
  const r = renders[0];
  const follow = (j: Job) => {
    setJob(j);
    const stop = streamJob(pid, j.id, (x) => {
      setJob(x);
      if (x.status === "succeeded") { stop(); setJob(null); setPick(new Set()); setInstr(""); load(); }
      if (x.status === "failed") { stop(); toast(x.error || t("errors.unknown"), true); }
    });
  };
  const start = async () => { try { follow(await api<Job>(`/projects/${pid}/variants/${vid}/renders`, { method: "POST", json: { room_id: roomId } })); } catch (x) { toast((x as Error).message, true); } };
  const regen = async () => {
    if (!r || !pick.size) return;
    try { follow(await api<Job>(`/projects/${pid}/renders/${r.id}/regenerate`, { method: "POST", json: { object_ids: [...pick], instruction: instr } })); }
    catch (x) { toast((x as Error).message, true); }
  };
  const busy = !!job && !["succeeded", "failed"].includes(job.status);
  return (
    <div className="col gap-10">
      <div className="row between wrap">
        <b className="row gap-6"><Camera size={16} /> {t("render.title")}</b>
        {!readOnly && <button className="btn sm primary" disabled={busy} onClick={start}><Sparkles size={15} /> {r ? t("render.again") : t("render.generate")}</button>}
      </div>
      {busy && job && <div className="card pad small col gap-4">{job.steps.map((s) => <div key={s.key} className="row gap-6"><Badge tone={s.status === "done" ? "sage" : s.status === "running" ? "info" : ""}>{stepTitle(s)}</Badge><span className="muted">{stepDetail(s)}</span></div>)}</div>}
      {!r && !busy && <div className="alert info small">{t("render.empty")}</div>}
      {r && <>
        <figure className="card" style={{ overflow: "hidden", margin: 0 }}>
          <img src={fileUrl(r.url)} alt={t("render.alt")} style={{ width: "100%", display: "block", aspectRatio: `${r.width} / ${r.height}`, objectFit: "cover" }} />
          <figcaption className="pad small row between wrap">
            <span className="muted">{t("render.caption", { model: r.model, w: r.width, h: r.height })}</span>
            {r.grounding.score === null || r.grounding.verified === false ? <Badge tone="warn">{t("render.not_verified")}</Badge>
              : <Badge tone={r.grounding.score >= 0.7 ? "sage" : "warn"}>{t("render.match", { p: pct(r.grounding.score) })}</Badge>}
          </figcaption>
        </figure>
        <table className="table compact">
          <thead><tr>{!readOnly && <th />}<th>{t("render.col.item")}</th><th>{t("render.col.product")}</th><th className="right">{t("render.col.match")}</th></tr></thead>
          <tbody>{r.manifest.map((it) => {
            const g = r.grounding.items[it.code];
            const analog = r.grounding.visual_analogs.includes(it.code);
            return <tr key={it.code}>
              {!readOnly && <td><input type="checkbox" aria-label={it.code} checked={pick.has(it.object_id)} onChange={(e) => { const s = new Set(pick); if (e.target.checked) s.add(it.object_id); else s.delete(it.object_id); setPick(s); }} /></td>}
              <td className="small"><span className="dot" style={{ background: it.color_hex }} /> <b>{it.code}</b> {catName(it.type.toLowerCase().replace(/ /g, "_")) || it.type}</td>
              <td className="small">{it.url ? <a href={it.url} target="_blank" rel="noreferrer">{it.name}</a> : it.name}{it.sku && <span className="tiny muted"> · {it.sku}</span>}
                {it.mode !== "real" && <Badge tone="warn">{t(`render.mode.${it.mode}`)}</Badge>}</td>
              <td className="right small">{g ? pct(g.score) : "—"} {analog && <Badge tone="warn">{t("render.analog")}</Badge>}{g?.note && <div className="tiny muted">{g.note}</div>}</td>
            </tr>;
          })}</tbody>
        </table>
        {r.grounding.extra_objects.length > 0 && <div className="tiny muted">{t("render.extra", { list: r.grounding.extra_objects.join(", ") })}</div>}
        {!readOnly && <div className="row gap-6 wrap">
          <input className="input grow" placeholder={t("render.instr_ph")} aria-label={t("render.instr_ph")} value={instr} onChange={(e) => setInstr(e.target.value)} />
          <button className="btn" disabled={busy || !pick.size} onClick={regen}><RefreshCw size={15} /> {t("render.regen", { n: pick.size })}</button>
        </div>}
        <p className="tiny muted">{t("render.note")}</p>
      </>}
    </div>
  );
}
