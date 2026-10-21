import { useRef, useState } from "react";
import { Sparkles } from "lucide-react";
import type { Scene } from "../lib/api";
import Scene3D from "./Scene3D";
import { useT } from "../i18n";

/** Before/after of the same apartment: raw shell vs designed scene, one camera. */
export default function BeforeAfter({ scene, height = 460, interactive = true, quality = "fast" }: { scene: Scene; height?: number | string; interactive?: boolean; quality?: "fast" | "high" }) {
  const { t } = useT();
  const [pos, setPos] = useState(0.5);
  const box = useRef<HTMLDivElement>(null);
  const drag = (clientX: number) => {
    const r = box.current!.getBoundingClientRect();
    setPos(Math.min(0.95, Math.max(0.05, (clientX - r.left) / r.width)));
  };
  return (
    <div ref={box} className="before-after" style={{ height }}>
      <Scene3D scene={scene} split={pos} height={height} interactive={interactive} cutaway autoRotate={false} quality={quality}
        elevation={quality === "high" ? 0.95 : undefined} wallHeight={quality === "high" ? scene.ceiling_height : undefined} background={quality === "high" ? "#f1ece4" : undefined} />
      <span className="label-pill" style={{ left: 16, background: "rgba(46,46,46,.85)" }}>{t("common.before")}</span>
      <span className="label-pill" style={{ right: 16, background: "var(--terra-ink)" }}>{t("common.after")}</span>
      <div className="ba-handle" style={{ left: `${pos * 100}%` }}
        onPointerDown={(e) => { (e.target as Element).setPointerCapture(e.pointerId); }}
        onPointerMove={(e) => { if (e.buttons) drag(e.clientX); }}>
        <div className="ba-knob"><Sparkles size={22} /></div>
      </div>
    </div>
  );
}
