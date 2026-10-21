import { useMemo, useRef, useState } from "react";
import type { Issue, Pt, Scene, SceneObject, Wall } from "../lib/api";
import { solidSegments } from "../lib/scene3d";
import { useT } from "../i18n";
import { n1 } from "../lib/format";

type Mode = "review" | "design" | "readonly" | "electric";
interface Props {
  scene: Scene;
  mode?: Mode;
  issues?: Issue[];
  selected?: string | null;
  onSelect?: (id: string | null, kind: "wall" | "room" | "object" | null) => void;
  onMove?: (id: string, x: number, y: number) => void;
  height?: number | string;
  hotspots?: boolean;
  onHotspot?: (o: SceneObject) => void;
  mask?: { walls: Record<string, string>; rooms: Record<string, string>; openings: Record<string, string> };
}

const ZONE: Record<string, string> = { day: "#f3e3d3", night: "#e5eadc", wet: "#dde8ef", service: "#efe9df", outdoor: "#eef0ea" };
const MASK: Record<string, string> = { green: "#5d8f4e", yellow: "#d6a21e", red: "#c8463d" };

function outline(w: Wall, s: number, e: number): Pt[] {
  const L = Math.hypot(w.b[0] - w.a[0], w.b[1] - w.a[1]) || 1;
  const ux = (w.b[0] - w.a[0]) / L, uy = (w.b[1] - w.a[1]) / L;
  const nx = uy, ny = -ux, h = w.thickness / 2;
  const p0: Pt = [w.a[0] + ux * s, w.a[1] + uy * s], p1: Pt = [w.a[0] + ux * e, w.a[1] + uy * e];
  return [[p0[0] + nx * h, p0[1] + ny * h], [p1[0] + nx * h, p1[1] + ny * h], [p1[0] - nx * h, p1[1] - ny * h], [p0[0] - nx * h, p0[1] - ny * h]];
}
const pts = (p: Pt[]) => p.map(([x, y]) => `${x.toFixed(0)},${y.toFixed(0)}`).join(" ");
function fp(o: SceneObject) { const r = Math.round(o.rotation) % 180 !== 0; const w = r ? o.d : o.w, d = r ? o.w : o.d; return { x0: o.x - w / 2, y0: o.y - d / 2, w, d }; }
function labelPoint(poly: Pt[]): Pt { const xs = poly.map((p) => p[0]), ys = poly.map((p) => p[1]); let cx = (Math.min(...xs) + Math.max(...xs)) / 2, cy = (Math.min(...ys) + Math.max(...ys)) / 2; if (!inside([cx, cy], poly)) { const c = poly.reduce((a, p) => [a[0] + p[0] / poly.length, a[1] + p[1] / poly.length], [0, 0]); cx = c[0]; cy = c[1]; } return [cx, cy]; }
function inside([x, y]: Pt, poly: Pt[]) { let c = false; for (let i = 0, j = poly.length - 1; i < poly.length; j = i++) { const [xi, yi] = poly[i], [xj, yj] = poly[j]; if (yi > y !== yj > y && x < ((xj - xi) * (y - yi)) / (yj - yi || 1e-9) + xi) c = !c; } return c; }
function area(poly: Pt[]) { let s = 0; for (let i = 0; i < poly.length; i++) { const [x1, y1] = poly[i], [x2, y2] = poly[(i + 1) % poly.length]; s += x1 * y2 - x2 * y1; } return Math.abs(s) / 2e6; }

export default function PlanView({ scene, mode = "readonly", issues = [], selected, onSelect, onMove, height = 520, hotspots, onHotspot, mask }: Props) {
  const { t } = useT();
  /** System-recognised rooms show the localised room type; user-renamed rooms keep their name. */
  const roomLabel = (r: { name: string; type: string; source: string }) => (r.source === "manual" ? r.name : t(`enum.room.${r.type}`));
  const svg = useRef<SVGSVGElement>(null);
  const [drag, setDrag] = useState<{ id: string; dx: number; dy: number } | null>(null);
  const [ghost, setGhost] = useState<{ id: string; x: number; y: number } | null>(null);
  const vb = useMemo(() => {
    const xs: number[] = [], ys: number[] = [];
    scene.walls.forEach((w) => { xs.push(w.a[0], w.b[0]); ys.push(w.a[1], w.b[1]); });
    scene.rooms.forEach((r) => r.polygon.forEach(([x, y]) => { xs.push(x); ys.push(y); }));
    if (!xs.length) return [0, 0, 10000, 8000];
    const pad = 700;
    return [Math.min(...xs) - pad, Math.min(...ys) - pad, Math.max(...xs) - Math.min(...xs) + 2 * pad, Math.max(...ys) - Math.min(...ys) + 2 * pad];
  }, [scene]);
  const issueBy = useMemo(() => {
    const m = new Map<string, "block" | "warning">();
    for (const i of issues) if (i.severity !== "pass") for (const id of i.element_ids) if (m.get(id) !== "block") m.set(id, i.severity as "block" | "warning");
    return m;
  }, [issues]);

  const toLocal = (e: React.PointerEvent) => {
    const s = svg.current!;
    const p = s.createSVGPoint();
    p.x = e.clientX; p.y = e.clientY;
    const q = p.matrixTransform(s.getScreenCTM()!.inverse());
    return [q.x, q.y] as Pt;
  };
  const objects = scene.objects.map((o) => (ghost && ghost.id === o.id ? { ...o, x: ghost.x, y: ghost.y } : o));

  return (
    <svg ref={svg} className="plan-svg" viewBox={vb.join(" ")} style={{ height }} role="img" aria-label={t("plan.aria")}
      onPointerMove={(e) => { if (!drag) return; const [x, y] = toLocal(e); setGhost({ id: drag.id, x: Math.round((x - drag.dx) / 25) * 25, y: Math.round((y - drag.dy) / 25) * 25 }); }}
      onPointerUp={() => { if (drag && ghost && onMove) onMove(ghost.id, ghost.x, ghost.y); setDrag(null); setGhost(null); }}
      onClick={(e) => { if (e.target === svg.current) onSelect?.(null, null); }}>
      <defs>
        <pattern id="hatchDemo" width="80" height="80" patternUnits="userSpaceOnUse" patternTransform="rotate(45)"><rect width="80" height="80" fill="#f8d7d5" /><line x1="0" y1="0" x2="0" y2="80" stroke="#c8463d" strokeWidth="18" /></pattern>
        <pattern id="hatchNew" width="80" height="80" patternUnits="userSpaceOnUse" patternTransform="rotate(-45)"><rect width="80" height="80" fill="#dcefd5" /><line x1="0" y1="0" x2="0" y2="80" stroke="#5d8f4e" strokeWidth="14" /></pattern>
      </defs>
      <rect x={vb[0]} y={vb[1]} width={vb[2]} height={vb[3]} fill="#fbf8f3" />
      {scene.rooms.map((r) => (
        <polygon key={r.id} points={pts(r.polygon)} fill={mode === "review" && mask ? `${MASK[mask.rooms[r.id]] || "#999"}22` : ZONE[r.zone || ""] || "#f4efe8"}
          stroke={selected === r.id ? "#a8573a" : "none"} strokeWidth={30} onClick={(e) => { e.stopPropagation(); onSelect?.(r.id, "room"); }} style={{ cursor: onSelect ? "pointer" : "default" }} />
      ))}
      {scene.walls.map((w) => {
        const segs = w.status === "demolish" ? [[0, Math.hypot(w.b[0] - w.a[0], w.b[1] - w.a[1])] as [number, number]] : solidSegments(w, scene.openings);
        const reviewColor = mode === "review" && mask ? MASK[mask.walls[w.id]] : null;
        const fill = w.status === "demolish" ? "url(#hatchDemo)" : w.status === "new" ? "url(#hatchNew)" : reviewColor || (w.material === "concrete" ? "#5b544d" : "#8a837c");
        return segs.map(([s, e], i) => (
          <polygon key={`${w.id}-${i}`} points={pts(outline(w, s, e))} fill={fill} stroke={selected === w.id ? "#a8573a" : "#3b3631"} strokeWidth={selected === w.id ? 40 : 8}
            onClick={(ev) => { ev.stopPropagation(); onSelect?.(w.id, "wall"); }} style={{ cursor: onSelect ? "pointer" : "default" }} />
        ));
      })}
      {scene.openings.map((o) => {
        const w = scene.walls.find((x) => x.id === o.wall_id);
        if (!w) return null;
        const L = Math.hypot(w.b[0] - w.a[0], w.b[1] - w.a[1]) || 1;
        const ux = (w.b[0] - w.a[0]) / L, uy = (w.b[1] - w.a[1]) / L, nx = uy, ny = -ux;
        const p0: Pt = [w.a[0] + ux * o.offset, w.a[1] + uy * o.offset], p1: Pt = [w.a[0] + ux * (o.offset + o.width), w.a[1] + uy * (o.offset + o.width)];
        const col = mode === "review" && mask ? MASK[mask.openings[o.id]] : undefined;
        if (o.type === "window") return <g key={o.id}>{[-w.thickness / 2, 0, w.thickness / 2].map((k) => <line key={k} x1={p0[0] + nx * k} y1={p0[1] + ny * k} x2={p1[0] + nx * k} y2={p1[1] + ny * k} stroke={col || "#4f7da3"} strokeWidth={18} />)}</g>;
        if (o.type === "sliding_door") return <line key={o.id} x1={p0[0]} y1={p0[1]} x2={p1[0]} y2={p1[1]} stroke={col || "#2e2e2e"} strokeWidth={30} />;
        if (o.type === "opening") return null;
        const side = o.swing === "left" ? 1 : -1;
        const [hinge, free] = o.hinge === "start" ? [p0, p1] : [p1, p0];
        const ht = w.thickness / 2;
        const h0: Pt = [hinge[0] + nx * ht * side, hinge[1] + ny * ht * side];
        const leaf: Pt = [h0[0] + nx * o.width * side, h0[1] + ny * o.width * side];
        const f0: Pt = [free[0] + nx * ht * side, free[1] + ny * ht * side];
        const cross = (leaf[0] - h0[0]) * (f0[1] - h0[1]) - (leaf[1] - h0[1]) * (f0[0] - h0[0]);
        return <g key={o.id}><line x1={h0[0]} y1={h0[1]} x2={leaf[0]} y2={leaf[1]} stroke={col || "#2e2e2e"} strokeWidth={22} />
          <path d={`M ${leaf[0]} ${leaf[1]} A ${o.width} ${o.width} 0 0 ${cross > 0 ? 1 : 0} ${f0[0]} ${f0[1]}`} fill="none" stroke="#7a7068" strokeWidth={8} strokeDasharray="40 30" /></g>;
      })}
      {scene.fixtures.filter((f) => f.type !== "warm_floor").map((f) => {
        const [w, d] = f.size || [180, 180];
        const c = { radiator: "#c97f63", riser_water: "#4f7da3", riser_sewer: "#6b6b6b", electrical_panel: "#d6a21e" }[f.type] || "#999";
        return <rect key={f.id} x={f.position[0] - w / 2} y={f.position[1] - d / 2} width={w} height={d} fill={c} opacity={0.85} />;
      })}
      {mode !== "review" && objects.map((o) => {
        const r = fp(o);
        const iss = issueBy.get(o.id);
        const sel = selected === o.id;
        const fx = -Math.sin((o.rotation * Math.PI) / 180), fy = Math.cos((o.rotation * Math.PI) / 180);
        return (
          <g key={o.id} style={{ cursor: mode === "design" ? (o.locked ? "not-allowed" : "move") : onSelect ? "pointer" : "default" }}
            onPointerDown={(e) => { if (mode !== "design" || o.locked) return; e.stopPropagation(); (e.target as Element).setPointerCapture?.(e.pointerId); const [x, y] = toLocal(e); setDrag({ id: o.id, dx: x - o.x, dy: y - o.y }); onSelect?.(o.id, "object"); }}
            onClick={(e) => { e.stopPropagation(); onSelect?.(o.id, "object"); }}>
            <rect x={r.x0} y={r.y0} width={r.w} height={r.d} rx={30} fill={o.color_hex} fillOpacity={o.category === "rug" ? 0.3 : 0.88}
              stroke={sel ? "#a8573a" : iss === "block" ? "#c8463d" : iss === "warning" ? "#d6a21e" : "#5b4636"} strokeWidth={sel ? 45 : iss ? 30 : 12} strokeDasharray={iss && !sel ? "60 40" : undefined} />
            {o.category !== "rug" && <line x1={o.x} y1={o.y} x2={o.x + fx * Math.min(r.w, r.d) * 0.42} y2={o.y + fy * Math.min(r.w, r.d) * 0.42} stroke="#5b4636" strokeWidth={10} />}
            {o.locked && <text x={r.x0 + 80} y={r.y0 + 170} fontSize={150}>🔒</text>}
            {o.category !== "rug" && <text x={o.x} y={o.y + 40} fontSize={120} textAnchor="middle" fill="#2e2e2e" fontWeight={700} style={{ pointerEvents: "none" }}>{o.code}</text>}
          </g>
        );
      })}
      {mode === "electric" && scene.electrical.map((e) => <g key={e.id}><circle cx={e.position[0]} cy={e.position[1]} r={70} fill={e.type.startsWith("switch") ? "#c8463d" : "#fff"} stroke="#2e2e2e" strokeWidth={14} /><text x={e.position[0] + 100} y={e.position[1] - 60} fontSize={90} fill="#2e2e2e">{e.code}</text></g>)}
      {mode === "electric" && scene.lights.map((l) => l.end ? <line key={l.id} x1={l.position[0]} y1={l.position[1]} x2={l.end[0]} y2={l.end[1]} stroke="#e0a800" strokeWidth={22} strokeDasharray="60 30" /> : <circle key={l.id} cx={l.position[0]} cy={l.position[1]} r={60} fill="#ffe7a3" stroke="#a87c00" strokeWidth={10} />)}
      {scene.rooms.map((r) => {
        const [cx, cy] = labelPoint(r.polygon);
        return <g key={`l-${r.id}`} style={{ pointerEvents: "none" }}>
          <circle cx={cx} cy={cy - 330} r={150} fill="#fff" stroke="#c97f63" strokeWidth={16} />
          <text x={cx} y={cy - 280} fontSize={150} textAnchor="middle" fill="#a8573a" fontWeight={800}>{r.number}</text>
          <text x={cx} y={cy - 30} fontSize={140} textAnchor="middle" fill="#2e2e2e" fontWeight={600}>{roomLabel(r)}</text>
          <text x={cx} y={cy + 150} fontSize={120} textAnchor="middle" fill="#8a8178">{n1(area(r.polygon))} {t("common.m2")}</text>
        </g>;
      })}
      {hotspots && scene.objects.filter((o) => !["rug", "dining_chair"].includes(o.category)).map((o) => (
        <g key={`h-${o.id}`} onClick={(e) => { e.stopPropagation(); onHotspot?.(o); }} style={{ cursor: "pointer" }}>
          <circle cx={o.x} cy={o.y} r={130} fill="#fff" stroke="#c97f63" strokeWidth={24} />
          <text x={o.x} y={o.y + 45} fontSize={120} textAnchor="middle" fill="#a8573a" fontWeight={800}>+</text>
        </g>
      ))}
    </svg>
  );
}
