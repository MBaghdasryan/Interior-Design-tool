import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { ArrowLeft, GitCompare, History, RotateCcw } from "lucide-react";
import { api, type Diff, type Version } from "../lib/api";
import { amd, catName, dt, roomType } from "../lib/format";
import { useT } from "../i18n";
import PlanView from "../components/PlanView";
import { Badge, Loading, useToast } from "../components/ui";

const SRC_TONE: Record<string, string> = { ai: "terra", command: "terra", manual: "info", restore: "" };

export default function Versions() {
  const { t, lang } = useT();
  const { pid, vid } = useParams();
  const toast = useToast();
  const [list, setList] = useState<Version[] | null>(null);
  const [a, setA] = useState("");
  const [b, setB] = useState("");
  const [diff, setDiff] = useState<Diff | null>(null);
  const [preview, setPreview] = useState<Version | null>(null);
  const [rooms, setRooms] = useState<Record<string, string>>({});
  const load = () => api<Version[]>(`/projects/${pid}/variants/${vid}/versions`).then((l) => { setList(l); if (l.length > 1) { setA(l[l.length - 1].id); setB(l[0].id); } });
  useEffect(() => { load(); api<{ scene: { rooms: { id: string; type: string }[] } }>(`/projects/${pid}/geometry`).then((g) => setRooms(Object.fromEntries((g.scene?.rooms || []).map((r) => [r.id, r.type])))); }, [pid, vid]);  // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => { if (a && b && a !== b) api<Diff>(`/projects/${pid}/variants/${vid}/compare?a=${a}&b=${b}`).then(setDiff); }, [a, b, pid, vid]);
  const open = async (id: string) => setPreview(await api<Version>(`/projects/${pid}/variants/${vid}/versions/${id}`));
  const restore = async (id: string) => { try { await api(`/projects/${pid}/variants/${vid}/versions/${id}/restore`, { method: "POST" }); toast(t("ver.restored")); load(); } catch (x) { toast((x as Error).message, true); } };
  const rn = (id: string) => (rooms[id] ? roomType(rooms[id]) : id);
  if (!list) return <Loading />;
  return (
    <div className="col gap-16">
      <div className="row"><Link to={`/app/p/${pid}`} className="icon-btn" aria-label={t("common.back")}><ArrowLeft size={18} /></Link><h1>{t("ver.title")}</h1></div>
      <div className="grid" style={{ gridTemplateColumns: "380px minmax(0,1fr)", alignItems: "start" }}>
        <div className="card pad col gap-6">
          <h3><History size={18} /> {t("ver.history")}</h3>
          {list.map((v) => (
            <div key={v.id} className="row top" style={{ padding: "8px 0", borderBottom: "1px solid var(--line)" }}>
              <b className="mono" style={{ width: 34 }}>v{v.number}</b>
              <div className="grow"><div className="row wrap"><Badge tone={SRC_TONE[v.source]}>{t(`enum.version_source.${v.source}`)}</Badge>{v.frozen && <Badge tone="dark">{t("ver.frozen")}</Badge>}</div>
                {lang === "ru" || v.source === "command" ? <div className="small mt-8">{v.note}</div> : null}<div className="tiny muted">{dt(v.created_at)} · {amd(v.total ?? null)}</div></div>
              <div className="col gap-4"><button className="btn sm" onClick={() => open(v.id)}>{t("common.open")}</button><button className="btn sm ghost" onClick={() => restore(v.id)} aria-label={t("ver.restore")} title={t("ver.restore")}><RotateCcw size={13} /></button></div>
            </div>
          ))}
        </div>
        <div className="col gap-16">
          <div className="card pad col gap-10">
            <h3><GitCompare size={18} /> {t("ver.compare")}</h3>
            <div className="row"><select className="select input" value={a} onChange={(e) => setA(e.target.value)}>{list.map((v) => <option key={v.id} value={v.id}>v{v.number}</option>)}</select><span>→</span>
              <select className="select input" value={b} onChange={(e) => setB(e.target.value)}>{list.map((v) => <option key={v.id} value={v.id}>v{v.number}</option>)}</select></div>
            {diff && <>
              <div className="grid g4 small">
                <div><div className="muted">{t("cmd.estimate_delta")}</div><b className="mono" style={{ color: diff.total_delta <= 0 ? "var(--sage-ink)" : "var(--danger)" }}>{diff.total_delta > 0 ? "+" : ""}{amd(diff.total_delta)}</b></div>
                <div><div className="muted">{t("ver.added")}</div><b>{diff.added.length}</b></div><div><div className="muted">{t("ver.removed")}</div><b>{diff.removed.length}</b></div><div><div className="muted">{t("ver.changed_moved")}</div><b>{diff.changed.length}/{diff.moved.length}</b></div>
              </div>
              {diff.changed.map((c, i) => <div key={i} className="small">↻ {catName(c.category)} ({rn(c.room_id)}): {c.from} → <b>{c.to}</b></div>)}
              {diff.added.map((c, i) => <div key={`a${i}`} className="small" style={{ color: "var(--sage-ink)" }}>+ {catName(c.category)} ({rn(c.room_id)}) {c.name}</div>)}
              {diff.removed.map((c, i) => <div key={`r${i}`} className="small" style={{ color: "var(--danger)" }}>− {catName(c.category)} ({rn(c.room_id)}) {c.name}</div>)}
            </>}
          </div>
          {preview && <div className="card"><div className="row between" style={{ padding: 12 }}><b>{t("ver.version_total", { n: preview.number, total: amd(preview.estimate.totals.known) })}</b></div><PlanView scene={preview.scene} height={460} issues={preview.issues} /></div>}
        </div>
      </div>
    </div>
  );
}
