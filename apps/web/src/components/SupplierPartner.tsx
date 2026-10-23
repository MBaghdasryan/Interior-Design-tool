import { useEffect, useRef, useState } from "react";
import * as THREE from "three";
import { GLTFLoader } from "three/examples/jsm/loaders/GLTFLoader.js";
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js";
import { Box, CheckCircle2, Circle, FileBadge, Image as ImageIcon, Layers, Trash2, Upload, X } from "lucide-react";
import { api, fileUrl } from "../lib/api";
import { useScope, withQs } from "../lib/scope";
import { amd, catName, dt, kb } from "../lib/format";
import { useT } from "../i18n";
import { Badge, useToast } from "./ui";

interface Onb { supplier: { id: string; name: string; website: string; city: string; kind: string; tax_id: string; contacts: Record<string, string> } | null; verification: string; note: string;
  agreement_version: string; steps: Record<string, boolean>; products: number; assets: number }
const STEPS = ["profile", "agreement", "catalogue", "category_map", "assets", "submitted"];
const V_TONE: Record<string, string> = { verified: "sage", pending: "warn", rejected: "danger", not_started: "" };

/** Partner onboarding: profile → agreement → catalogue → category mapping → assets → submit for verification. */
export function OnboardingCard({ onChange }: { onChange?: () => void }) {
  const { t } = useT();
  const { qs } = useScope();
  const toast = useToast();
  const [st, setSt] = useState<Onb | null>(null);
  const [f, setF] = useState({ name: "", website: "", city: "", kind: "store", tax_id: "", phone: "", email: "" });
  const [agree, setAgree] = useState(false);
  const load = () => api<Onb>(withQs("/supplier/onboarding", qs)).then((s) => { setSt(s); if (s.supplier) setF((x) => ({ ...x, name: s.supplier!.name, website: s.supplier!.website, city: s.supplier!.city, kind: s.supplier!.kind, tax_id: s.supplier!.tax_id, phone: s.supplier!.contacts?.phone || "", email: s.supplier!.contacts?.email || "" })); }).catch(() => {});
  useEffect(() => { load(); }, [qs]);  // eslint-disable-line react-hooks/exhaustive-deps
  const run = async (fn: () => Promise<unknown>, ok: string) => { try { await fn(); toast(ok); load(); onChange?.(); } catch (x) { toast((x as Error).message, true); } };
  if (!st) return null;
  return (
    <section className="card pad col gap-10" aria-labelledby="onb-h">
      <div className="row between wrap"><h3 id="onb-h">{t("sob.title")}</h3><Badge tone={V_TONE[st.verification]}>{t(`sob.v.${st.verification}`)}</Badge></div>
      {st.verification === "pending" && <div className="alert warn small">{t("sob.pending_hint")}</div>}
      {st.verification === "rejected" && <div className="alert danger small">{t("sob.rejected_hint", { note: st.note || "—" })}</div>}
      <ol className="row gap-12 wrap small" style={{ listStyle: "none", padding: 0, margin: 0 }}>
        {STEPS.map((s) => <li key={s} className="row gap-4">{st.steps[s] ? <CheckCircle2 size={16} color="var(--sage-ink)" /> : <Circle size={16} />}{t(`sob.step.${s}`)}</li>)}
      </ol>
      {qs ? <div className="alert info small">{t("mg.onb_platform_hint")}</div> : <>
      <div className="grid g3">
        {(["name", "website", "city", "tax_id", "phone", "email"] as const).map((k) => (
          <label key={k} className="col gap-4"><span className="tiny muted">{t(`sob.f.${k}`)}</span><input className="input" value={f[k]} onChange={(e) => setF({ ...f, [k]: e.target.value })} /></label>))}
        <label className="col gap-4"><span className="tiny muted">{t("sob.f.kind")}</span>
          <select className="select input" value={f.kind} onChange={(e) => setF({ ...f, kind: e.target.value })}>{["store", "manufacturer", "installer"].map((k) => <option key={k} value={k}>{t(`sob.kind.${k}`)}</option>)}</select></label>
      </div>
      <div><button className="btn" disabled={f.name.length < 2} onClick={() => run(() => api(withQs("/supplier/onboarding/profile", qs), { method: "PUT", json: f }), t("sob.saved"))}>{t("sob.save_profile")}</button></div>
      {st.supplier && !st.steps.agreement && <div className="row gap-8 wrap small">
        <label className="row gap-6"><input type="checkbox" checked={agree} onChange={(e) => setAgree(e.target.checked)} /> {t("sob.agree", { v: st.agreement_version })}</label>
        <button className="btn sm" disabled={!agree} onClick={() => run(() => api(withQs("/supplier/onboarding/agreement", qs), { method: "POST", json: { version: st.agreement_version, accept: true } }), t("sob.saved"))}>{t("sob.accept")}</button></div>}
      </>}
      {st.supplier && <CategoryMap />}
      {st.supplier && !qs && st.verification !== "verified" && <div><button className="btn primary" disabled={st.steps.submitted && st.verification === "pending"} onClick={() => run(() => api(withQs("/supplier/onboarding/submit", qs), { method: "POST" }), t("sob.submitted"))}>{t("sob.submit")}</button></div>}
    </section>
  );
}

function CategoryMap() {
  const { t } = useT();
  const { qs } = useScope();
  const toast = useToast();
  const [rows, setRows] = useState<[string, string][]>([]);
  const [tax, setTax] = useState<string[]>([]);
  useEffect(() => { api<{ mapping: Record<string, string>; taxonomy: string[] }>(withQs("/supplier/category-map", qs)).then((r) => { setRows(Object.entries(r.mapping)); setTax(r.taxonomy); }).catch(() => {}); }, [qs]);
  const save = async () => { try { await api(withQs("/supplier/category-map", qs), { method: "PUT", json: { mapping: Object.fromEntries(rows.filter(([k, v]) => k && v)) } }); toast(t("sob.saved")); } catch (x) { toast((x as Error).message, true); } };
  return (
    <div className="col gap-6">
      <b className="small">{t("sob.catmap")}</b><span className="tiny muted">{t("sob.catmap_hint")}</span>
      {rows.map(([k, v], i) => <div key={i} className="row gap-6">
        <input className="input grow" aria-label={t("sob.catmap_label")} placeholder={t("sob.catmap_label")} value={k} onChange={(e) => setRows(rows.map((r, j) => (j === i ? [e.target.value, r[1]] : r)))} />
        <select className="select input" aria-label={t("common.category")} value={v} onChange={(e) => setRows(rows.map((r, j) => (j === i ? [r[0], e.target.value] : r)))}><option value="">—</option>{tax.map((c) => <option key={c} value={c}>{catName(c)}</option>)}</select>
        <button className="icon-btn" aria-label={t("common.delete")} onClick={() => setRows(rows.filter((_, j) => j !== i))}><Trash2 size={15} /></button></div>)}
      <div className="row gap-6"><button className="btn sm ghost" onClick={() => setRows([...rows, ["", ""]])}>{t("sob.catmap_add")}</button><button className="btn sm" onClick={save}>{t("common.save")}</button></div>
    </div>
  );
}

interface Asset { id: string; kind: string; filename: string; size: number; variant_id: string | null; meta: Record<string, string | number>; scan_status: string; created_at: string; url: string }
const KINDS = [["model3d", Box, ".glb,.gltf"], ["texture", ImageIcon, ".png,.jpg,.jpeg,.webp"], ["bim_cad", Layers, ".ifc,.dwg,.dxf,.rvt"], ["certificate", FileBadge, ".pdf"]] as const;

/** Supplier asset library: files are validated by content on the server; GLB models open in a 3D preview. */
export function AssetsCard({ products }: { products: { id: string; sku: string; name: string }[] }) {
  const { t } = useT();
  const { qs } = useScope();
  const toast = useToast();
  const [rows, setRows] = useState<Asset[]>([]);
  const [kind, setKind] = useState<string>("model3d");
  const [variant, setVariant] = useState("");
  const [busy, setBusy] = useState(false);
  const [preview, setPreview] = useState<Asset | null>(null);
  const input = useRef<HTMLInputElement>(null);
  const load = () => api<Asset[]>(withQs("/supplier/assets", qs)).then(setRows).catch(() => {});
  useEffect(() => { load(); }, [qs]);  // eslint-disable-line react-hooks/exhaustive-deps
  const upload = async (file: File) => {
    const fd = new FormData();
    fd.append("file", file);
    fd.append("kind", kind);
    if (variant) fd.append("variant_id", variant);
    setBusy(true);
    try { await api(withQs("/supplier/assets", qs), { method: "POST", body: fd }); toast(t("sas.uploaded")); load(); } catch (x) { toast((x as Error).message, true); } finally { setBusy(false); if (input.current) input.current.value = ""; }
  };
  const accept = KINDS.find((k) => k[0] === kind)?.[2] || "";
  return (
    <section className="card pad col gap-10" aria-labelledby="sas-h">
      <h3 id="sas-h">{t("sas.title")}</h3>
      <p className="tiny muted">{t("sas.lead")}</p>
      <div className="row gap-6 wrap">
        <select className="select input" aria-label={t("sas.kind")} value={kind} onChange={(e) => setKind(e.target.value)}>{KINDS.map(([k]) => <option key={k} value={k}>{t(`sas.k.${k}`)}</option>)}</select>
        <select className="select input" aria-label={t("sas.sku")} value={variant} onChange={(e) => setVariant(e.target.value)}><option value="">{t("sas.no_sku")}</option>{products.map((p) => <option key={p.id} value={p.id}>{p.sku} · {p.name}</option>)}</select>
        <input ref={input} type="file" hidden accept={accept} aria-label={t("sas.upload")} onChange={(e) => e.target.files?.[0] && upload(e.target.files[0])} />
        <button className="btn" disabled={busy} onClick={() => input.current?.click()}><Upload size={15} /> {t("sas.upload")}</button>
      </div>
      {!rows.length && <div className="small muted">{t("sas.empty")}</div>}
      {rows.map((a) => {
        const I = KINDS.find((k) => k[0] === a.kind)?.[1] || Box;
        return (
          <div key={a.id} className="row gap-8 small" style={{ borderTop: "1px solid var(--line)", paddingTop: 8 }}>
            <I size={18} />
            <div className="grow"><b>{a.filename}</b> <span className="tiny muted">{kb(a.size)} · {dt(a.created_at)}</span>
              <div className="tiny muted">{t(`sas.k.${a.kind}`)}{a.meta.pbr_channel ? ` · ${t(`sas.pbr.${a.meta.pbr_channel}`)}` : ""}{a.meta.meshes ? ` · ${t("sas.meshes", { n: a.meta.meshes })}` : ""}{a.meta.width ? ` · ${a.meta.width}×${a.meta.height}` : ""}{a.meta.schema ? ` · ${a.meta.schema}` : ""}{a.variant_id ? ` · ${products.find((p) => p.id === a.variant_id)?.sku || ""}` : ""}</div></div>
            {a.kind === "model3d" && a.meta.ext === ".glb" && <button className="btn sm" onClick={() => setPreview(a)}>{t("sas.preview")}</button>}
            {a.kind === "texture" && <img src={fileUrl(a.url)} alt={a.filename} width={40} height={40} style={{ objectFit: "cover", borderRadius: 6 }} />}
            <a className="btn sm ghost" href={fileUrl(a.url)}>{t("sas.open")}</a>
            <button className="icon-btn" aria-label={t("common.delete")} onClick={async () => { await api(withQs(`/supplier/assets/${a.id}`, qs), { method: "DELETE" }).catch(() => {}); load(); }}><Trash2 size={15} /></button>
          </div>
        );
      })}
      {preview && <div className="modal" role="dialog" aria-modal="true" aria-label={preview.filename} onClick={() => setPreview(null)}>
        <div className="card pad col gap-8" style={{ width: "min(720px, 94vw)" }} onClick={(e) => e.stopPropagation()}>
          <div className="row between"><b>{preview.filename}</b><button className="icon-btn" aria-label={t("common.close")} onClick={() => setPreview(null)}><X size={16} /></button></div>
          <ModelPreview url={fileUrl(preview.url)} />
        </div></div>}
    </section>
  );
}

/** Minimal GLB viewer: fits the model, orbit controls, renders on demand. */
export function ModelPreview({ url, height = 420 }: { url: string; height?: number }) {
  const host = useRef<HTMLDivElement>(null);
  const { t } = useT();
  const [err, setErr] = useState(false);
  useEffect(() => {
    const el = host.current;
    if (!el) return;
    const renderer = new THREE.WebGLRenderer({ antialias: true });
    renderer.setPixelRatio(Math.min(2, window.devicePixelRatio));
    renderer.setSize(el.clientWidth, height);
    renderer.outputColorSpace = THREE.SRGBColorSpace;
    el.appendChild(renderer.domElement);
    const scene = new THREE.Scene();
    scene.background = new THREE.Color("#efe9e1");
    scene.add(new THREE.HemisphereLight(0xffffff, 0x8a8178, 1.2));
    const sun = new THREE.DirectionalLight(0xffffff, 1.4);
    sun.position.set(3, 5, 4);
    scene.add(sun);
    const camera = new THREE.PerspectiveCamera(40, el.clientWidth / height, 0.01, 1000);
    const controls = new OrbitControls(camera, renderer.domElement);
    const draw = () => renderer.render(scene, camera);
    controls.addEventListener("change", draw);
    new GLTFLoader().load(url, (g) => {
      scene.add(g.scene);
      const box = new THREE.Box3().setFromObject(g.scene);
      const size = box.getSize(new THREE.Vector3()).length() || 1;
      const c = box.getCenter(new THREE.Vector3());
      camera.position.copy(c).add(new THREE.Vector3(size * 0.8, size * 0.6, size * 0.8));
      controls.target.copy(c);
      controls.update();
      draw();
    }, undefined, () => setErr(true));
    draw();
    return () => { controls.dispose(); renderer.dispose(); el.innerHTML = ""; };
  }, [url, height]);
  return err ? <div className="empty">{t("sas.preview_failed")}</div> : <div ref={host} style={{ width: "100%", height }} />;
}

interface PData { locations: { id: string; kind: string; name: string; city: string; address: string }[]; "delivery-options": { id: string; name: string; regions: string[]; fee_amd: number; days_min: number; days_max: number }[];
  services: { id: string; name: string; category: string; price_amd: number | null; unit: string }[] }

/** Warehouses / showrooms, delivery options and installation services. */
export function PartnerDataCard() {
  const { t } = useT();
  const { qs } = useScope();
  const toast = useToast();
  const [d, setD] = useState<PData | null>(null);
  const [loc, setLoc] = useState({ name: "", address: "", kind: "warehouse" });  // city defaults server-side
  const [del, setDel] = useState({ name: "", regions: "", fee_amd: "", days_min: "1", days_max: "3" });
  const [svc, setSvc] = useState({ name: "", price_amd: "" });
  const load = () => api<PData>(withQs("/supplier/partner-data", qs)).then(setD).catch(() => {});
  useEffect(() => { load(); }, [qs]);  // eslint-disable-line react-hooks/exhaustive-deps
  const run = async (fn: () => Promise<unknown>) => { try { await fn(); toast(t("sob.saved")); load(); } catch (x) { toast((x as Error).message, true); } };
  if (!d) return null;
  const rm = (kind: string, id: string) => run(() => api(withQs(`/supplier/${kind}/${id}`, qs), { method: "DELETE" }));
  return (
    <section className="card pad col gap-10" aria-labelledby="spd-h">
      <h3 id="spd-h">{t("spd.title")}</h3>
      <div className="grid g3" style={{ alignItems: "start" }}>
        <div className="col gap-6"><b className="small">{t("spd.locations")}</b>
          {d.locations.map((x) => <div key={x.id} className="row between small"><span>{t(`spd.lk.${x.kind}`)}: {x.name} · {x.city} {x.address}</span><button className="icon-btn" aria-label={t("common.delete")} onClick={() => rm("locations", x.id)}><Trash2 size={14} /></button></div>)}
          <input className="input" aria-label={t("spd.name")} placeholder={t("spd.name")} value={loc.name} onChange={(e) => setLoc({ ...loc, name: e.target.value })} />
          <input className="input" aria-label={t("spd.address")} placeholder={t("spd.address")} value={loc.address} onChange={(e) => setLoc({ ...loc, address: e.target.value })} />
          <select className="select input" aria-label={t("spd.kind")} value={loc.kind} onChange={(e) => setLoc({ ...loc, kind: e.target.value })}>{["warehouse", "showroom", "pickup"].map((k) => <option key={k} value={k}>{t(`spd.lk.${k}`)}</option>)}</select>
          <button className="btn sm" disabled={!loc.name} onClick={() => run(() => api(withQs("/supplier/locations", qs), { method: "POST", json: loc }))}>{t("spd.add")}</button></div>
        <div className="col gap-6"><b className="small">{t("spd.delivery")}</b>
          {d["delivery-options"].map((x) => <div key={x.id} className="row between small"><span>{x.name}: {amd(x.fee_amd)}, {x.days_min}–{x.days_max} {t("spd.days")}</span><button className="icon-btn" aria-label={t("common.delete")} onClick={() => rm("delivery-options", x.id)}><Trash2 size={14} /></button></div>)}
          <input className="input" aria-label={t("spd.name")} placeholder={t("spd.name")} value={del.name} onChange={(e) => setDel({ ...del, name: e.target.value })} />
          <input className="input" aria-label={t("spd.regions")} placeholder={t("spd.regions")} value={del.regions} onChange={(e) => setDel({ ...del, regions: e.target.value })} />
          <div className="row gap-4"><input className="input" inputMode="numeric" aria-label={t("spd.fee")} placeholder={t("spd.fee")} value={del.fee_amd} onChange={(e) => setDel({ ...del, fee_amd: e.target.value })} />
            <input className="input" style={{ width: 60 }} inputMode="numeric" aria-label={t("spd.days_min")} value={del.days_min} onChange={(e) => setDel({ ...del, days_min: e.target.value })} />
            <input className="input" style={{ width: 60 }} inputMode="numeric" aria-label={t("spd.days_max")} value={del.days_max} onChange={(e) => setDel({ ...del, days_max: e.target.value })} /></div>
          <button className="btn sm" disabled={!del.name} onClick={() => run(() => api(withQs("/supplier/delivery-options", qs), { method: "POST", json: { name: del.name, regions: del.regions.split(",").map((s) => s.trim()).filter(Boolean), fee_amd: Number(del.fee_amd) || 0, days_min: Number(del.days_min) || 0, days_max: Number(del.days_max) || 0 } }))}>{t("spd.add")}</button></div>
        <div className="col gap-6"><b className="small">{t("spd.services")}</b>
          {d.services.map((x) => <div key={x.id} className="row between small"><span>{x.name}: {x.price_amd == null ? t("spd.on_request") : amd(x.price_amd)}</span><button className="icon-btn" aria-label={t("common.delete")} onClick={() => rm("services", x.id)}><Trash2 size={14} /></button></div>)}
          <input className="input" aria-label={t("spd.name")} placeholder={t("spd.name")} value={svc.name} onChange={(e) => setSvc({ ...svc, name: e.target.value })} />
          <input className="input" inputMode="numeric" aria-label={t("spd.price")} placeholder={t("spd.price")} value={svc.price_amd} onChange={(e) => setSvc({ ...svc, price_amd: e.target.value })} />
          <button className="btn sm" disabled={!svc.name} onClick={() => run(() => api(withQs("/supplier/services", qs), { method: "POST", json: { name: svc.name, price_amd: svc.price_amd ? Number(svc.price_amd) : null } }))}>{t("spd.add")}</button></div>
      </div>
    </section>
  );
}

interface Rates { rates: { body?: Record<string, number>; front?: Record<string, number>; back?: number | null; edge_per_m?: number | null; hardware?: Record<string, number>; assembly_pct?: number; lead_time_days?: number | null };
  body: string[]; fronts: string[]; hardware: string[]; kind: string }

/** Manufacturer rates for the custom furniture configurator; without them configurations stay «on request». */
export function CustomRatesCard() {
  const { t } = useT();
  const { qs } = useScope();
  const toast = useToast();
  const [d, setD] = useState<Rates | null>(null);
  useEffect(() => { api<Rates>(withQs("/supplier/custom-rates", qs)).then(setD).catch(() => {}); }, [qs]);
  if (!d || d.kind !== "manufacturer") return null;
  const r = d.rates;
  const setMap = (k: "body" | "front" | "hardware", key: string, v: string) => setD({ ...d, rates: { ...r, [k]: { ...(r[k] || {}), [key]: Number(v) || 0 } } });
  const num = (label: string, value: number | null | undefined, on: (v: string) => void) => (
    <label key={label} className="col gap-4"><span className="tiny muted">{label}</span><input className="input" style={{ width: 120 }} inputMode="numeric" value={value ?? ""} onChange={(e) => on(e.target.value)} /></label>);
  const save = async () => { try { setD(await api<Rates>(withQs("/supplier/custom-rates", qs), { method: "PUT", json: r })); toast(t("sob.saved")); } catch (x) { toast((x as Error).message, true); } };
  return (
    <section className="card pad col gap-10" aria-labelledby="crt-h">
      <div className="row between"><h3 id="crt-h">{t("crt.title")}</h3><button className="btn sm primary" onClick={save}>{t("common.save")}</button></div>
      <p className="tiny muted">{t("crt.lead")}</p>
      <b className="small">{t("crt.body")}</b><div className="row gap-8 wrap">{d.body.map((k) => num(t(`cst.mat.${k}`), r.body?.[k], (v) => setMap("body", k, v)))}</div>
      <b className="small">{t("crt.front")}</b><div className="row gap-8 wrap">{d.fronts.map((k) => num(t(`cst.mat.${k}`), r.front?.[k], (v) => setMap("front", k, v)))}</div>
      <b className="small">{t("crt.hardware")}</b><div className="row gap-8 wrap">{d.hardware.map((k) => num(t(`cst.hw.${k}`), r.hardware?.[k], (v) => setMap("hardware", k, v)))}</div>
      <div className="row gap-8 wrap">
        {num(t("crt.back"), r.back, (v) => setD({ ...d, rates: { ...r, back: v === "" ? null : Number(v) } }))}
        {num(t("crt.edge"), r.edge_per_m, (v) => setD({ ...d, rates: { ...r, edge_per_m: v === "" ? null : Number(v) } }))}
        {num(t("crt.assembly"), r.assembly_pct, (v) => setD({ ...d, rates: { ...r, assembly_pct: Number(v) || 0 } }))}
        {num(t("crt.lead"), r.lead_time_days, (v) => setD({ ...d, rates: { ...r, lead_time_days: v === "" ? null : Number(v) } }))}
      </div>
    </section>
  );
}
