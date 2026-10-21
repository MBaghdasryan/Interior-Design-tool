// Procedural PBR-ish textures generated on a canvas (no binary assets in the repo).
// Each texture is cached by key; repeat is set by the caller in metres.
import * as THREE from "three";

const cache = new Map<string, THREE.CanvasTexture>();

function rng(seed: number) {
  let s = seed >>> 0;
  return () => ((s = (s * 1664525 + 1013904223) >>> 0) / 4294967296);
}
function shade(hex: string, f: number) {
  const c = new THREE.Color(hex);
  const hsl = { h: 0, s: 0, l: 0 };
  c.getHSL(hsl);
  c.setHSL(hsl.h, hsl.s, Math.max(0, Math.min(1, hsl.l * f)));
  return `#${c.getHexString()}`;
}
function make(key: string, size: number, draw: (g: CanvasRenderingContext2D, r: () => number) => void, color = true) {
  const k = `${key}:${size}`;
  if (cache.has(k)) return cache.get(k)!;
  const cv = document.createElement("canvas");
  cv.width = cv.height = size;
  const g = cv.getContext("2d")!;
  draw(g, rng(key.split("").reduce((a, ch) => a * 31 + ch.charCodeAt(0), 7)));
  const t = new THREE.CanvasTexture(cv);
  t.wrapS = t.wrapT = THREE.RepeatWrapping;
  t.anisotropy = 8;
  if (color) t.colorSpace = THREE.SRGBColorSpace;
  cache.set(k, t);
  return t;
}
function grain(g: CanvasRenderingContext2D, r: () => number, x: number, y: number, w: number, h: number, base: string, along: "x" | "y") {
  g.fillStyle = base;
  g.fillRect(x, y, w, h);
  const n = along === "x" ? h / 2 : w / 2;
  for (let i = 0; i < n; i++) {
    g.strokeStyle = shade(base, 0.86 + r() * 0.22);
    g.globalAlpha = 0.18 + r() * 0.2;
    g.lineWidth = 0.6 + r() * 1.2;
    g.beginPath();
    if (along === "x") { const yy = y + r() * h; g.moveTo(x, yy); g.bezierCurveTo(x + w * 0.3, yy + (r() - 0.5) * 3, x + w * 0.7, yy + (r() - 0.5) * 3, x + w, yy); }
    else { const xx = x + r() * w; g.moveTo(xx, y); g.bezierCurveTo(xx + (r() - 0.5) * 3, y + h * 0.3, xx + (r() - 0.5) * 3, y + h * 0.7, xx, y + h); }
    g.stroke();
  }
  g.globalAlpha = 1;
}

/** Herringbone parquet; one texture tile ≈ 1.2 m. */
export function herringbone(color: string) {
  return make(`hb-${color}`, 1024, (g, r) => {
    g.fillStyle = shade(color, 0.7); g.fillRect(0, 0, 1024, 1024);
    const L = 256, W = 64;
    for (let row = -4; row < 20; row++) {
      for (let col = -4; col < 12; col++) {
        const ox = col * 2 * W + row * W * 0, oy = row * W * 2 + col * W * 2;
        const tone = shade(color, 0.86 + r() * 0.28);
        g.save(); g.translate(ox, oy % 1600 - 300); g.rotate(Math.PI / 4);
        grain(g, r, 0, 0, L, W, tone, "x"); g.strokeStyle = shade(color, 0.55); g.globalAlpha = 0.6; g.strokeRect(0, 0, L, W); g.globalAlpha = 1;
        g.translate(L, 0); g.rotate(Math.PI / 2);
        grain(g, r, 0, 0, L, W, shade(color, 0.86 + r() * 0.28), "x"); g.strokeStyle = shade(color, 0.55); g.globalAlpha = 0.6; g.strokeRect(0, 0, L, W); g.globalAlpha = 1;
        g.restore();
      }
    }
  });
}

/** Plank floor; tile ≈ 2 m. */
export function planks(color: string) {
  return make(`pl-${color}`, 1024, (g, r) => {
    const W = 1024 / 9;
    for (let i = 0; i < 9; i++) {
      let y = -r() * 600;
      while (y < 1024) {
        const L = 380 + r() * 420;
        grain(g, r, i * W, y, W, L, shade(color, 0.85 + r() * 0.3), "y");
        g.strokeStyle = shade(color, 0.5); g.globalAlpha = 0.55; g.strokeRect(i * W, y, W, L); g.globalAlpha = 1;
        y += L;
      }
    }
  });
}

/** Porcelain tile grid; tile = 600 mm, texture = 4×4 tiles. */
export function tiles(color: string, large = true) {
  return make(`tl-${color}-${large}`, 1024, (g, r) => {
    const n = large ? 4 : 8, s = 1024 / n;
    for (let i = 0; i < n; i++) for (let j = 0; j < n; j++) {
      g.fillStyle = shade(color, 0.95 + r() * 0.08); g.fillRect(i * s, j * s, s, s);
      for (let k = 0; k < 40; k++) { g.fillStyle = shade(color, 0.8 + r() * 0.35); g.globalAlpha = 0.08; g.beginPath(); g.ellipse(i * s + r() * s, j * s + r() * s, 4 + r() * 30, 2 + r() * 10, r() * 3, 0, 7); g.fill(); }
      g.globalAlpha = 1;
    }
    g.strokeStyle = shade(color, 0.72); g.lineWidth = 3;
    for (let i = 0; i <= n; i++) { g.beginPath(); g.moveTo(i * s, 0); g.lineTo(i * s, 1024); g.stroke(); g.beginPath(); g.moveTo(0, i * s); g.lineTo(1024, i * s); g.stroke(); }
  });
}

/** Raw concrete / screed for the "before" shell. */
export function concrete(color = "#a9a5a0") {
  return make(`cc-${color}`, 512, (g, r) => {
    g.fillStyle = color; g.fillRect(0, 0, 512, 512);
    for (let i = 0; i < 9000; i++) { g.fillStyle = shade(color, 0.75 + r() * 0.5); g.globalAlpha = 0.12; g.fillRect(r() * 512, r() * 512, 1 + r() * 3, 1 + r() * 3); }
    for (let i = 0; i < 14; i++) { g.fillStyle = shade(color, 0.85 + r() * 0.25); g.globalAlpha = 0.15; g.beginPath(); g.ellipse(r() * 512, r() * 512, 30 + r() * 120, 20 + r() * 80, r() * 3, 0, 7); g.fill(); }
    g.globalAlpha = 0.25; g.strokeStyle = shade(color, 0.7);
    for (let i = 0; i < 6; i++) { g.beginPath(); g.arc(r() * 512, r() * 512, 2, 0, 7); g.stroke(); }
    g.globalAlpha = 1;
  });
}

/** Fine plaster / painted wall noise. */
export function plaster(color: string) {
  return make(`ps-${color}`, 256, (g, r) => {
    g.fillStyle = color; g.fillRect(0, 0, 256, 256);
    for (let i = 0; i < 4000; i++) { g.fillStyle = shade(color, 0.94 + r() * 0.1); g.globalAlpha = 0.25; g.fillRect(r() * 256, r() * 256, 1, 1); }
    g.globalAlpha = 1;
  });
}

/** Woven fabric for upholstery, bedding, curtains. */
export function fabric(color: string) {
  return make(`fb-${color}`, 256, (g, r) => {
    g.fillStyle = color; g.fillRect(0, 0, 256, 256);
    for (let y = 0; y < 256; y += 2) { g.fillStyle = shade(color, 0.93 + r() * 0.08); g.globalAlpha = 0.5; g.fillRect(0, y, 256, 1); }
    for (let x = 0; x < 256; x += 2) { g.fillStyle = shade(color, 0.95 + r() * 0.08); g.globalAlpha = 0.35; g.fillRect(x, 0, 1, 256); }
    g.globalAlpha = 1;
  });
}

/** Rug with a soft border pattern. */
export function rug(color: string) {
  return make(`rg-${color}`, 512, (g, r) => {
    g.fillStyle = shade(color, 1.05); g.fillRect(0, 0, 512, 512);
    g.strokeStyle = shade(color, 0.75); g.lineWidth = 14; g.strokeRect(28, 28, 456, 456);
    g.lineWidth = 3; g.strokeRect(54, 54, 404, 404);
    for (let i = 0; i < 12000; i++) { g.fillStyle = shade(color, 0.85 + r() * 0.3); g.globalAlpha = 0.18; g.fillRect(r() * 512, r() * 512, 2, 2); }
    g.globalAlpha = 1;
  });
}

/** Wood veneer for cabinetry and tables. */
export function veneer(color: string) {
  return make(`vn-${color}`, 512, (g, r) => grain(g, r, 0, 0, 512, 512, color, "x"));
}
