import { useEffect, useMemo, useState } from "react";
import { useParams } from "react-router-dom";
import { CheckCircle2, MessageSquare, Send, ShoppingCart } from "lucide-react";
import { api, type SceneObject, type Variant } from "../lib/api";
import { amd, catName, lineName, variantTitle } from "../lib/format";
import { useT } from "../i18n";
import BeforeAfter from "../components/BeforeAfter";
import PlanView from "../components/PlanView";
import Scene3D from "../components/Scene3D";
import { EstimateSummary, Notices } from "../components/EstimateView";
import { AccuracyBadge, Badge, Loading, PriceStatus, useToast } from "../components/ui";
import { LangSwitch, Logo } from "../components/AppShell";

interface CV { project: { title: string; address: string; area_m2: number; accuracy_level: string; status: string }; variants: Variant[]; comments: { id: string; body: string; author_name: string; variant_id: string | null; anchor: { object_id?: string }; created_at: string }[] }

// Mobile-first approval flow for the end client (opened by share link, no account).
export default function ClientViewer() {
  const { t } = useT();
  const { token } = useParams();
  const toast = useToast();
  const [d, setD] = useState<CV | null>(null);
  const [idx, setIdx] = useState(0);
  const [tab, setTab] = useState<"look" | "plan" | "cost" | "talk">("look");
  const [name, setName] = useState(() => { try { return localStorage.getItem("forma.client.name") || ""; } catch { return ""; } });
  const [text, setText] = useState("");
  const [anchor, setAnchor] = useState<SceneObject | null>(null);
  const load = () => api<CV>(`/client/${token}`).then(setD).catch((e) => toast(e.message, true));
  useEffect(() => { load(); }, [token]);  // eslint-disable-line react-hooks/exhaustive-deps
  const v = d?.variants[idx];
  const comments = useMemo(() => d?.comments.filter((c) => !c.variant_id || c.variant_id === v?.id) || [], [d, v]);
  if (!d) return <Loading />;
  if (!v?.version) return <div className="empty">{t("cv.preparing")}</div>;
  const scene = v.version.scene;
  const est = v.version.estimate;
  const remember = () => { try { localStorage.setItem("forma.client.name", name); } catch { /* ignore */ } };
  const send = async () => {
    if (!name || !text) { toast(t("cv.need_name"), true); return; }
    remember();
    await api(`/client/${token}/comments`, { method: "POST", json: { name, body: text, variant_id: v.id, anchor: anchor ? { object_id: anchor.id } : {} } });
    setText(""); setAnchor(null); toast(t("cv.comment_sent")); load();
  };
  const decide = async (decision: "approved" | "changes_requested") => {
    if (!name) { toast(t("cv.need_name_only"), true); setTab("talk"); return; }
    remember();
    await api(`/client/${token}/decision`, { method: "POST", json: { name, variant_id: v.id, decision } });
    toast(decision === "approved" ? t("cv.approved_msg") : t("cv.changes_msg"));
  };
  return (
    <div style={{ maxWidth: 760, margin: "0 auto", paddingBottom: 90 }}>
      <header className="row between wrap" style={{ padding: 16 }}><div className="row"><Logo size={26} /><b>{d.project.title}</b></div><div className="row"><LangSwitch compact /><AccuracyBadge level={d.project.accuracy_level} /></div></header>
      <div className="row" style={{ padding: "0 16px", overflowX: "auto" }}>{d.variants.map((x, i) => <button key={x.id} className={`chip ${i === idx ? "on" : ""}`} onClick={() => setIdx(i)}>{variantTitle(x)}{x.status === "approved" && " ✓"}</button>)}</div>
      <div className="tabs" style={{ padding: "0 8px", marginTop: 8 }}>
        {(["look", "plan", "cost", "talk"] as const).map((k) => <button key={k} className={`tab ${tab === k ? "on" : ""}`} onClick={() => setTab(k)}>{t(`cv.tab.${k}`, { n: comments.length })}</button>)}
      </div>
      <div style={{ padding: 16 }} className="col gap-16">
        {tab === "look" && <>
          <div className="card" style={{ overflow: "hidden" }}><BeforeAfter scene={scene} height={340} quality="high" /></div>
          <div className="grid g2">{scene.rooms.filter((r) => ["kitchen_living", "bedroom", "living", "kids"].includes(r.type)).map((r) => <div key={r.id} className="canvas-wrap" style={{ height: 200 }}><Scene3D scene={scene} mode="room" roomId={r.id} height={200} /><span className="label-pill" style={{ left: 8, top: "auto", bottom: 8, padding: "3px 10px", fontSize: 12, background: "rgba(46,46,46,.7)" }}>{t(`enum.room.${r.type}`)}</span></div>)}</div>
          <p className="muted">{t(`enum.style_sub.${v.style}`)}</p>
        </>}
        {tab === "plan" && <>
          <div className="card" style={{ overflow: "hidden" }}><PlanView scene={scene} height={360} hotspots onHotspot={(o) => { setAnchor(o); setTab("talk"); }} /></div>
          <p className="small muted">{t("cv.plan_hint")}</p>
          {est.lines.filter((l) => l.ref && ["furniture", "custom", "lighting", "plumbing"].includes(l.group)).map((l) => (
            <div key={l.id} className="product-row"><div className="thumb" style={{ background: l.color_hex || "#eee" }} /><div><b className="small">{lineName(l)}</b><div className="tiny muted">{catName(l.category)} · {l.supplier}</div><PriceStatus s={l.price_status} /></div><b className="mono small">{l.total === null ? t("common.on_request") : amd(l.total)}</b></div>
          ))}
        </>}
        {tab === "cost" && <div className="card pad"><div className="muted small">{t("cv.estimate")}</div><div style={{ fontSize: 26, fontWeight: 800 }} className="mono">{amd(est.totals.known)}</div>
          <div className="mt-16"><EstimateSummary est={est} /></div><div className="mt-8"><Notices est={est} /></div></div>}
        {tab === "talk" && <div className="col gap-10">
          {comments.map((c) => <div key={c.id} className="card pad small"><div className="row between"><b>{c.author_name}</b>{c.anchor.object_id && <Badge>{scene.objects.find((o) => o.id === c.anchor.object_id)?.code}</Badge>}</div><p className="mt-8">{c.body}</p></div>)}
          <div className="card pad col gap-6">
            <input className="input" placeholder={t("cv.name_ph")} value={name} onChange={(e) => setName(e.target.value)} />
            {anchor && <div className="row small"><MessageSquare size={14} /> {t("cv.about_item")} <b>{anchor.code} {catName(anchor.category)}</b><button className="btn sm ghost" onClick={() => setAnchor(null)} aria-label={t("common.close")}>×</button></div>}
            <textarea className="input" rows={3} placeholder={t("cv.comment_ph")} value={text} onChange={(e) => setText(e.target.value)} />
            <button className="btn" onClick={send}><Send size={15} /> {t("common.send")}</button>
          </div>
        </div>}
      </div>
      <div style={{ position: "fixed", left: 0, right: 0, bottom: 0, background: "var(--surface)", borderTop: "1px solid var(--line)", padding: 12 }}>
        <div className="row" style={{ maxWidth: 760, margin: "0 auto" }}>
          <div className="grow"><div className="tiny muted">{variantTitle(v)}</div><b className="mono">{amd(est.totals.known)}</b></div>
          <button className="btn" onClick={() => decide("changes_requested")}>{t("cv.changes")}</button>
          <button className="btn primary" onClick={() => decide("approved")}><CheckCircle2 size={16} /> {t("cv.approve")}</button>
          <button className="icon-btn hide-sm" onClick={() => setTab("cost")} aria-label={t("cv.tab.cost")}><ShoppingCart size={16} /></button>
        </div>
      </div>
    </div>
  );
}
