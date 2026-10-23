import { createContext, useCallback, useContext, useEffect, useRef, useState, type ReactNode } from "react";
import { ChevronLeft, ChevronRight, Minus, Plus, RotateCcw, X } from "lucide-react";
import { useT } from "../i18n";

/** One item of the viewer: a picture (render, photo) or a live view (3D dollhouse, plan) rendered large. */
export type LightItem = { kind: "image"; src: string; caption?: string } | { kind: "view"; render: () => ReactNode; caption?: string };

const Ctx = createContext<(items: LightItem[], index?: number) => void>(() => {});
export const useLightbox = () => useContext(Ctx);

export function LightboxProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<{ items: LightItem[]; i: number } | null>(null);
  const open = useCallback((items: LightItem[], index = 0) => setState({ items, i: index }), []);
  return <Ctx.Provider value={open}>{children}{state && <Viewer items={state.items} index={state.i} onIndex={(i) => setState({ ...state, i })} onClose={() => setState(null)} />}</Ctx.Provider>;
}

/** Wraps anything clickable that should open large. Keyboard: Enter/Space. */
export function Zoomable({ items, index = 0, children, className = "", style }: { items: LightItem[]; index?: number; children: ReactNode; className?: string; style?: React.CSSProperties }) {
  const open = useLightbox();
  const { t } = useT();
  return (
    <div className={`zoomable ${className}`} style={style} role="button" tabIndex={0} aria-label={t("lb.open")} title={t("lb.open")}
      onClick={(e) => { if (!(e.target as HTMLElement).closest("button, a, input, select")) open(items, index); }}
      onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); open(items, index); } }}>
      {children}
    </div>
  );
}

function Viewer({ items, index, onIndex, onClose }: { items: LightItem[]; index: number; onIndex: (i: number) => void; onClose: () => void }) {
  const { t } = useT();
  const [zoom, setZoom] = useState(1);
  const [pan, setPan] = useState({ x: 0, y: 0 });
  const drag = useRef<{ x: number; y: number } | null>(null);
  const it = items[index];
  const go = useCallback((d: number) => { onIndex((index + d + items.length) % items.length); setZoom(1); setPan({ x: 0, y: 0 }); }, [index, items.length, onIndex]);
  useEffect(() => {
    const k = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
      if (e.key === "ArrowRight" && items.length > 1) go(1);
      if (e.key === "ArrowLeft" && items.length > 1) go(-1);
      if (e.key === "+" || e.key === "=") setZoom((z) => Math.min(4, z + 0.5));
      if (e.key === "-") setZoom((z) => Math.max(1, z - 0.5));
    };
    window.addEventListener("keydown", k);
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => { window.removeEventListener("keydown", k); document.body.style.overflow = prev; };
  }, [go, items.length, onClose]);
  return (
    <div className="lightbox" role="dialog" aria-modal="true" aria-label={it.caption || t("lb.title")}>
      <div className="lb-top">
        <span className="small">{it.caption}{items.length > 1 ? ` · ${index + 1} / ${items.length}` : ""}</span>
        <div className="row gap-6">
          {it.kind === "image" && <>
            <button className="icon-btn" onClick={() => setZoom((z) => Math.max(1, z - 0.5))} aria-label={t("lb.zoom_out")}><Minus size={16} /></button>
            <span className="small mono" style={{ minWidth: 48, textAlign: "center" }}>{Math.round(zoom * 100)}%</span>
            <button className="icon-btn" onClick={() => setZoom((z) => Math.min(4, z + 0.5))} aria-label={t("lb.zoom_in")}><Plus size={16} /></button>
            <button className="icon-btn" onClick={() => { setZoom(1); setPan({ x: 0, y: 0 }); }} aria-label={t("lb.reset")}><RotateCcw size={16} /></button>
          </>}
          <button className="icon-btn" onClick={onClose} aria-label={t("common.close")}><X size={18} /></button>
        </div>
      </div>
      <div className="lb-stage" onClick={(e) => { if (e.target === e.currentTarget) onClose(); }}
        onWheel={(e) => { if (it.kind === "image") setZoom((z) => Math.min(4, Math.max(1, z - Math.sign(e.deltaY) * 0.25))); }}>
        {it.kind === "image"
          ? <img src={it.src} alt={it.caption || ""} draggable={false} style={{ transform: `translate(${pan.x}px, ${pan.y}px) scale(${zoom})`, cursor: zoom > 1 ? "grab" : "zoom-in" }}
            onClick={() => zoom === 1 && setZoom(2)}
            onPointerDown={(e) => { if (zoom > 1) { drag.current = { x: e.clientX - pan.x, y: e.clientY - pan.y }; (e.target as HTMLElement).setPointerCapture(e.pointerId); } }}
            onPointerMove={(e) => { if (drag.current) setPan({ x: e.clientX - drag.current.x, y: e.clientY - drag.current.y }); }}
            onPointerUp={() => { drag.current = null; }} />
          : <div className="lb-view">{it.render()}</div>}
        {items.length > 1 && <>
          <button className="lb-nav prev" onClick={() => go(-1)} aria-label={t("lb.prev")}><ChevronLeft size={26} /></button>
          <button className="lb-nav next" onClick={() => go(1)} aria-label={t("lb.next")}><ChevronRight size={26} /></button>
        </>}
      </div>
      {it.kind === "view" && <div className="lb-hint tiny">{t("lb.view_hint")}</div>}
    </div>
  );
}
