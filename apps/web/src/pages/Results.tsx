import { useCallback, useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { AlertTriangle, ArrowRight, Box, CalendarClock, CheckCircle2, ExternalLink, FileText, Image, LayoutPanelTop, ListChecks, Pencil, Receipt, Share2, ShoppingCart, Sparkles, Store, Truck, Wrench } from "lucide-react";
import { api, fileUrl, type Doc, type Project, type Scene, type Variant } from "../lib/api";
import { amd, catName, lineName, m2, n1, pct, roomType, variantSubtitle, variantTitle } from "../lib/format";
import { ruleMessage } from "../lib/messages";
import { tOr, useT } from "../i18n";
import Scene3D from "../components/Scene3D";
import PlanView from "../components/PlanView";
import EstimateView, { EstimateSummary } from "../components/EstimateView";
import CommandDrawer from "../components/CommandDrawer";
import AlternativesDrawer from "../components/AlternativesDrawer";
import RenderGallery from "../components/RenderGallery";
import TrustPanel from "../components/TrustPanel";
import PilotPanel from "../components/PilotPanel";
import { AccuracyBadge, Badge, Empty, Loading, Modal, PriceStatus, useToast } from "../components/ui";

type Tab = "plan" | "visuals" | "products" | "estimate" | "suppliers" | "timeline" | "checks";

export default function Results() {
  const { t, lang } = useT();
  const { pid } = useParams();
  const nav = useNavigate();
  const toast = useToast();
  const [project, setProject] = useState<Project | null>(null);
  const [variants, setVariants] = useState<Variant[]>([]);
  const [cur, setCur] = useState<Variant | null>(null);
  const [tab, setTab] = useState<Tab>("plan");
  const [cmdOpen, setCmdOpen] = useState(false);
  const [alt, setAlt] = useState<string | null>(null);
  const [approveOpen, setApproveOpen] = useState(false);
  const [view3d, setView3d] = useState(false);
  const [docs, setDocs] = useState<Doc[]>([]);

  const load = useCallback(async (keep?: string) => {
    const p = await api<Project>(`/projects/${pid}`);
    setProject(p);
    const vs: Variant[] = p.variants || [];
    setVariants(vs);
    const pick = vs.find((v) => v.id === keep) || vs.find((v) => v.status === "approved") || vs.find((v) => v.status === "selected") || vs[0];
    if (pick) setCur(await api<Variant>(`/projects/${pid}/variants/${pick.id}`));
    api<Doc[]>(`/projects/${pid}/documents`).then(setDocs).catch(() => {});
  }, [pid]);
  useEffect(() => { load(); }, [load]);

  const select = async (v: Variant) => {
    await api(`/projects/${pid}/variants/${v.id}/select`, { method: "POST" });
    setCur(await api<Variant>(`/projects/${pid}/variants/${v.id}`));
    setVariants((vs) => vs.map((x) => ({ ...x, status: x.id === v.id ? (x.status === "approved" ? "approved" : "selected") : x.status === "selected" ? "draft" : x.status })));
  };
  const recheck = async () => {
    try { await api(`/projects/${pid}/variants/${cur!.id}/recheck-prices`, { method: "POST" }); toast(t("estimate.recheck")); load(cur!.id); }
    catch (x) { toast((x as Error).message, true); }
  };

  const ver = cur?.version;
  const est = ver?.estimate;
  const scene = ver?.scene;
  const demo = (cur?.metrics.sourcing?.demo_fallback || 0) > 0 || (est?.totals.demo || 0) > 0;
  const keyProducts = useMemo(() => (est?.lines || []).filter((l) => l.ref && ["furniture", "custom", "lighting", "plumbing"].includes(l.group)).sort((a, b) => (b.total || 0) - (a.total || 0)).slice(0, 3), [est]);
  const suppliers = useMemo(() => {
    const m = new Map<string, { name: string; items: number; total: number; lead: number; demo: boolean }>();
    for (const l of est?.lines || []) {
      if (!l.supplier_key || ["delivery", "installation"].includes(l.group)) continue;
      const s = m.get(l.supplier_key) || { name: l.supplier || l.supplier_key, items: 0, total: 0, lead: 0, demo: !!l.is_demo };
      s.items += 1; s.total += l.total || 0; s.lead = Math.max(s.lead, l.lead_days || 0);
      m.set(l.supplier_key, s);
    }
    return [...m.entries()].sort((a, b) => b[1].total - a[1].total);
  }, [est]);

  if (!project) return <Loading />;
  if (!variants.length) return <Empty>{t("res.no_variants")} <Link className="btn sm primary" to={`/app/p/${pid}/upload`}>{t("res.run")}</Link></Empty>;
  if (!cur || !ver || !est || !scene) return <Loading />;
  const issues = ver.issues || [];
  const blocks = issues.filter((i) => i.severity === "block").length;
  const xlsx = docs.find((d) => d.kind === "xlsx");
  const feas = cur.metrics.feasibility;
  const stock = (s?: string, days?: number | null) => (s === "in_stock" ? t("common.in_stock") : s === "to_order" ? (days ? t("common.to_order_days", { n: days }) : t("common.to_order")) : t("common.stock_unknown"));
  const tabs: [Tab, typeof Box, string][] = [["plan", LayoutPanelTop, t("res.tab.plan")], ["visuals", Image, t("res.tab.visuals")], ["products", Box, t("res.tab.products", { n: scene.objects.length })],
    ["estimate", Receipt, t("res.tab.estimate")], ["suppliers", Store, t("res.tab.suppliers")], ["timeline", CalendarClock, t("res.tab.timeline")], ["checks", ListChecks, `${t("res.tab.checks")}${blocks ? ` (${blocks})` : ""}`]];

  return (
    <div className="col gap-16">
      <div className="row between wrap top">
        <div>
          <div className="row gap-16"><h1>{t("res.ready")}</h1><span className="muted" style={{ fontSize: 24 }}>{t("res.n_variants", { n: variants.length })}</span></div>
          <div className="row mt-8 wrap">
            {demo ? <><AlertTriangle size={18} color="var(--warn)" /><b>{t("res.demo_part")}</b><span className="muted small">{t("res.demo_hint")}</span></>
              : <><CheckCircle2 size={18} color="var(--sage-ink)" /><b>{t("res.real")}</b></>}
            <AccuracyBadge level={project.accuracy_level} /><Badge tone={cur.mode === "concept" ? "warn" : "sage"}>{cur.mode === "concept" ? t("res.mode_concept") : t("res.mode_real")}</Badge>
          </div>
        </div>
        <div className="checks">
          <Check ok={!est.budget || est.budget.within} title={t("res.check.budget")} sub={est.budget ? (est.budget.within ? t("res.check.budget_ok") : t("res.check.budget_over", { v: amd(est.budget.delta) })) : `${t(`enum.tier.${cur.tier}`)} · ${amd(est.totals.known)}`} />
          <Check ok={cur.metrics.availability_share > 0.6} title={t("res.check.real")} sub={t("res.check.real_sub", { v: pct(cur.metrics.availability_share) })} />
          <Check ok={blocks === 0} title={t("res.check.feas")} sub={t(feas >= 0.85 ? "res.feas.high" : feas >= 0.6 ? "res.feas.mid" : "res.feas.low", { v: pct(feas) })} />
        </div>
      </div>

      <div className="grid g3">
        {variants.map((v) => (
          <div key={v.id} className={`variant-card ${v.id === cur.id ? "on" : ""}`} onClick={() => select(v)} role="button" tabIndex={0} aria-pressed={v.id === cur.id}>
            {v.id === cur.id ? <Scene3D scene={scene} height="100%" interactive={false} cutaway /> : <VariantThumb pid={pid!} vid={v.id} />}
            <div className="cap"><b>{variantTitle(v)}</b><span className="small">{variantSubtitle(v)}</span><div className="small mono" style={{ opacity: 0.9 }}>{amd(v.metrics.total)}</div></div>
            {v.id === cur.id && <div className="tick"><CheckCircle2 size={18} /></div>}
            {v.status === "approved" && <div className="mode"><Badge tone="dark">{t("res.approved")}</Badge></div>}
          </div>
        ))}
      </div>

      <div className="grid" style={{ gridTemplateColumns: "minmax(0, 1fr) 380px", alignItems: "start" }}>
        <div className="card pad col gap-16">
          <div className="row between top wrap">
            <div className="col gap-6" style={{ maxWidth: 620 }}>
              <div className="row wrap"><h2>{variantTitle(cur)}</h2><Badge tone="terra">{cur.status === "approved" ? t("res.approved_variant") : t("res.selected")}</Badge><Badge>v{ver.number}</Badge></div>
              <div className="muted">{t("res.meta", { rooms: scene.rooms.filter((r) => r.type !== "balcony").length, area: m2(project.area_m2), city: project.city })}</div>
              <p>{lang === "ru" && cur.description ? cur.description : `${variantSubtitle(cur)}. ${t("res.desc_default")}`}</p>
            </div>
            <div className="col gap-6" style={{ minWidth: 300 }}>
              {cur.status === "approved" ? <Link className="btn primary lg" to={`/app/p/${pid}/procurement`}><ShoppingCart size={18} /> {t("res.cart")} <ArrowRight size={16} /></Link>
                : <button className="btn primary lg" onClick={() => setApproveOpen(true)}>{t("cta.approve")} <ArrowRight size={16} /></button>}
              <button className="btn outline-terra lg" onClick={() => setCmdOpen(true)} disabled={cur.status === "approved"}><Sparkles size={18} /> {t("cta.ai_change")}</button>
              <button className="btn lg" onClick={() => nav(`/app/p/${pid}/editor/${cur.id}`)} disabled={cur.status === "approved"}><Pencil size={16} /> {t("cta.manual")}</button>
            </div>
          </div>

          <div className="tabs">{tabs.map(([k, I, l]) => <button key={k} className={`tab ${tab === k ? "on" : ""}`} onClick={() => setTab(k)}><I size={16} /> {l}</button>)}</div>

          {tab === "plan" && (
            <div className="grid" style={{ gridTemplateColumns: "minmax(0,1.1fr) minmax(0,1fr)", alignItems: "start" }}>
              <div className="col gap-10">
                <div className="canvas-wrap">{view3d ? <Scene3D scene={scene} height={420} /> : <PlanView scene={scene} height={420} hotspots onHotspot={(o) => setAlt(o.id)} issues={issues} />}</div>
                <div className="row wrap"><button className="btn sm" onClick={() => setView3d(!view3d)}><Box size={14} /> {view3d ? t("res.show_plan") : t("res.show_3d")}</button><span className="small muted">{t("res.plus_hint")}</span></div>
              </div>
              <div className="col gap-10">
                <b>{t("res.explication")}</b>
                {scene.rooms.map((r) => <div key={r.id} className="row between small"><span className="row gap-6"><span className="badge terra" style={{ borderRadius: 999, width: 22, justifyContent: "center" }}>{r.number}</span>{r.source === "manual" ? r.name : roomType(r.type)}</span><span className="mono">{n1(area(r.polygon))} {t("common.m2")}</span></div>)}
                <div className="grid g2 mt-8">{scene.rooms.filter((r) => ["kitchen_living", "bedroom", "bathroom", "kids", "living"].includes(r.type)).slice(0, 4).map((r) => (
                  <div key={r.id} className="canvas-wrap" style={{ height: 150 }}><Scene3D scene={scene} mode="room" roomId={r.id} height={150} interactive={false} /><span className="label-pill" style={{ left: 8, top: "auto", bottom: 8, padding: "3px 10px", fontSize: 12, background: "rgba(46,46,46,.7)" }}>{roomType(r.type)}</span></div>))}</div>
              </div>
            </div>
          )}
          {tab === "visuals" && <Visuals scene={scene} pid={pid!} vid={cur.id} />}
          {tab === "products" && (
            <div className="col">
              {est.lines.filter((l) => l.ref && !["finishing", "works"].includes(l.group)).map((l) => {
                const obj = scene.objects.find((o) => o.product_variant_id === l.ref);
                return (
                  <div key={l.id} className="product-row">
                    <div className="thumb" style={{ background: l.color_hex || "#e8e2d9" }}><Box size={18} color="#fff" /></div>
                    <div className="col gap-4"><b>{lineName(l)}</b><div className="small muted">{catName(l.category)} · {l.supplier} · {l.sku}</div>
                      <div className="row wrap"><PriceStatus s={l.price_status} /><Badge tone={l.stock === "in_stock" ? "sage" : ""}>{stock(l.stock, l.lead_days)}</Badge>{l.warnings?.length ? <span className="tiny" style={{ color: "#8a5d00" }}>⚠ {t("estimate.has_warnings", { n: l.warnings.length })}</span> : null}</div></div>
                    <div className="col" style={{ alignItems: "flex-end" }}><b className="mono">{l.total === null ? t("common.on_request") : amd(l.total)}</b><span className="small muted">{l.qty} {t(`unit.${l.unit}`)}</span>
                      <div className="row gap-6">{obj && cur.status !== "approved" && <button className="btn sm" onClick={() => setAlt(obj.id)}>{t("common.replace_analog")}</button>}{l.url && <a className="btn sm ghost" href={l.url} target="_blank" rel="noreferrer">{t("common.open_at_supplier")} <ExternalLink size={12} /></a>}</div></div>
                  </div>
                );
              })}
            </div>
          )}
          {tab === "estimate" && <EstimateView est={est} onRecheck={cur.status === "approved" ? undefined : recheck} xlsxUrl={xlsx ? fileUrl(xlsx.url) : undefined} />}
          {tab === "suppliers" && (
            <div className="col gap-10">
              <table className="table"><thead><tr><th>{t("common.supplier")}</th><th className="right">{t("res.sup.col.items")}</th><th className="right">{t("common.sum")}</th><th>{t("res.sup.col.lead")}</th></tr></thead>
                <tbody>{suppliers.map(([k, s]) => <tr key={k}><td><b>{s.name}</b> {s.demo && <Badge tone="danger">DEMO</Badge>}</td><td className="right">{s.items}</td><td className="right mono">{amd(s.total)}</td><td>{s.lead ? t("common.days", { n: s.lead }) : "—"}</td></tr>)}</tbody></table>
              <Link className="btn" to={`/app/p/${pid}/procurement`}><Store size={16} /> {t("res.rfq_cta")}</Link>
            </div>
          )}
          {tab === "timeline" && <Timeline lead={cur.metrics.lead_days_max} />}
          {tab === "checks" && (
            <div className="col gap-6">
              {issues.filter((i) => i.severity !== "pass").map((i, k) => <div key={k} className={`alert ${i.severity === "block" ? "danger" : "warn"} small`}><AlertTriangle size={16} /> {ruleMessage(i)}</div>)}
              {issues.filter((i) => i.severity === "pass").map((i, k) => <div key={`p${k}`} className="alert sage small"><CheckCircle2 size={16} /> {ruleMessage(i)}</div>)}
              {(cur.metrics.unplaced || []).map((u, k) => <div key={`u${k}`} className="alert info small">{t("res.unplaced", { cat: catName(u.category) })}</div>)}
              {scene.assumptions.map((a) => <div key={a.key} className="alert info small">{t("res.assumption")}: {tOr(`geo.assume.${a.key}`, lang === "ru" ? a.text : a.key)}</div>)}
              <TrustPanel pid={pid!} />
              <PilotPanel pid={pid!} />
            </div>
          )}
        </div>

        <aside className="col gap-16">
          <div className="card pad">
            <div className="muted small">{t("estimate.title")}</div>
            <div style={{ fontSize: 28, fontWeight: 800 }} className="mono">{amd(est.totals.known)}</div>
            {est.totals.range_high > est.totals.known && <div className="small muted">{t("estimate.upto", { v: amd(est.totals.range_high) })}</div>}
            <div className="mt-16"><EstimateSummary est={est} /></div>
          </div>
          <div className="card pad">
            <div className="row between"><b>{t("res.key_products")}</b><button className="btn ghost sm" onClick={() => setTab("products")}>{t("res.see_all", { n: scene.objects.length })}</button></div>
            {keyProducts.map((l) => (
              <div key={l.id} className="product-row">
                <div className="thumb" style={{ background: l.color_hex || "#eee" }} />
                <div><b className="small">{lineName(l)}</b><div className="tiny muted">{l.supplier}</div><div className="row gap-4 mt-8"><Badge tone={l.stock === "in_stock" ? "sage" : ""}>{stock(l.stock)}</Badge><b className="small mono">{amd(l.unit_price)}</b></div></div>
                <button className="icon-btn" aria-label={t("res.to_cart")} onClick={() => setTab("suppliers")}><ShoppingCart size={16} color="var(--terra-ink)" /></button>
              </div>
            ))}
          </div>
          <div className="card pad">
            <div className="row between"><b>{t("res.tab.suppliers")}</b><span className="small muted">{suppliers.length}</span></div>
            <div className="grid g2 mt-8">{suppliers.slice(0, 4).map(([k, s]) => <div key={k} className="card flat pad small"><b>{s.name.replace(" (DEMO)", "")}</b><div className="tiny muted">{t("res.items_n", { n: s.items })}</div></div>)}</div>
            <div className="grid g2 mt-8">
              <div className="card flat pad row small"><Truck size={18} /><div><b>{t("res.delivery")}</b><div className="tiny muted">{t("res.delivery_sub", { n: cur.metrics.lead_days_max })}</div></div></div>
              <div className="card flat pad row small"><Wrench size={18} /><div><b>{t("res.install")}</b><div className="tiny muted">{t("res.install_sub")}</div></div></div>
            </div>
          </div>
          <div className="card pad col gap-6">
            <b>{t("res.docs")}</b>
            <Link className="btn" to={`/app/p/${pid}/documents`}><FileText size={16} /> {t("res.album")}</Link>
            <Link className="btn" to={`/app/p/${pid}/versions/${cur.id}`}>{t("res.history", { n: ver.number })}</Link>
            <button className="btn" onClick={() => { navigator.clipboard?.writeText(`${location.origin}/client/${project.share_token}`); toast(t("common.link_copied")); }}><Share2 size={16} /> {t("res.share")}</button>
          </div>
        </aside>
      </div>

      <CommandDrawer open={cmdOpen} onClose={() => setCmdOpen(false)} pid={pid!} vid={cur.id} onApplied={() => load(cur.id)} />
      <AlternativesDrawer pid={pid!} vid={cur.id} objectId={alt} onClose={() => setAlt(null)} onReplaced={() => load(cur.id)} />
      <ApproveModal open={approveOpen} onClose={() => setApproveOpen(false)} pid={pid!} variant={cur} blocks={blocks} onDone={() => load(cur.id)} />
    </div>
  );
}

function area(poly: [number, number][]) { let s = 0; for (let i = 0; i < poly.length; i++) { const [x1, y1] = poly[i], [x2, y2] = poly[(i + 1) % poly.length]; s += x1 * y2 - x2 * y1; } return Math.abs(s) / 2e6; }

function Check({ ok, title, sub }: { ok: boolean; title: string; sub: string }) {
  return <div className="check-item"><span className={ok ? "ok" : "wrn"}>{ok ? <CheckCircle2 size={14} /> : <AlertTriangle size={13} />}</span><div><b className="small">{title}</b><div className="tiny muted">{sub}</div></div></div>;
}

function VariantThumb({ pid, vid }: { pid: string; vid: string }) {
  const [v, setV] = useState<Variant | null>(null);
  useEffect(() => { api<Variant>(`/projects/${pid}/variants/${vid}`).then(setV); }, [pid, vid]);
  return v?.version ? <Scene3D scene={v.version.scene} height="100%" interactive={false} cutaway /> : <div className="skeleton" style={{ height: "100%" }} />;
}

function Visuals({ scene, pid, vid }: { scene: Scene; pid: string; vid: string }) {
  const { t } = useT();
  const rooms = scene.rooms.filter((r) => r.type !== "balcony");
  const [room, setRoom] = useState(rooms[0]?.id);
  const cams = scene.cameras.filter((c) => c.room_id === room);
  return (
    <div className="col gap-10">
      <div className="row wrap">{rooms.map((r) => <button key={r.id} className={`chip ${room === r.id ? "on" : ""}`} onClick={() => setRoom(r.id)}>{roomType(r.type)}</button>)}</div>
      {room && cams.length > 0 && <RenderGallery pid={pid} vid={vid} roomId={room} />}
      <div className="grid g3">{cams.map((c, i) => <div key={c.id} className="canvas-wrap" style={{ height: 300 }}><Scene3D scene={scene} mode="room" roomId={room} cameraIndex={i} height={300} quality="high" /></div>)}</div>
      <div className="alert info small">{t("res.visuals_note")}</div>
    </div>
  );
}

const STAGES: [string, number, number][] = [["demolition", 0, 5], ["rough", 4, 12], ["partitions", 8, 18], ["screed", 14, 21], ["tiling", 21, 30], ["ceilings", 26, 34], ["painting", 32, 44], ["floors", 42, 48], ["finish", 46, 52], ["custom", 50, 58], ["delivery", 52, 60]];
function Timeline({ lead }: { lead: number }) {
  const { t } = useT();
  return <div className="col gap-6">
    {STAGES.map(([n, s, e], i) => <div key={n} className="row small"><span style={{ width: 260 }}>{t(`res.stage.${n}`)}</span><div className="grow" style={{ position: "relative", height: 14, background: "var(--bg-2)", borderRadius: 6 }}><i style={{ position: "absolute", left: `${(s / 60) * 100}%`, width: `${((e - s) / 60) * 100}%`, top: 0, bottom: 0, background: i % 2 ? "var(--sage)" : "var(--terra)", borderRadius: 6 }} /></div><span className="muted mono" style={{ width: 80 }}>{t("res.days", { a: s, b: e })}</span></div>)}
    <div className="alert info small mt-8">{t("res.timeline_note", { n: lead })}</div>
  </div>;
}

function ApproveModal({ open, onClose, pid, variant, blocks, onDone }: { open: boolean; onClose: () => void; pid: string; variant: Variant; blocks: number; onDone: () => void }) {
  const { t } = useT();
  const [note, setNote] = useState("");
  const [res, setRes] = useState<{ warnings: string[]; estimate_snapshot_id: string } | null>(null);
  const toast = useToast();
  const go = async () => {
    try { setRes(await api(`/projects/${pid}/variants/${variant.id}/approve`, { method: "POST", json: { decision: "approved", note } })); onDone(); }
    catch (x) { toast((x as Error).message, true); }
  };
  return (
    <Modal open={open} onClose={onClose}>
      <div style={{ padding: 24 }} className="col gap-16">
        <h2>{t("apr.title", { name: variantTitle(variant) })}</h2>
        {res ? <>
          <div className="alert sage"><CheckCircle2 size={18} /> {t("apr.done")}</div>
          {res.warnings.length > 0 && <div className="alert warn small">{t("errors.order.made_to_measure_requires_production")}</div>}
          <div className="row"><Link className="btn primary" to={`/app/p/${pid}/procurement`}>{t("apr.to_rfq")}</Link><Link className="btn" to={`/app/p/${pid}/documents`}>{t("apr.to_album")}</Link></div>
        </> : <>
          <ul className="small" style={{ margin: 0, paddingLeft: 18 }}><li>{t("apr.l1")}</li><li>{t("apr.l2")}</li><li>{t("apr.l3")}</li></ul>
          {blocks > 0 && <div className="alert danger"><AlertTriangle size={18} /> {t("apr.blocks", { n: blocks })}</div>}
          <textarea className="input" rows={3} placeholder={t("apr.note_ph")} value={note} onChange={(e) => setNote(e.target.value)} />
          <div className="row" style={{ justifyContent: "flex-end" }}><button className="btn" onClick={onClose}>{t("common.cancel")}</button><button className="btn primary" disabled={blocks > 0} onClick={go}>{t("apr.approve")}</button></div>
        </>}
      </div>
    </Modal>
  );
}
