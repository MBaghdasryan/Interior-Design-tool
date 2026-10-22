import { useCallback, useEffect, useRef, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { ArrowLeft, Box, Lock, Redo2, Repeat, RotateCw, Save, Sparkles, Trash2, Undo2, Unlock, Zap } from "lucide-react";
import { api, type SceneObject, type Variant } from "../lib/api";
import { amd, catName, variantTitle } from "../lib/format";
import { ruleMessage } from "../lib/messages";
import { useT } from "../i18n";
import PlanView from "../components/PlanView";
import Scene3D from "../components/Scene3D";
import CommandDrawer from "../components/CommandDrawer";
import AlternativesDrawer from "../components/AlternativesDrawer";
import { Badge, Loading, useToast } from "../components/ui";

export default function Editor() {
  const { t } = useT();
  const { pid, vid } = useParams();
  const toast = useToast();
  const [v, setV] = useState<Variant | null>(null);
  const [objs, setObjs] = useState<SceneObject[]>([]);
  const [past, setPast] = useState<SceneObject[][]>([]);
  const [future, setFuture] = useState<SceneObject[][]>([]);
  const [sel, setSel] = useState<string | null>(null);
  const [mode, setMode] = useState<"2d" | "3d" | "electric">("2d");
  const [dirty, setDirty] = useState(false);
  const [saving, setSaving] = useState(false);
  const [cmd, setCmd] = useState(false);
  const [alt, setAlt] = useState<string | null>(null);
  const [autosave, setAutosave] = useState(true);
  const timer = useRef<ReturnType<typeof setTimeout>>();

  const load = useCallback(async () => {
    const x = await api<Variant>(`/projects/${pid}/variants/${vid}`);
    setV(x); setObjs(x.version!.scene.objects); setDirty(false);
  }, [pid, vid]);
  useEffect(() => { load(); }, [load]);

  const commit = (next: SceneObject[]) => { setPast((p) => [...p.slice(-49), objs]); setFuture([]); setObjs(next); setDirty(true); };
  const update = (id: string, patch: Partial<SceneObject>) => commit(objs.map((o) => (o.id === id ? { ...o, ...patch } : o)));
  const undo = () => { if (!past.length) return; setFuture((f) => [objs, ...f]); setObjs(past[past.length - 1]); setPast(past.slice(0, -1)); setDirty(true); };
  const redo = () => { if (!future.length) return; setPast((p) => [...p, objs]); setObjs(future[0]); setFuture(future.slice(1)); setDirty(true); };

  const save = useCallback(async (note?: string) => {
    if (!dirty) return;
    setSaving(true);
    try { const ver = await api(`/projects/${pid}/variants/${vid}/objects`, { method: "PUT", json: { objects: objs, note: note || t("ed.manual_note") } }); setV((cur) => (cur ? { ...cur, version: ver } : cur)); setDirty(false); }
    catch (x) { toast((x as Error).message, true); }
    setSaving(false);
  }, [dirty, objs, pid, vid, toast, t]);
  useEffect(() => {
    if (!autosave || !dirty) return;
    clearTimeout(timer.current);
    timer.current = setTimeout(() => save(t("ed.autosave_note")), 5000);
    return () => clearTimeout(timer.current);
  }, [objs, autosave, dirty, save, t]);
  useEffect(() => {
    const k = (e: KeyboardEvent) => {
      if ((e.target as HTMLElement)?.tagName === "INPUT") return;
      if ((e.ctrlKey || e.metaKey) && e.key === "z") { e.preventDefault(); if (e.shiftKey) redo(); else undo(); }
      if (sel && e.key === "r") update(sel, { rotation: ((objs.find((o) => o.id === sel)?.rotation || 0) + 90) % 360 });
    };
    window.addEventListener("keydown", k);
    return () => window.removeEventListener("keydown", k);
  });

  if (!v?.version) return <Loading />;
  const scene = { ...v.version.scene, objects: objs };
  const o = objs.find((x) => x.id === sel);
  const est = v.version.estimate;
  const issues = v.version.issues.filter((i) => i.severity !== "pass");
  const state = saving ? t("ed.saving") : dirty ? t("ed.unsaved") : t("ed.saved");

  return (
    <div className="col gap-16">
      <div className="row between wrap">
        <div className="row"><Link to={`/app/p/${pid}`} className="icon-btn" aria-label={t("common.back")}><ArrowLeft size={18} /></Link><div><h2>{t("ed.title", { name: variantTitle(v) })}</h2><div className="small muted">{t("ed.meta", { n: v.version.number, state })}</div></div></div>
        <div className="row wrap">
          <button className="icon-btn" onClick={undo} disabled={!past.length} aria-label={t("ed.undo")} title={t("ed.undo")}><Undo2 size={17} /></button>
          <button className="icon-btn" onClick={redo} disabled={!future.length} aria-label={t("ed.redo")} title={t("ed.redo")}><Redo2 size={17} /></button>
          <label className="check small"><input type="checkbox" checked={autosave} onChange={(e) => setAutosave(e.target.checked)} /> {t("ed.autosave")}</label>
          <button className="btn outline-terra" onClick={() => setCmd(true)}><Sparkles size={16} /> {t("cta.ai_change")}</button>
          <button className="btn primary" disabled={!dirty || saving} onClick={() => save()}><Save size={16} /> {t("ed.save_version")}</button>
        </div>
      </div>
      <div className="grid" style={{ gridTemplateColumns: "minmax(0,1fr) 340px", alignItems: "start" }}>
        <div className="card" style={{ overflow: "hidden" }}>
          <div className="tabs" style={{ padding: "0 12px" }}>
            <button className={`tab ${mode === "2d" ? "on" : ""}`} onClick={() => setMode("2d")}>{t("ed.tab.2d")}</button>
            <button className={`tab ${mode === "3d" ? "on" : ""}`} onClick={() => setMode("3d")}><Box size={15} /> {t("ed.tab.3d")}</button>
            <button className={`tab ${mode === "electric" ? "on" : ""}`} onClick={() => setMode("electric")}><Zap size={15} /> {t("ed.tab.electric")}</button>
          </div>
          {mode === "3d" ? <Scene3D scene={scene} height={640} highlight={sel} onPick={setSel} /> :
            <PlanView scene={scene} mode={mode === "electric" ? "electric" : "design"} issues={v.version.issues} selected={sel} onSelect={(id, kind) => setSel(kind === "object" ? id : null)}
              onMove={(id, x, y) => update(id, { x, y, source: "manual" })} height={640} />}
          <div className="small muted" style={{ padding: 10, borderTop: "1px solid var(--line)" }}>{t("ed.help")}</div>
        </div>
        <div className="col gap-16">
          {o ? (
            <div className="card pad col gap-10">
              <div className="row between"><h3>{o.code} · {catName(o.category)}</h3>{o.locked && <Badge tone="dark">{t("ed.locked")}</Badge>}</div>
              <div className="small">{o.name}</div>
              <div className="small muted">{t("ed.obj_meta", { dims: `${Math.round(o.w)}×${Math.round(o.d)}×${Math.round(o.h)}`, r: o.rotation, mode: o.mode === "concept" ? t("ed.mode_concept") : t("ed.mode_real") })}</div>
              <div className="grid g2">
                <div className="field"><label>X, {t("common.mm")}</label><input className="input" aria-label={`X, ${t("common.mm")}`} value={Math.round(o.x)} onChange={(e) => update(o.id, { x: Number(e.target.value) || o.x })} /></div>
                <div className="field"><label>Y, {t("common.mm")}</label><input className="input" aria-label={`Y, ${t("common.mm")}`} value={Math.round(o.y)} onChange={(e) => update(o.id, { y: Number(e.target.value) || o.y })} /></div>
              </div>
              <div className="row wrap">
                <button className="btn sm" onClick={() => update(o.id, { rotation: (o.rotation + 90) % 360 })} disabled={o.locked}><RotateCw size={14} /> {t("ed.rotate")}</button>
                <button className="btn sm" onClick={() => update(o.id, { locked: !o.locked })}>{o.locked ? <><Unlock size={14} /> {t("ed.unlock")}</> : <><Lock size={14} /> {t("ed.lock")}</>}</button>
                <button className="btn sm" onClick={async () => { if (dirty) await save(); setAlt(o.id); }}><Repeat size={14} /> {t("ed.analog")}</button>
                <button className="btn sm" onClick={() => { commit(objs.filter((x) => x.id !== o.id)); setSel(null); }} disabled={o.locked}><Trash2 size={14} /> {t("common.delete")}</button>
              </div>
            </div>
          ) : <div className="card pad small muted">{t("ed.pick")}</div>}
          <div className="card pad">
            <div className="row between"><b>{t("ed.estimate")}</b><b className="mono">{amd(est.totals.known)}</b></div>
            <div className="small muted">{t("ed.estimate_note")}</div>
          </div>
          <div className="card pad col gap-6">
            <b>{t("ed.checks", { n: issues.length })}</b>
            {issues.length === 0 && <div className="small" style={{ color: "var(--sage-ink)" }}>{t("ed.no_issues")}</div>}
            {issues.slice(0, 12).map((i, k) => <button key={k} className={`alert ${i.severity === "block" ? "danger" : "warn"} small`} style={{ textAlign: "left", cursor: "pointer" }} onClick={() => setSel(i.element_ids.find((id) => objs.some((x) => x.id === id)) || null)}>{ruleMessage(i)}</button>)}
            {dirty && <div className="tiny muted">{t("ed.after_save")}</div>}
          </div>
        </div>
      </div>
      <CommandDrawer open={cmd} onClose={() => setCmd(false)} pid={pid!} vid={vid!} onApplied={load} />
      <AlternativesDrawer pid={pid!} vid={vid!} objectId={alt} onClose={() => setAlt(null)} onReplaced={load} />
    </div>
  );
}
