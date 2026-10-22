import { useEffect, useRef, useState } from "react";
import { api } from "../lib/api";
import { translate } from "../i18n";

// Autodesk Platform Services Viewer (SVF2). The browser only gets a short-lived
// viewables:read token from our API — client secrets never leave the server.
const VIEWER_VER = "7.99";
declare global { interface Window { Autodesk?: any } }

function loadViewer(): Promise<void> {
  if (window.Autodesk?.Viewing) return Promise.resolve();
  return new Promise((resolve, reject) => {
    const css = document.createElement("link");
    css.rel = "stylesheet";
    css.href = `https://developer.api.autodesk.com/modelderivative/v2/viewers/${VIEWER_VER}/style.min.css`;
    document.head.appendChild(css);
    const s = document.createElement("script");
    s.src = `https://developer.api.autodesk.com/modelderivative/v2/viewers/${VIEWER_VER}/viewer3D.min.js`;
    s.onload = () => resolve();
    s.onerror = () => reject(new Error(translate("aps.viewer_load_failed")));
    document.head.appendChild(s);
  });
}

export default function ApsViewer({ urn, height = 480 }: { urn: string; height?: number }) {
  const host = useRef<HTMLDivElement>(null);
  const [err, setErr] = useState("");
  useEffect(() => {
    let viewer: any;
    let cancelled = false;
    (async () => {
      try {
        await loadViewer();
        const A = window.Autodesk;
        // optOutTrackingByDefault: the viewer must not send usage telemetry to third parties (privacy; also blocked by CSP)
        await new Promise<void>((res) => A.Viewing.Initializer({ env: "AutodeskProduction2", api: "streamingV2", optOutTrackingByDefault: true, getAccessToken: async (cb: (t: string, e: number) => void) => {
          const t = await api<{ access_token: string; expires_in: number }>("/aps/viewer-token"); cb(t.access_token, t.expires_in);
        } }, () => res()));
        try { A.Viewing.Private?.analytics?.optOut?.(); } catch { /* older viewer builds */ }
        if (cancelled || !host.current) return;
        viewer = new A.Viewing.GuiViewer3D(host.current);
        viewer.start();
        A.Viewing.Document.load(`urn:${urn}`, (doc: any) => viewer.loadDocumentNode(doc, doc.getRoot().getDefaultGeometry()), (code: number, msg: string) => setErr(`APS: ${code} ${msg}`));
      } catch (e) { setErr((e as Error).message); }
    })();
    return () => { cancelled = true; viewer?.finish?.(); };
  }, [urn]);
  return <div style={{ position: "relative", height, borderRadius: 12, overflow: "hidden", background: "#e9e4dd" }}>
    <div ref={host} style={{ position: "absolute", inset: 0 }} />
    {err && <div className="alert danger" style={{ position: "absolute", left: 12, right: 12, top: 12 }}>{err}</div>}
  </div>;
}
