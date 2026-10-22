import { useCallback, useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { AlertTriangle, ArrowRight, Box, CheckCircle2, Ruler, Save } from "lucide-react";
import { api, type Job, type Project, type Room, type Scene, type Wall } from "../lib/api";
import { mm, pct } from "../lib/format";
import { ruleMessage, stepDetail, stepTitle } from "../lib/messages";
import { tOr, useT } from "../i18n";
import PlanView from "../components/PlanView";
import Scene3D from "../components/Scene3D";
import ApsViewer from "../components/ApsViewer";
import TrustPanel from "../components/TrustPanel";
import { AccuracyBadge, Badge, Loading, Progress, StepStatus, useToast } from "../components/ui";
import { useMe } from "../components/AppShell";

interface Geo { version: number; confirmed: boolean; scene: Scene | null; mask: { walls: Record<string, string>; rooms: Record<string, string>; openings: Record<string, string>; summary: Record<string, number> }; confidence: number; accuracy_level: string; rooms: { id: string; area_m2: number }[]; checks: { message: string; severity: string; code?: string; params?: Record<string, unknown>; rule: string; element_ids: string[] }[] }
const ROOM_TYPES = ["living", "kitchen", "kitchen_living", "bedroom", "kids", "bathroom", "wc", "hallway", "wardrobe", "balcony", "office"];
const ZONES: Record<string, string> = { living: "day", kitchen: "day", kitchen_living: "day", bedroom: "night", kids: "night", bathroom: "wet", wc: "wet", hallway: "service", wardrobe: "service", balcony: "outdoor", office: "day" };

export default function Geometry() {
  const { t, lang } = useT();
  const { pid } = useParams();
  const nav = useNavigate();
  const toast = useToast();
  const { cfg } = useMe();
  const [geo, setGeo] = useState<Geo | null>(null);
  const [scene, setScene] = useState<Scene | null>(null);
  const [sel, setSel] = useState<{ id: string; kind: string } | null>(null);
  const [dirty, setDirty] = useState(false);
  const [view, setView] = useState<"2d" | "3d" | "aps">("2d");
  const [cd, setCd] = useState({ wall_id: "W1", measured_mm: "" });
  const [job, setJob] = useState<Job | null>(null);
  const [project, setProject] = useState<Project | null>(null);

  const load = useCallback(async () => {
    const g = await api<Geo>(`/projects/${pid}/geometry`);
    setGeo(g); setScene(g.scene); setDirty(false);
    setProject(await api<Project>(`/projects/${pid}`));
  }, [pid]);
  useEffect(() => { load(); }, [load]);
  useEffect(() => {
    let tm: ReturnType<typeof setInterval> | undefined;
    const poll = async () => {
      const jobs = await api<Job[]>(`/projects/${pid}/jobs?kind=recognize`);
      const j = jobs[0];
      setJob(j || null);
      if (!j || ["succeeded", "failed"].includes(j.status)) { clearInterval(tm); if (j?.status === "succeeded") load(); }
    };
    poll(); tm = setInterval(poll, 1500);
    return () => clearInterval(tm);
  }, [pid, load]);

  if (!geo) return <Loading />;
  if (!scene) return <div className="card pad col"><h2>{t("geo.empty_title")}</h2><p className="muted">{t("geo.empty_text")}</p>{job && job.status !== "succeeded" && <JobBox job={job} />}<button className="btn" onClick={() => nav(`/app/p/${pid}/upload`)}>{t("geo.to_upload")}</button></div>;

  const wall = sel?.kind === "wall" ? scene.walls.find((w) => w.id === sel.id) : undefined;
  const room = sel?.kind === "room" ? scene.rooms.find((r) => r.id === sel.id) : undefined;
  const updWall = (patch: Partial<Wall>) => { setScene({ ...scene, walls: scene.walls.map((w) => (w.id === wall!.id ? { ...w, ...patch, source: "manual", confidence: 1 } : w)) }); setDirty(true); };
  const updRoom = (patch: Partial<Room>) => { setScene({ ...scene, rooms: scene.rooms.map((r) => (r.id === room!.id ? { ...r, ...patch, source: "manual", confidence: 1 } : r)) }); setDirty(true); };
  const save = async () => { await api(`/projects/${pid}/geometry`, { method: "PUT", json: { scene } }); toast(t("geo.saved")); load(); };
  const setControl = async () => {
    try {
      const r = await api<{ factor: number }>(`/projects/${pid}/geometry/control-dimension`, { method: "POST", json: { wall_id: cd.wall_id, measured_mm: Number(cd.measured_mm), rescale: true } });
      toast(t("geo.scale_applied", { f: r.factor })); load();
    } catch (x) { toast((x as Error).message, true); }
  };
  const confirm = async () => {
    if (dirty) await save();
    try { const r = await api<{ accuracy_level: string }>(`/projects/${pid}/geometry/confirm`, { method: "POST" }); toast(t("geo.confirmed_toast", { level: t(`enum.accuracy.${r.accuracy_level}`) })); nav(`/app/p/${pid}/upload`); }
    catch (x) { toast((x as Error).message, true); }
  };
  const len = (w: Wall) => Math.round(Math.hypot(w.b[0] - w.a[0], w.b[1] - w.a[1]));
  const apsAsset = project?.assets?.find((a) => a.aps?.urn);
  const s = geo.mask.summary;

  return (
    <div className="col gap-16">
      <div className="row between wrap">
        <div><h1>{t("geo.title")}</h1><div className="row mt-8 wrap"><AccuracyBadge level={geo.accuracy_level} /><Badge>v{geo.version}</Badge>{geo.confirmed ? <Badge tone="sage">{t("geo.confirmed")}</Badge> : <Badge tone="warn">{t("geo.draft")}</Badge>}<span className="muted small">{t("geo.confidence", { v: pct(geo.confidence) })}</span></div></div>
        <div className="row">
          {dirty && <button className="btn" onClick={save}><Save size={16} /> {t("common.save")}</button>}
          <button className="btn primary" onClick={confirm}><CheckCircle2 size={16} /> {t("geo.confirm")} <ArrowRight size={16} /></button>
        </div>
      </div>
      {job && job.status !== "succeeded" && <JobBox job={job} />}
      <div className="grid" style={{ gridTemplateColumns: "minmax(0, 1fr) 360px", alignItems: "start" }}>
        <div className="card" style={{ overflow: "hidden" }}>
          <div className="tabs" style={{ padding: "0 12px" }}>
            <button className={`tab ${view === "2d" ? "on" : ""}`} onClick={() => setView("2d")}>{t("geo.tab.mask")}</button>
            <button className={`tab ${view === "3d" ? "on" : ""}`} onClick={() => setView("3d")}><Box size={15} /> {t("geo.tab.3d")}</button>
            {cfg?.aps_enabled && apsAsset && <button className={`tab ${view === "aps" ? "on" : ""}`} onClick={() => setView("aps")}>{t("geo.tab.aps")}</button>}
          </div>
          {view === "2d" && <PlanView scene={scene} mode="review" mask={geo.mask} selected={sel?.id} onSelect={(id, kind) => setSel(id ? { id, kind: kind! } : null)} height={600} />}
          {view === "3d" && <Scene3D scene={scene} height={600} cutaway />}
          {view === "aps" && apsAsset?.aps.urn && <ApsViewer urn={apsAsset.aps.urn} height={600} />}
          <div className="row wrap" style={{ padding: 12, borderTop: "1px solid var(--line)" }}>
            <span className="row gap-6 small"><i className="dot" style={{ background: "#5d8f4e" }} /> {t("geo.green", { n: s.green })}</span>
            <span className="row gap-6 small"><i className="dot" style={{ background: "#d6a21e" }} /> {t("geo.yellow", { n: s.yellow })}</span>
            <span className="row gap-6 small"><i className="dot" style={{ background: "#c8463d" }} /> {t("geo.red", { n: s.red })}</span>
            <span className="muted small grow right">{t("geo.click_hint")}</span>
          </div>
        </div>
        <div className="col gap-16">
          <div className="card pad col gap-10">
            <div className="row"><Ruler size={18} /><h3>{t("geo.control")}</h3></div>
            <p className="small muted">{t("geo.control_hint")}</p>
            <div className="row"><select className="select input" value={cd.wall_id} onChange={(e) => setCd({ ...cd, wall_id: e.target.value })}>{scene.walls.map((w) => <option key={w.id} value={w.id}>{w.id} · {mm(len(w))}</option>)}</select>
              <input className="input" placeholder={t("common.mm")} inputMode="numeric" value={cd.measured_mm} onChange={(e) => setCd({ ...cd, measured_mm: e.target.value.replace(/\D/g, "") })} /></div>
            <button className="btn" disabled={!cd.measured_mm} onClick={setControl}>{t("geo.control_apply")}</button>
            {scene.control_dimensions.map((c) => <div key={c.wall_id} className="small"><CheckCircle2 size={13} color="var(--sage-ink)" /> {c.wall_id} = {mm(c.measured_mm)}</div>)}
          </div>
          {wall && <div className="card pad col gap-10">
            <h3>{t("geo.wall", { id: wall.id })}</h3><div className="small muted">{t("geo.wall_meta", { len: mm(len(wall)), src: wall.source, conf: pct(wall.confidence) })}</div>
            <div className="grid g2">
              <div className="field"><label>{t("geo.thickness")}</label><input aria-label={t("geo.thickness")} className="input" value={wall.thickness} onChange={(e) => updWall({ thickness: Number(e.target.value) || wall.thickness })} /></div>
              <div className="field"><label>{t("geo.material")}</label><select aria-label={t("geo.material")} className="select input" value={wall.material} onChange={(e) => updWall({ material: e.target.value })}>{["concrete", "brick", "block", "drywall", "glass"].map((x) => <option key={x} value={x}>{t(`enum.material.${x}`)}</option>)}</select></div>
              <div className="field"><label>{t("geo.status")}</label><select aria-label={t("geo.status")} className="select input" value={wall.status} onChange={(e) => updWall({ status: e.target.value as Wall["status"] })}>{["existing", "demolish", "new"].map((x) => <option key={x} value={x}>{t(`enum.wall_status.${x}`)}</option>)}</select></div>
              <div className="field"><label>{t("geo.kind")}</label><select aria-label={t("geo.kind")} className="select input" value={wall.kind} onChange={(e) => updWall({ kind: e.target.value })}>{["exterior", "interior", "partition", "balcony"].map((x) => <option key={x} value={x}>{t(`enum.wall_kind.${x}`)}</option>)}</select></div>
            </div>
            <label className="check"><input type="checkbox" checked={wall.load_bearing} onChange={(e) => updWall({ load_bearing: e.target.checked })} /> {t("geo.bearing")}</label>
            {wall.load_bearing && wall.status === "demolish" && <div className="alert danger small">{t("geo.bearing_warn")}</div>}
          </div>}
          {room && <div className="card pad col gap-10">
            <h3>{t("geo.room", { n: room.number })}</h3><div className="small muted">{geo.rooms.find((r) => r.id === room.id)?.area_m2} {t("common.m2")} · {pct(room.confidence)}</div>
            <div className="field"><label>{t("geo.room_name")}</label><input aria-label={t("geo.room_name")} className="input" value={room.source === "manual" ? room.name : t(`enum.room.${room.type}`)} onChange={(e) => updRoom({ name: e.target.value })} /></div>
            <div className="grid g2">
              <div className="field"><label>{t("geo.room_type")}</label><select aria-label={t("geo.room_type")} className="select input" value={room.type} onChange={(e) => updRoom({ type: e.target.value, zone: ZONES[e.target.value] })}>{ROOM_TYPES.map((k) => <option key={k} value={k}>{t(`enum.room.${k}`)}</option>)}</select></div>
              <div className="field"><label>{t("geo.ceiling")}</label><input aria-label={t("geo.ceiling")} className="input" value={room.ceiling_height} onChange={(e) => updRoom({ ceiling_height: Number(e.target.value) || room.ceiling_height })} /></div>
            </div>
          </div>}
          <TrustPanel pid={pid!} onChange={load} />
          <div className="card pad col gap-6">
            <h3>{t("geo.assumptions")}</h3>
            {scene.assumptions.length === 0 && <p className="muted small">{t("common.none")}</p>}
            {scene.assumptions.map((a) => <div key={a.key} className={`alert ${a.severity === "critical" ? "danger" : a.severity === "warning" ? "warn" : "info"} small`}><AlertTriangle size={16} />{tOr(`geo.assume.${a.key}`, lang === "ru" ? a.text : a.key, {}, lang)}</div>)}
            {geo.checks.map((c, i) => <div key={i} className="alert warn small"><AlertTriangle size={16} />{ruleMessage(c as never)}</div>)}
          </div>
        </div>
      </div>
    </div>
  );
}

function JobBox({ job }: { job: Job }) {
  const { t } = useT();
  return <div className="card pad col gap-6"><div className="row between"><b>{t("geo.recognition", { status: t(`enum.job.${job.status}`) })}</b><span className="small muted">{Math.round(job.progress * 100)}%</span></div><Progress value={job.progress} />
    {job.steps.map((s) => <div key={s.key} className="small row gap-6"><StepStatus s={s.status} />{stepTitle(s)}<span className="muted">{stepDetail(s)}</span></div>)}
    {job.error && <div className="alert danger small">{job.error}</div>}</div>;
}
