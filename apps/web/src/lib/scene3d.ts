// Builds a Three.js group from the normalised scene (millimetres, plan Y down).
// World: X = plan X, Z = plan Y, Y = height; 1 unit = 1 metre.
// quality "high" adds procedural PBR textures, rounded furniture, trims and
// interior lights (landing / client viewer); "fast" keeps the editor light.
import * as THREE from "three";
import { RoundedBoxGeometry } from "three/examples/jsm/geometries/RoundedBoxGeometry.js";
import type { Opening, Scene, SceneObject, Wall } from "./api";
import { concrete, fabric, herringbone, planks, plaster, rug, tiles, veneer } from "./textures";

const S = 0.001;
export interface BuildOpts { furnished?: boolean; raw?: boolean; wallHeight?: number; highlight?: string | null; hideRooms?: Set<string>; quality?: "fast" | "high" }

function len(w: Wall) { return Math.hypot(w.b[0] - w.a[0], w.b[1] - w.a[1]); }
function along(w: Wall, t: number): [number, number] { const L = len(w) || 1; return [w.a[0] + ((w.b[0] - w.a[0]) * t) / L, w.a[1] + ((w.b[1] - w.a[1]) * t) / L]; }

export function solidSegments(w: Wall, ops: Opening[]): [number, number][] {
  const L = len(w);
  const cuts = ops.filter((o) => o.wall_id === w.id).map((o) => [Math.max(0, o.offset), Math.min(L, o.offset + o.width)] as [number, number]).sort((a, b) => a[0] - b[0]);
  const out: [number, number][] = [];
  let cur = 0;
  for (const [s, e] of cuts) { if (s > cur) out.push([cur, s]); cur = Math.max(cur, e); }
  if (cur < L) out.push([cur, L]);
  return out.filter(([s, e]) => e - s > 1);
}

const matCache = new Map<string, THREE.MeshStandardMaterial>();
function mat(color: string, opts: Partial<THREE.MeshStandardMaterialParameters> = {}) {
  const key = color + JSON.stringify(opts, (k, v) => (k === "map" ? (v as THREE.Texture)?.uuid : v));
  if (!matCache.has(key)) matCache.set(key, new THREE.MeshStandardMaterial({ color, roughness: 0.85, metalness: 0.02, ...opts }));
  return matCache.get(key)!;
}
function texMat(tex: THREE.Texture, repeat: number, opts: Partial<THREE.MeshStandardMaterialParameters> = {}) {
  const t = tex.clone();
  t.needsUpdate = true;
  t.repeat.set(repeat, repeat);
  return new THREE.MeshStandardMaterial({ map: t, roughness: 0.75, metalness: 0, ...opts });
}

function wallBox(w: Wall, s: number, e: number, z0: number, z1: number, material: THREE.Material, thickness = w.thickness, offsetN = 0) {
  const L = e - s;
  const geo = new THREE.BoxGeometry(L * S, (z1 - z0) * S, thickness * S);
  const m = new THREE.Mesh(geo, material);
  const [cx, cy] = along(w, (s + e) / 2);
  const ux = (w.b[0] - w.a[0]) / (len(w) || 1), uy = (w.b[1] - w.a[1]) / (len(w) || 1);
  m.position.set((cx + uy * offsetN) * S, ((z0 + z1) / 2) * S, (cy - ux * offsetN) * S);
  m.rotation.y = -Math.atan2(w.b[1] - w.a[1], w.b[0] - w.a[0]);
  m.castShadow = true; m.receiveShadow = true;
  return m;
}

/** Object meshes in the object's local frame (front = +Z after rotation 0 → plan +Y). */
function objectMesh(o: SceneObject, highlight: boolean, hq: boolean): THREE.Object3D {
  const g = new THREE.Group();
  const soft = ["sofa", "armchair", "bed", "kids_bed", "dining_chair", "desk_chair", "bench"].includes(o.category);
  const base = hq ? (soft ? texMat(fabric(o.color_hex), 3, { roughness: 0.95 }) : texMat(veneer(o.color_hex), 1, { roughness: 0.55 }))
    : mat(o.color_hex, highlight ? { emissive: new THREE.Color("#c97f63"), emissiveIntensity: 0.35 } : {});
  if (highlight && hq) { (base as THREE.MeshStandardMaterial).emissive = new THREE.Color("#c97f63"); (base as THREE.MeshStandardMaterial).emissiveIntensity = 0.3; }
  const dark = mat(new THREE.Color(o.color_hex).multiplyScalar(0.62).getStyle(), { roughness: 0.5 });
  const linen = hq ? texMat(fabric("#f3efe8"), 4, { roughness: 1 }) : mat("#efe9e1");
  const metal = mat("#2b2b2b", { metalness: 0.7, roughness: 0.35 });
  const ceramic = mat("#fbfbfa", { roughness: 0.15, metalness: 0.05 });
  const add = (x: number, z: number, w: number, d: number, y0: number, h: number, m: THREE.Material, r = 0) => {
    const rr = hq ? Math.min(r, w / 2 - 1, d / 2 - 1, h / 2 - 1) : 0;
    const geo = rr > 2 ? new RoundedBoxGeometry(w * S, Math.max(h, 5) * S, d * S, 3, rr * S) : new THREE.BoxGeometry(w * S, Math.max(h, 5) * S, d * S);
    const b = new THREE.Mesh(geo, m);
    b.position.set(x * S, (y0 + h / 2) * S, z * S); b.castShadow = true; b.receiveShadow = true; g.add(b);
    return b;
  };
  const cyl = (x: number, z: number, rTop: number, rBot: number, y0: number, h: number, m: THREE.Material) => {
    const c = new THREE.Mesh(new THREE.CylinderGeometry(rTop * S, rBot * S, h * S, 28), m);
    c.position.set(x * S, (y0 + h / 2) * S, z * S); c.castShadow = true; c.receiveShadow = true; g.add(c); return c;
  };
  const { w, d, h } = o;
  switch (o.category) {
    case "sofa": {
      add(0, 0.05 * d, w - 40, 0.8 * d, 80, 200, base, 40); // frame
      const seats = Math.max(2, Math.round(w / 900));
      for (let i = 0; i < seats; i++) {
        const sw = (w - 360) / seats;
        add(-w / 2 + 180 + sw * (i + 0.5), 0.12 * d, sw - 20, 0.62 * d, 280, 160, base, 60);
        add(-w / 2 + 180 + sw * (i + 0.5), -0.3 * d, sw - 30, 0.22 * d, 300, h - 330, base, 70);
      }
      add(-w / 2 + 90, 0.02 * d, 180, d - 40, 80, 520, base, 70); add(w / 2 - 90, 0.02 * d, 180, d - 40, 80, 520, base, 70);
      add(-w / 2 + 380, -0.12 * d, 380, 120, 440, 340, hq ? texMat(fabric("#c97f63"), 2) : dark, 60);
      for (const sx of [-1, 1]) for (const sz of [-1, 1]) cyl((sx * (w - 160)) / 2, (sz * (d - 120)) / 2, 18, 14, 0, 80, metal);
      break;
    }
    case "armchair": add(0, 0.1 * d, w - 80, 0.75 * d, 120, 260, base, 60); add(0, -0.38 * d, w - 40, 0.22 * d, 120, h - 120, base, 70); add(-w / 2 + 60, 0, 120, d - 80, 120, 450, base, 50); add(w / 2 - 60, 0, 120, d - 80, 120, 450, base, 50);
      for (const sx of [-1, 1]) for (const sz of [-1, 1]) cyl((sx * (w - 140)) / 2, (sz * (d - 140)) / 2, 16, 12, 0, 120, dark); break;
    case "bed": case "kids_bed": {
      add(0, 0.02 * d, w, d - 60, 100, 220, base, 30);
      add(0, 0.05 * d, w - 60, d - 160, 320, 200, linen, 60); // mattress + duvet
      add(0, 0.18 * d, w - 40, d * 0.62, 470, 60, hq ? texMat(fabric("#e6ddd0"), 4) : light(), 40);
      add(0, -d / 2 + 50, w + 40, 100, 0, h, base, 30); // headboard
      const pillows = o.category === "bed" ? 2 : 1;
      for (let i = 0; i < pillows; i++) add((pillows === 1 ? 0 : (i - 0.5) * (w * 0.46)), -d / 2 + 300, (w - 200) / pillows - 40, 300, 520, 140, linen, 60);
      add(0, 0.33 * d, w + 10, 380, 500, 40, hq ? texMat(fabric(o.color_hex), 3) : dark, 15); // throw
      break;
    }
    case "dining_table": case "desk": case "coffee_table": {
      const top = hq ? texMat(veneer(o.color_hex), 1, { roughness: 0.35 }) : base;
      if (o.category === "coffee_table" && hq) { cyl(0, 0, Math.min(w, d) / 2, Math.min(w, d) / 2, h - 40, 40, top); cyl(0, 0, Math.min(w, d) / 3, Math.min(w, d) / 3, 0, h - 40, dark); break; }
      add(0, 0, w, d, h - 40, 40, top, 10); const lw = 50;
      for (const [sx, sz] of [[-1, -1], [1, -1], [1, 1], [-1, 1]]) add((sx * (w - lw - 60)) / 2, (sz * (d - lw - 60)) / 2, lw, lw, 0, h - 40, dark);
      if (o.category === "dining_table" && hq) { cyl(0, 0, 90, 70, h, 140, mat("#e9e1d6", { roughness: 0.3 })); }
      break;
    }
    case "dining_chair": case "desk_chair": add(0, 0.05 * d, w - 30, d - 60, 420, 70, base, 30); add(0, -d / 2 + 30, w - 40, 50, 470, h - 470, base, 20);
      for (const [sx, sz] of [[-1, -1], [1, -1], [1, 1], [-1, 1]]) cyl((sx * (w - 80)) / 2, (sz * (d - 80)) / 2, 14, 12, 0, 420, dark); break;
    case "kitchen_run": {
      const front = hq ? texMat(veneer(o.color_hex), 1, { roughness: 0.4 }) : base;
      add(0, 0.02 * d, w, d - 20, 100, 760, front); add(0, 0, w, d, 0, 100, dark);
      add(0, 0.01 * d, w + 10, d + 20, 860, 40, mat("#ece7df", { roughness: 0.25 }));
      add(0, -d / 2 + 175, w, 350, 1500, 750, front);
      add(0, -d / 2 + 2, w, 4, 900, 600, hq ? texMat(tiles("#e8e2d9", false), 1, { roughness: 0.2 }) : mat("#ddd5ca"));
      const n = Math.max(3, Math.round(w / 600));
      for (let i = 0; i < n; i++) { const x = -w / 2 + (w / n) * (i + 0.5); add(x, d / 2 + 6, 160, 12, 780, 14, metal); add(x, -d / 2 + 354, 160, 12, 1520, 14, metal); }
      add(w * 0.18, 0.05 * d, 560, 480, 899, 6, mat("#1e1e1e", { roughness: 0.15 })); // hob
      add(-w * 0.22, 0.05 * d, 500, 400, 885, 18, mat("#bfc4c7", { metalness: 0.8, roughness: 0.2 })); // sink
      break;
    }
    case "wardrobe": case "hallway_wardrobe": case "storage_system": {
      const front = hq ? texMat(veneer(o.color_hex), 1, { roughness: 0.45 }) : base;
      add(0, 0, w, d, 0, h, front, 6);
      const n = Math.max(2, Math.round(w / 500));
      for (let i = 1; i < n; i++) add(-w / 2 + (w * i) / n, d / 2, 6, 6, 40, h - 80, dark);
      for (let i = 0; i < n; i++) add(-w / 2 + (w * (i + 0.5)) / n + ((i % 2) * 2 - 1) * (w / n / 2 - 60), d / 2 + 8, 14, 12, 900, 260, metal);
      break;
    }
    case "rug": add(0, 0, w, d, 0, 10, hq ? texMat(rug(o.color_hex), 1, { roughness: 1 }) : base); break;
    case "plant": {
      cyl(0, 0, w * 0.28, w * 0.22, 0, 420, mat("#d8cfc4", { roughness: 0.6 }));
      const leaf = mat("#5f7d4e", { roughness: 0.7 });
      const leaf2 = mat("#7d9468", { roughness: 0.7 });
      for (let i = 0; i < (hq ? 14 : 1); i++) {
        const s = new THREE.Mesh(new THREE.SphereGeometry(((w / 2) * (0.35 + (i % 4) * 0.12)) * S, 14, 10), i % 2 ? leaf : leaf2);
        const a = i * 2.4;
        s.position.set(Math.cos(a) * w * 0.18 * S, (h * (0.45 + (i % 5) * 0.11)) * S, Math.sin(a) * w * 0.18 * S);
        s.scale.set(1, 1.3, 1); s.castShadow = true; g.add(s);
      }
      break;
    }
    case "floor_lamp": cyl(0, 0, 130, 140, 0, 20, metal); cyl(0, 0, 12, 12, 0, h - 200, metal);
      { const sh = new THREE.Mesh(new THREE.CylinderGeometry(0.12, 0.2, 0.28, 24, 1, true), mat("#f6efe3", { emissive: new THREE.Color("#ffe2b3"), emissiveIntensity: 0.8, side: THREE.DoubleSide })); sh.position.y = (h - 140) * S; g.add(sh); } break;
    case "toilet": add(0, 0.1 * d, w, d * 0.78, 300, 120, ceramic, 60); add(0, 0.1 * d, w - 60, d * 0.7, 120, 180, ceramic, 60); add(0, -d / 2 + 60, w + 60, 120, 0, 1100, mat("#e9e5df", { roughness: 0.3 }), 10); break;
    case "vanity": add(0, 0, w, d, 300, 500, base, 10); add(0, 0.03 * d, w, d, 800, 50, ceramic, 20); cyl(0, -d / 2 + 70, 15, 15, 850, 180, metal);
      add(0, -d / 2 + 10, w * 0.9, 20, 1000, 800, mat("#d9e3e8", { metalness: 0.9, roughness: 0.05 })); break;
    case "bathtub": add(0, 0, w, d, 0, 580, ceramic, 60); add(0, 0, w - 140, d - 140, 470, 112, mat("#e6eff3", { roughness: 0.1 }), 40); break;
    case "fridge": add(0, 0, w, d, 0, h, mat("#d7d5d1", { metalness: 0.5, roughness: 0.3 }), 10); add(w / 2 - 50, d / 2 + 10, 20, 20, 900, 500, metal); break;
    case "washer": add(0, 0, w, d, 0, h, ceramic, 15); { const door = new THREE.Mesh(new THREE.TorusGeometry(0.15, 0.025, 12, 32), metal); door.position.set(0, 0.45, (d / 2 + 5) * S); g.add(door); } break;
    case "mirror": add(0, 0, w, 20, o.elevation, h, mat("#d9e3e8", { metalness: 0.9, roughness: 0.05 })); break;
    case "nightstand": case "dresser": case "shoe_cabinet": case "tv_unit": {
      add(0, 0, w, d, 120, h - 120, base, 8); for (const sx of [-1, 1]) for (const sz of [-1, 1]) cyl((sx * (w - 60)) / 2, (sz * (d - 60)) / 2, 12, 10, 0, 120, dark);
      if (o.category === "nightstand" && hq) { cyl(0, 0, 70, 90, h, 200, mat("#e9e1d6", { emissive: new THREE.Color("#ffd9a0"), emissiveIntensity: 0.4 })); }
      if (o.category === "tv_unit" && hq) { add(0, -d / 2 + 30, 1450, 40, 1000, 830, mat("#111111", { roughness: 0.2, metalness: 0.4 })); }
      break;
    }
    default: add(0, 0, w, d, o.elevation || 0, h, base, 10);
  }
  g.position.set(o.x * S, 0, o.y * S);
  g.rotation.y = (-o.rotation * Math.PI) / 180;
  g.userData = { objectId: o.id };
  return g;
  function light() { return mat("#efe9e1"); }
}

function floorMaterial(scene: Scene, roomId: string, raw: boolean, hq: boolean) {
  if (raw) return hq ? texMat(concrete("#9e9a95"), 0.6, { roughness: 1 }) : mat("#9c9893", { roughness: 1 });
  const fin = scene.finishes?.find((f) => f.room_id === roomId && f.surface === "floor");
  const color = fin?.color_hex || "#c9a882";
  if (!hq) return mat(color, { roughness: 0.7 });
  if (fin?.pattern === "large_tile" || fin?.pattern === "tile_grid") return texMat(tiles(color, fin.pattern === "large_tile"), 0.42, { roughness: 0.25 });
  if (fin?.pattern === "herringbone") return texMat(herringbone(color), 0.8, { roughness: 0.5 });
  return texMat(planks(color), 0.5, { roughness: 0.55 });
}

export function buildScene(scene: Scene, opts: BuildOpts = {}): THREE.Group {
  const root = new THREE.Group();
  const hq = opts.quality === "high";
  const H = opts.wallHeight ?? scene.ceiling_height;
  const wallColor = scene.finishes?.find((f) => f.surface === "walls")?.color_hex || "#f2ede6";
  const wallMat = opts.raw ? (hq ? texMat(concrete("#b0aca6"), 0.8, { roughness: 1 }) : mat("#a9a5a0", { roughness: 1 })) : (hq ? texMat(plaster(wallColor), 2, { roughness: 0.9 }) : mat("#f2ede6"));
  const glass = new THREE.MeshPhysicalMaterial({ color: "#cfe1ec", transparent: true, opacity: 0.28, roughness: 0.02, metalness: 0, transmission: hq ? 0.6 : 0 });
  const frame = mat(opts.raw ? "#8b8f92" : "#f7f5f2", { roughness: 0.4 });
  const sill = mat("#e8e2da", { roughness: 0.3 });
  const trim = mat("#ffffff", { roughness: 0.5 });
  const cap = mat(opts.raw ? "#6f6b66" : "#2e2a27", { roughness: 0.9 }); // poché on the cut plane
  for (const w of scene.walls) {
    if (w.status === "demolish" && !opts.raw) continue;
    if (w.status === "new" && opts.raw) continue;
    for (const [s, e] of solidSegments(w, scene.openings)) {
      root.add(wallBox(w, s, e, 0, H, wallMat));
      if (hq) root.add(wallBox(w, s, e, H, H + 8, cap));
      if (hq && !opts.raw) for (const side of [-1, 1]) root.add(wallBox(w, s, e, 0, 80, trim, 14, side * (w.thickness / 2 + 7)));
    }
    for (const o of scene.openings.filter((x) => x.wall_id === w.id)) {
      const head = o.type === "window" ? o.sill + o.height : o.height;
      if (head < H) { root.add(wallBox(w, o.offset, o.offset + o.width, head, H, wallMat)); if (hq) root.add(wallBox(w, o.offset, o.offset + o.width, H, H + 8, cap)); }
      if (o.type === "window") {
        if (o.sill > 0) root.add(wallBox(w, o.offset, o.offset + o.width, 0, Math.min(o.sill, H), wallMat));
        if (o.sill < H) {
          const top = Math.min(head, H);
          root.add(wallBox(w, o.offset, o.offset + o.width, o.sill, top, glass, 24));
          if (hq) {
            root.add(wallBox(w, o.offset, o.offset + o.width, o.sill - 30, o.sill, sill, w.thickness + 80));
            for (const t of [o.offset, o.offset + o.width / 2, o.offset + o.width]) root.add(wallBox(w, t - 25, t + 25, o.sill, top, frame, 70));
            root.add(wallBox(w, o.offset, o.offset + o.width, top - 50, top, frame, 70));
          }
        }
      } else if (hq && !opts.raw && ["door", "entrance_door", "balcony_door"].includes(o.type)) {
        // door leaf shown ajar (~25°), plus casing
        const side = o.swing === "left" ? 1 : -1;
        const hingeT = o.hinge === "start" ? o.offset : o.offset + o.width;
        const [hx, hy] = along(w, hingeT);
        const ux = (w.b[0] - w.a[0]) / (len(w) || 1), uy = (w.b[1] - w.a[1]) / (len(w) || 1);
        const dir = o.hinge === "start" ? 1 : -1;
        const ang = Math.atan2(uy, ux) + dir * side * (-0.45);
        const leaf = new THREE.Mesh(new THREE.BoxGeometry(o.width * S, (o.height - 10) * S, 40 * S), o.type === "entrance_door" ? mat("#3b332d", { roughness: 0.4 }) : mat("#f3efe9", { roughness: 0.45 }));
        leaf.position.set((hx + Math.cos(ang) * dir * o.width / 2 + uy * side * (w.thickness / 2) * -1) * S, (o.height / 2) * S, (hy + Math.sin(ang) * dir * o.width / 2 - ux * side * (w.thickness / 2) * -1) * S);
        leaf.rotation.y = -ang;
        leaf.castShadow = true;
        root.add(leaf);
        for (const t of [o.offset - 30, o.offset + o.width + 30]) root.add(wallBox(w, t - 30, t + 30, 0, o.height + 40, trim, w.thickness + 20));
      }
    }
  }
  for (const r of scene.rooms) {
    if (opts.hideRooms?.has(r.id)) continue;
    const shape = new THREE.Shape(r.polygon.map(([x, y]) => new THREE.Vector2(x * S, -y * S)));
    const geo = new THREE.ShapeGeometry(shape);
    // planar UVs in metres so textures keep real-world scale
    const pos = geo.attributes.position as THREE.BufferAttribute;
    const uv = new Float32Array(pos.count * 2);
    for (let i = 0; i < pos.count; i++) { uv[i * 2] = pos.getX(i); uv[i * 2 + 1] = pos.getY(i); }
    geo.setAttribute("uv", new THREE.BufferAttribute(uv, 2));
    const m = new THREE.Mesh(geo, floorMaterial(scene, r.id, !!opts.raw, hq));
    m.rotation.x = -Math.PI / 2;
    m.position.y = 0.002;
    m.receiveShadow = true;
    m.userData = { roomId: r.id };
    root.add(m);
  }
  if (opts.furnished !== false && !opts.raw) {
    for (const o of scene.objects) {
      if (opts.hideRooms?.has(o.room_id)) continue;
      root.add(objectMesh(o, opts.highlight === o.id, hq));
    }
    for (const li of scene.lights || []) {
      if (li.type === "pendant") {
        const y = Math.min(H, scene.ceiling_height) - 750;
        const shadeMesh = new THREE.Mesh(new THREE.SphereGeometry(0.13, 24, 16, 0, Math.PI * 2, 0, Math.PI / 1.7), mat("#f4ead8", { emissive: new THREE.Color("#ffd6a0"), emissiveIntensity: 1.2, side: THREE.DoubleSide }));
        shadeMesh.position.set(li.position[0] * S, y * S, li.position[1] * S);
        shadeMesh.rotation.x = Math.PI;
        root.add(shadeMesh);
        if (hq) {
          const cord = new THREE.Mesh(new THREE.CylinderGeometry(0.004, 0.004, (Math.min(H, scene.ceiling_height) - y) * S, 6), mat("#222"));
          cord.position.set(li.position[0] * S, ((Math.min(H, scene.ceiling_height) + y) / 2) * S, li.position[1] * S);
          root.add(cord);
          const p = new THREE.PointLight("#ffcf94", 1.6, 4.5, 1.8);
          p.position.set(li.position[0] * S, (y - 120) * S, li.position[1] * S);
          root.add(p);
        }
      }
    }
    if (hq) {
      // curtains beside windows of living rooms and bedrooms
      const curtain = texMat(fabric("#efe7db"), 3, { roughness: 1, side: THREE.DoubleSide });
      for (const o of scene.openings.filter((x) => x.type === "window" || x.type === "balcony_door")) {
        const w = scene.walls.find((x) => x.id === o.wall_id);
        if (!w || w.kind !== "exterior") continue;
        const room = scene.rooms.find((r) => ["bedroom", "kids", "living", "kitchen_living"].includes(r.type) && r.polygon.some(([x, y]) => Math.hypot(x - along(w, o.offset)[0], y - along(w, o.offset)[1]) < 3000));
        if (!room) continue;
        for (const t of [o.offset - 160, o.offset + o.width + 160]) {
          const c = wallBox(w, t - 160, t + 160, 60, Math.min(H, scene.ceiling_height) - 120, curtain, 50, (w.thickness / 2 + 90) * (inRoomSide(w, room) ? 1 : -1));
          root.add(c);
        }
      }
    }
  }
  return root;
}

function inRoomSide(w: Wall, room: { polygon: [number, number][] }) {
  const [mx, my] = along(w, len(w) / 2);
  const ux = (w.b[0] - w.a[0]) / (len(w) || 1), uy = (w.b[1] - w.a[1]) / (len(w) || 1);
  const px = mx + uy * 400, py = my - ux * 400;
  let c = false;
  const p = room.polygon;
  for (let i = 0, j = p.length - 1; i < p.length; j = i++) {
    const [xi, yi] = p[i], [xj, yj] = p[j];
    if (yi > py !== yj > py && px < ((xj - xi) * (py - yi)) / (yj - yi || 1e-9) + xi) c = !c;
  }
  return c;
}

export function sceneBounds(scene: Scene) {
  const xs = scene.walls.flatMap((w) => [w.a[0], w.b[0]]);
  const ys = scene.walls.flatMap((w) => [w.a[1], w.b[1]]);
  if (!xs.length) return { cx: 0, cz: 0, size: 10 };
  const x0 = Math.min(...xs), x1 = Math.max(...xs), y0 = Math.min(...ys), y1 = Math.max(...ys);
  return { cx: ((x0 + x1) / 2) * S, cz: ((y0 + y1) / 2) * S, size: Math.max(x1 - x0, y1 - y0) * S };
}

export function addLights(scene3: THREE.Scene, bounds: { cx: number; cz: number; size: number }, hq = false) {
  scene3.add(new THREE.HemisphereLight("#fffaf2", hq ? "#d8cbbb" : "#b9a68f", hq ? 0.55 : 1.15));
  const sun = new THREE.DirectionalLight("#fff1dc", hq ? 2.2 : 1.6);
  sun.position.set(bounds.cx + bounds.size * 0.55, bounds.size * 1.3, bounds.cz - bounds.size * 0.8);
  sun.target.position.set(bounds.cx, 0, bounds.cz);
  sun.castShadow = true;
  sun.shadow.mapSize.set(hq ? 4096 : 2048, hq ? 4096 : 2048);
  sun.shadow.bias = -0.0004;
  sun.shadow.normalBias = 0.02;
  sun.shadow.radius = hq ? 6 : 1;
  const d = bounds.size * 0.8;
  Object.assign(sun.shadow.camera, { left: -d, right: d, top: d, bottom: -d, near: 0.1, far: bounds.size * 4 });
  scene3.add(sun, sun.target);
  if (hq) {
    // ground slab under the dollhouse with a soft contact shadow
    const ground = new THREE.Mesh(new THREE.PlaneGeometry(bounds.size * 4, bounds.size * 4), new THREE.ShadowMaterial({ opacity: 0.22 }));
    ground.rotation.x = -Math.PI / 2;
    ground.position.set(bounds.cx, -0.001, bounds.cz);
    ground.receiveShadow = true;
    scene3.add(ground);
  }
}
