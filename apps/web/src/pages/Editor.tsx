import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link, useParams } from "react-router-dom";
import type { LucideIcon } from "lucide-react";
import { ArrowLeft, Armchair, Box, CheckCircle2, DoorOpen, Flower2, Lamp, LayoutPanelTop, Lock, Maximize2, Minus, MousePointer2, Plus, Redo2, Repeat, RotateCw,
  Ruler, Save, Search, Share2, Sparkles, SquareDashed, Trash2, Undo2, Unlock } from "lucide-react";
import { api, type Finish, type Project, type Room, type SceneObject, type Variant } from "../lib/api";
import { amd, catName, n1, variantTitle } from "../lib/format";
import { ruleMessage } from "../lib/messages";
import { useT } from "../i18n";
import PlanView from "../components/PlanView";
import Scene3D from "../components/Scene3D";
import CommandDrawer from "../components/CommandDrawer";
import AlternativesDrawer from "../components/AlternativesDrawer";
import { useLightbox } from "../components/Lightbox";
import { Badge, Drawer, Loading, PriceStatus, useToast } from "../components/ui";

type Mode = "plan" | "3d" | "materials" | "lighting";
type Tool = "select" | "furniture" | "decor" | "rooms" | "measure";
interface Item { ref: string; category: string; name: string; supplier_name: string; price_amd: number | null; price_status: string; w: number; d: number; h: number;
  color_hex: string; stock: string; image_url?: string; source?: string }
interface Snap { objs: SceneObject[]; fins: Finish[]; rooms: Record<string, { name?: string; ceiling_height?: number }> }

// surfaces a room can finish and the catalogue categories that may cover them (mirrors the server check)
const SURFACES: [string, string[]][] = [["floor", ["floor_parquet", "floor_laminate", "floor_tile"]], ["walls", ["wall_paint", "wall_panel"]], ["ceiling", ["wall_paint", "drywall"]]];
const STRIP_GROUPS = ["furniture", "lighting", "plumbing", "finishing", "decor", "appliances"];
const TOOLS: [Tool | "walls" | "openings", LucideIcon][] = [["select", MousePointer2], ["walls", SquareDashed], ["openings", DoorOpen], ["furniture", Armchair],
  ["decor", Flower2], ["rooms", LayoutPanelTop], ["measure", Ruler]];

const polyArea = (p: [number, number][]) => { let s = 0; for (let i = 0; i < p.length; i++) { const [x1, y1] = p[i], [x2, y2] = p[(i + 1) % p.length]; s += x1 * y2 - x2 * y1; } return Math.abs(s) / 2e6; };
const perimeter = (p: [number, number][]) => p.reduce((s, q, i) => { const r = p[(i + 1) % p.length]; return s + Math.hypot(r[0] - q[0], r[1] - q[1]); }, 0) / 1000;
const centre = (p: [number, number][]): [number, number] => { const xs = p.map((q) => q[0]), ys = p.map((q) => q[1]); return [Math.round((Math.min(...xs) + Math.max(...xs)) / 2), Math.round((Math.min(...ys) + Math.max(...ys)) / 2)]; };

/** Manual editor (mockup «Apartment workspace»): rooms, tools, plan + 3D, room properties and finishes, budget, catalogue strip. */
export default function Editor() {
  const { t } = useT();
  const { pid, vid } = useParams();
  const toast = useToast();
  const openBig = useLightbox();
  const [v, setV] = useState<Variant | null>(null);
  const [project, setProject] = useState<Project | null>(null);
  const [objs, setObjs] = useState<SceneObject[]>([]);
  const [fins, setFins] = useState<Finish[]>([]);
  const [roomEdits, setRoomEdits] = useState<Snap["rooms"]>({});
  const [past, setPast] = useState<Snap[]>([]);
  const [future, setFuture] = useState<Snap[]>([]);
  const [sel, setSel] = useState<string | null>(null);
  const [room, setRoom] = useState<string>("");
  const [mode, setMode] = useState<Mode>("plan");
  const [tool, setTool] = useState<Tool>("select");
  const [zoom, setZoom] = useState(100);
  const [dirty, setDirty] = useState(false);
  const [saving, setSaving] = useState(false);
  const [cmd, setCmd] = useState(false);
  const [alt, setAlt] = useState<string | null>(null);
  const [autosave, setAutosave] = useState(true);
  const [picker, setPicker] = useState<string | null>(null);  // surface being re-finished
  const timer = useRef<ReturnType<typeof setTimeout>>();

  const load = useCallback(async () => {
    const x = await api<Variant>(`/projects/${pid}/variants/${vid}`);
    setV(x); setObjs(x.version!.scene.objects); setFins(x.version!.scene.finishes); setRoomEdits({}); setDirty(false);
  }, [pid, vid]);
  useEffect(() => { load(); api<Project>(`/projects/${pid}`).then(setProject).catch(() => {}); }, [load, pid]);

  const snap = (): Snap => ({ objs, fins, rooms: roomEdits });
  const apply = (s: Snap) => { setObjs(s.objs); setFins(s.fins); setRoomEdits(s.rooms); setDirty(true); };
  const commit = (next: Partial<Snap>) => { setPast((p) => [...p.slice(-49), snap()]); setFuture([]); apply({ ...snap(), ...next }); };
  const update = (id: string, patch: Partial<SceneObject>) => commit({ objs: objs.map((o) => (o.id === id ? { ...o, ...patch } : o)) });
  const undo = () => { if (!past.length) return; setFuture((f) => [snap(), ...f]); apply(past[past.length - 1]); setPast(past.slice(0, -1)); };
  const redo = () => { if (!future.length) return; setPast((p) => [...p, snap()]); apply(future[0]); setFuture(future.slice(1)); };

  const save = useCallback(async (note?: string) => {
    if (!dirty) return;
    setSaving(true);
    try {
      const rooms = Object.entries(roomEdits).map(([id, r]) => ({ id, ...r }));
      const ver = await api<Variant["version"]>(`/projects/${pid}/variants/${vid}/objects`, { method: "PUT", json: { objects: objs, finishes: fins, rooms, note: note || t("ed.manual_note") } });
      setV((cur) => (cur ? { ...cur, version: ver } : cur));
      if (ver) { setObjs(ver.scene.objects); setFins(ver.scene.finishes); setRoomEdits({}); }
      setDirty(false);
    } catch (x) { toast((x as Error).message, true); }
    setSaving(false);
  }, [dirty, objs, fins, roomEdits, pid, vid, toast, t]);
  useEffect(() => {
    if (!autosave || !dirty) return;
    clearTimeout(timer.current);
    timer.current = setTimeout(() => save(t("ed.autosave_note")), 5000);
    return () => clearTimeout(timer.current);
  }, [objs, fins, roomEdits, autosave, dirty, save, t]);
  useEffect(() => {
    const k = (e: KeyboardEvent) => {
      if (["INPUT", "TEXTAREA", "SELECT"].includes((e.target as HTMLElement)?.tagName)) return;
      if ((e.ctrlKey || e.metaKey) && e.key === "z") { e.preventDefault(); if (e.shiftKey) redo(); else undo(); }
      if (sel && e.key === "r") update(sel, { rotation: ((objs.find((o) => o.id === sel)?.rotation || 0) + 90) % 360 });
      if (sel && (e.key === "Delete" || e.key === "Backspace") && !objs.find((o) => o.id === sel)?.locked) { commit({ objs: objs.filter((o) => o.id !== sel) }); setSel(null); }
    };
    window.addEventListener("keydown", k);
    return () => window.removeEventListener("keydown", k);
  });

  const base = v?.version?.scene;
  const scene = useMemo(() => base && ({ ...base, objects: objs, finishes: fins,
    rooms: base.rooms.map((r) => (roomEdits[r.id] ? { ...r, ...(roomEdits[r.id].name ? { name: roomEdits[r.id].name!, source: "manual" } : {}), ...(roomEdits[r.id].ceiling_height ? { ceiling_height: roomEdits[r.id].ceiling_height! } : {}) } : r)) }),
  [base, objs, fins, roomEdits]);
  if (!v?.version || !scene) return <Loading />;
  const o = objs.find((x) => x.id === sel);
  const est = v.version.estimate;
  const issues = v.version.issues.filter((i) => i.severity !== "pass");
  const state = saving ? t("ed.saving") : dirty ? t("ed.unsaved") : t("ed.saved");
  const rName = (r: Room) => (r.source === "manual" ? r.name : t(`enum.room.${r.type}`));
  const curRoom = scene.rooms.find((r) => r.id === room) || null;
  const budget = (project?.brief as { budget_amd?: number } | undefined)?.budget_amd;
  const readOnly = v.status === "approved";

  const addProduct = (it: Item) => {
    const r = curRoom || scene.rooms[0];
    const [x, y] = centre(r.polygon);
    const no: SceneObject = { id: `N${Date.now().toString(36)}`, code: "", room_id: r.id, category: it.category, name: it.name, product_variant_id: it.ref,
      x, y, w: it.w || 600, d: it.d || 600, h: it.h || 800, rotation: 0, elevation: 0, locked: false, color_hex: it.color_hex || "#b9a48f", mode: "real", source: "manual", confidence: 1 } as SceneObject;
    commit({ objs: [...objs, no] });
    setSel(no.id);
    toast(t("ed.added", { name: it.name, room: rName(r) }));
  };
  const setFinish = (surface: string, it: Item) => {
    if (!curRoom) return;
    const rest = fins.filter((f) => !(f.room_id === curRoom.id && f.surface === surface));
    commit({ fins: [...rest, { room_id: curRoom.id, surface, product_variant_id: it.ref, material_code: "", name: it.name, color_hex: it.color_hex, pattern: surface === "floor" ? "plank" : surface === "walls" ? "paint" : "plain" }] });
    setPicker(null);
  };
  const editRoom = (id: string, patch: { name?: string; ceiling_height?: number }) => commit({ rooms: { ...roomEdits, [id]: { ...roomEdits[id], ...patch } } });
  const clickTool = (k: (typeof TOOLS)[number][0]) => {
    if (k === "walls" || k === "openings") { window.location.assign(`/app/p/${pid}/geometry`); return; }  // walls and openings are edited on the base geometry
    setTool(k);
    if (k === "furniture" || k === "decor") setMode((m) => (m === "3d" ? "plan" : m));
  };
  const planMode = mode === "lighting" ? "electric" : "design";
  const plan = <PlanView scene={scene} mode={readOnly ? "readonly" : planMode} issues={v.version.issues} selected={sel || room || null} dims={tool === "measure" || mode === "plan"}
    onSelect={(id, kind) => { if (kind === "object") setSel(id); else if (kind === "room" && id) { setRoom(id); setSel(null); } else setSel(null); }}
    onMove={(id, x, y) => update(id, { x, y, source: "manual" })} height="100%" />;
  const three = <Scene3D scene={scene} height="100%" highlight={sel} onPick={setSel} {...(curRoom ? { mode: "room" as const, roomId: curRoom.id } : {})} />;

  return (
    <div className="col gap-10 editor">
      <div className="ed-head">
        <div className="row gap-8"><Link to={`/app/p/${pid}`} className="icon-btn" aria-label={t("common.back")}><ArrowLeft size={18} /></Link>
          <div><b>{project?.title || variantTitle(v)}</b><div className="tiny muted">{variantTitle(v)} · {t("ed.meta", { n: v.version.number, objects: objs.length })}</div></div></div>
        <div className="seg ed-modes" role="tablist">{([["plan", LayoutPanelTop], ["3d", Box], ["materials", Flower2], ["lighting", Lamp]] as [Mode, LucideIcon][]).map(([k, I]) =>
          <button key={k} role="tab" aria-selected={mode === k} className={mode === k ? "on" : ""} onClick={() => setMode(k)}><I size={15} /> {t(`ed.mode.${k}`)}</button>)}</div>
        <div className="row gap-6 wrap">
          <button className="icon-btn" onClick={undo} disabled={!past.length} aria-label={t("ed.undo")} title={t("ed.undo")}><Undo2 size={17} /></button>
          <button className="icon-btn" onClick={redo} disabled={!future.length} aria-label={t("ed.redo")} title={t("ed.redo")}><Redo2 size={17} /></button>
          <span className={`small row gap-4 ${dirty ? "" : "ok-text"}`}>{!dirty && <CheckCircle2 size={15} />} {state}</span>
          <label className="check small"><input type="checkbox" checked={autosave} onChange={(e) => setAutosave(e.target.checked)} /> {t("ed.autosave")}</label>
          <button className="btn outline-terra" onClick={() => setCmd(true)} disabled={readOnly}><Sparkles size={16} /> {t("cta.ai_change")}</button>
          <button className="btn" disabled={!dirty || saving} onClick={() => save()}><Save size={16} /> {t("ed.save_version")}</button>
          {project && <button className="btn primary" onClick={() => { navigator.clipboard?.writeText(`${location.origin}/client/${project.share_token}`); toast(t("common.link_copied")); }}><Share2 size={16} /> {t("ed.share")}</button>}
        </div>
      </div>

      <div className="row gap-6 ed-rooms" role="tablist" aria-label={t("ed.rooms")}>
        <button className={`room-tab ${!room ? "on" : ""}`} onClick={() => setRoom("")}><b>{t("ed.all_rooms")}</b><span className="tiny muted">{n1(scene.rooms.reduce((s, r) => s + polyArea(r.polygon), 0))} {t("common.m2")}</span></button>
        {scene.rooms.map((r) => <button key={r.id} role="tab" aria-selected={room === r.id} className={`room-tab ${room === r.id ? "on" : ""}`} onClick={() => { setRoom(r.id); setSel(null); }}>
          <b>{rName(r)}</b><span className="tiny muted">{n1(polyArea(r.polygon))} {t("common.m2")}</span></button>)}
      </div>

      <div className="ed-body">
        <nav className="ed-rail" aria-label={t("ed.tools")}>{TOOLS.map(([k, I]) => <button key={k} className={tool === k ? "on" : ""} onClick={() => clickTool(k)} title={t(`ed.tool.${k}`)}><I size={20} /><span>{t(`ed.tool.${k}`)}</span></button>)}</nav>

        <div className="card ed-canvas">
          <div className={`ed-views ${mode === "3d" ? "one" : mode === "plan" ? "two" : "one"}`} style={{ ["--z" as string]: zoom / 100 }}>
            {mode !== "3d" && <div className="ed-plan"><div className="ed-zoom">{plan}</div></div>}
            {(mode === "3d" || mode === "plan") && <div className="ed-3d">{three}</div>}
          </div>
          <div className="ed-bar">
            <button className="icon-btn" onClick={() => setZoom((z) => Math.max(50, z - 10))} aria-label={t("lb.zoom_out")}><Minus size={15} /></button>
            <span className="small mono" style={{ width: 48, textAlign: "center" }}>{zoom}%</span>
            <button className="icon-btn" onClick={() => setZoom((z) => Math.min(250, z + 10))} aria-label={t("lb.zoom_in")}><Plus size={15} /></button>
            <button className="icon-btn" aria-label={t("lb.open")} title={t("lb.open")} onClick={() => openBig([{ kind: "view", caption: t("ed.mode.plan"), render: () => <PlanView scene={scene} height="100%" dims /> },
              { kind: "view", caption: t("ed.mode.3d"), render: () => <Scene3D scene={scene} height="100%" quality="high" /> }], mode === "3d" ? 1 : 0)}><Maximize2 size={15} /></button>
            <span className="tiny muted grow">{t("ed.help")}</span>
            <Badge tone={v.mode === "concept" ? "warn" : "sage"}>{v.mode === "concept" ? t("res.mode_concept") : t("res.mode_real")}</Badge>
          </div>
        </div>

        <aside className="col gap-10 ed-side">
          {o ? (
            <div className="card pad col gap-10">
              <div className="row between"><h3>{o.code || "—"} · {catName(o.category)}</h3>{o.locked && <Badge tone="dark">{t("ed.locked")}</Badge>}</div>
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
                <button className="btn sm danger" onClick={() => { commit({ objs: objs.filter((x) => x.id !== o.id) }); setSel(null); }} disabled={o.locked}><Trash2 size={14} /> {t("common.delete")}</button>
              </div>
              <button className="btn sm ghost" onClick={() => setSel(null)}>{t("ed.back_to_room")}</button>
            </div>
          ) : curRoom ? (
            <div className="card pad col gap-10">
              <h3>{t("ed.room_props")}</h3>
              <label className="field"><span>{t("ed.f.name")}</span><input className="input" value={curRoom.source === "manual" ? curRoom.name : rName(curRoom)} disabled={readOnly}
                onChange={(e) => editRoom(curRoom.id, { name: e.target.value })} /></label>
              <div className="grid g2">
                <div className="field"><span className="tiny muted">{t("ed.f.area")}</span><b className="mono">{n1(polyArea(curRoom.polygon))} {t("common.m2")}</b></div>
                <div className="field"><span className="tiny muted">{t("ed.f.perimeter")}</span><b className="mono">{n1(perimeter(curRoom.polygon))} {t("common.m")}</b></div>
              </div>
              <label className="field"><span>{t("ed.f.ceiling")}</span><input className="input" inputMode="numeric" value={curRoom.ceiling_height} disabled={readOnly}
                onChange={(e) => { const n = Number(e.target.value); if (n) editRoom(curRoom.id, { ceiling_height: n }); }} /></label>
              <div className="divider" />
              <b>{t("ed.finishes")}</b>
              {SURFACES.map(([sf]) => {
                const f = fins.find((x) => x.room_id === curRoom.id && x.surface === sf);
                return <button key={sf} className="finish-row" disabled={readOnly} onClick={() => setPicker(sf)}>
                  <span className="sw" style={{ background: f?.color_hex || "#eee" }} /><span className="grow"><span className="tiny muted">{t(`ed.surface.${sf}`)}</span><br /><span className="small">{f?.name || t("ed.not_set")}</span></span><span className="muted">›</span></button>;
              })}
            </div>
          ) : <div className="card pad small muted">{t("ed.pick_room")}</div>}

          <div className="card pad col gap-6">
            <div className="row between"><b>{t("ed.budget")}</b><span className="tiny muted">{v.mode === "concept" ? t("res.mode_concept") : t("res.mode_real")}</span></div>
            <div className="row between"><b className="mono">{amd(est.totals.known)}</b>{budget ? <span className="small muted">{t("ed.of_budget", { v: amd(budget) })}</span> : null}</div>
            {budget ? <div className={`bar ${est.totals.known > budget ? "terra" : ""}`}><i style={{ width: `${Math.min(100, (est.totals.known / budget) * 100)}%` }} /></div> : null}
            <div className="tiny muted">{dirty ? t("ed.after_save") : t("ed.estimate_note")}</div>
            <Link className="btn sm" to={`/app/p/${pid}`}>{t("ed.view_estimate")}</Link>
          </div>
          <div className="card pad col gap-6">
            <b>{t("ed.checks", { n: issues.length })}</b>
            {issues.length === 0 && <div className="small" style={{ color: "var(--sage-ink)" }}>{t("ed.no_issues")}</div>}
            {issues.slice(0, 8).map((i, k) => <button key={k} className={`alert ${i.severity === "block" ? "danger" : "warn"} small`} style={{ textAlign: "left", cursor: "pointer" }}
              onClick={() => setSel(i.element_ids.find((id) => objs.some((x) => x.id === id)) || null)}>{ruleMessage(i)}</button>)}
          </div>
        </aside>
      </div>

      {!readOnly && <CatalogStrip group={tool === "decor" ? "decor" : undefined} room={curRoom ? rName(curRoom) : rName(scene.rooms[0])} onAdd={addProduct} />}

      <Drawer open={!!picker} onClose={() => setPicker(null)} title={picker ? `${t(`ed.surface.${picker}`)} · ${curRoom ? rName(curRoom) : ""}` : ""}>
        {picker && <FinishPicker cats={SURFACES.find(([s]) => s === picker)![1]} onPick={(it) => setFinish(picker, it)} />}
      </Drawer>
      <CommandDrawer open={cmd} onClose={() => setCmd(false)} pid={pid!} vid={vid!} onApplied={load} />
      <AlternativesDrawer pid={pid!} vid={vid!} objectId={alt} onClose={() => setAlt(null)} onReplaced={load} />
    </div>
  );
}

function ProductCard({ it, onClick, cta }: { it: Item; onClick: () => void; cta: string }) {
  const { t } = useT();
  return (
    <button className="strip-card" onClick={onClick} title={cta}>
      <div className="img" style={it.image_url ? { backgroundImage: `url(${it.image_url})` } : { background: `linear-gradient(135deg, ${it.color_hex || "#d9c9b7"}, #f6f1ea)` }} />
      <div className="col gap-4" style={{ padding: "8px 10px", textAlign: "left" }}>
        <b className="small clamp2">{it.name}</b>
        <span className="tiny muted">{it.w ? `${Math.round(it.w)}×${Math.round(it.d)}×${Math.round(it.h)} ${t("common.mm")}` : catName(it.category)}</span>
        <b className="small mono">{it.price_amd == null ? t("common.on_request") : amd(it.price_amd)}</b>
        <span className="tiny"><span className={`dot ${it.stock === "in_stock" ? "ok" : ""}`} /> {it.stock === "in_stock" ? t("common.in_stock") : it.stock === "to_order" ? t("common.to_order") : t("common.stock_unknown")}</span>
      </div>
    </button>
  );
}

/** Catalogue strip under the canvas: pick a group, search, click to place the product in the current room. */
function CatalogStrip({ group: forced, room, onAdd }: { group?: string; room: string; onAdd: (it: Item) => void }) {
  const { t } = useT();
  const [group, setGroup] = useState(forced || "furniture");
  const [q, setQ] = useState("");
  const [items, setItems] = useState<Item[] | null>(null);
  useEffect(() => { if (forced) setGroup(forced); }, [forced]);
  useEffect(() => {
    setItems(null);
    const p = new URLSearchParams({ group, limit: "40" });
    if (q) p.set("q", q);
    const tm = setTimeout(() => api<{ items: Item[] }>(`/catalog/products?${p}`).then((r) => setItems(r.items)).catch(() => setItems([])), 250);
    return () => clearTimeout(tm);
  }, [group, q]);
  return (
    <section className="card ed-strip" aria-labelledby="strip-h">
      <div className="row between wrap gap-8" style={{ padding: "10px 14px 0" }}>
        <div className="row gap-4 wrap"><b id="strip-h" style={{ marginRight: 8 }}>{t("ed.catalog")}</b>
          {STRIP_GROUPS.map((g) => <button key={g} className={`tab ${group === g ? "on" : ""}`} onClick={() => setGroup(g)}>{t(`enum.group.${g}`)}</button>)}</div>
        <label className="row gap-4 input" style={{ height: 34, width: 260 }}><Search size={15} /><input aria-label={t("common.search")} placeholder={t("ed.search_products")} value={q} onChange={(e) => setQ(e.target.value)} style={{ border: 0, outline: 0, background: "transparent", width: "100%" }} /></label>
      </div>
      <div className="strip-row">
        {!items ? <span className="spinner" /> : !items.length ? <span className="small muted">{t("common.nothing_found")}</span>
          : items.map((it) => <ProductCard key={it.ref} it={it} onClick={() => onAdd(it)} cta={t("ed.add_to", { room })} />)}
      </div>
      <div className="tiny muted" style={{ padding: "0 14px 10px" }}>{t("ed.strip_hint", { room })}</div>
    </section>
  );
}

function FinishPicker({ cats, onPick }: { cats: string[]; onPick: (it: Item) => void }) {
  const { t } = useT();
  const [items, setItems] = useState<Item[] | null>(null);
  useEffect(() => {
    Promise.all(cats.map((c) => api<{ items: Item[] }>(`/catalog/products?category=${c}&limit=40`).then((r) => r.items).catch(() => [] as Item[])))
      .then((l) => setItems(l.flat()));
  }, [cats]);
  if (!items) return <Loading />;
  if (!items.length) return <div className="small muted">{t("common.nothing_found")}</div>;
  return <div className="col gap-6">{items.map((it) => (
    <button key={it.ref} className="finish-row" onClick={() => onPick(it)}>
      <span className="sw" style={it.image_url ? { backgroundImage: `url(${it.image_url})`, backgroundSize: "cover" } : { background: it.color_hex }} />
      <span className="grow" style={{ textAlign: "left" }}><span className="small">{it.name}</span><br /><span className="tiny muted">{catName(it.category)} · {it.supplier_name}</span></span>
      <span className="col" style={{ alignItems: "flex-end" }}><b className="small mono">{it.price_amd == null ? t("common.on_request") : amd(it.price_amd)}</b><PriceStatus s={it.price_status} /></span>
    </button>))}</div>;
}
