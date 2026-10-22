import { useCallback, useEffect, useRef, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import type { LucideIcon } from "lucide-react";
import { ArrowRight, Armchair, CloudUpload, Database, FileText, Globe2, Info, Palette, Plus, ScanLine, ShoppingCart, Sparkles, Users, Wallet, X } from "lucide-react";
import { api, fileUrl, uploadAsset, type Project, type Schemas } from "../lib/api";
import { kb, styleName, tierName } from "../lib/format";
import { LANGS, useT } from "../i18n";
import { Badge, Loading, Switch, useToast } from "../components/ui";
import PilotPanel from "../components/PilotPanel";

const STYLE_PALETTES: Record<string, string[]> = {
  contemporary: ["#f2f0ed", "#cfc8bf", "#8c8279", "#c97f63"], warm_minimal: ["#efe6da", "#d9c9b7", "#b98f6a", "#8a5a3c"], soft_scandi: ["#f4f1ec", "#e3d8c8", "#c8b08f", "#8f9f7e"],
  classic: ["#f3eee6", "#ddd2c2", "#b8a17f", "#7c6a55"], modern_loft: ["#3a3532", "#6b4a3a", "#a4593c", "#c9b8a3"],
};
const COLORS = ["#e8dccb", "#f1efea", "#c9c6c1", "#8f9f7e", "#c97f63", "#2e2e2e"];
const TIERS = ["economy", "comfort", "business", "premium"];
const FAMILY = ["single", "couple", "kids", "other"];
const SUPP = ["any", "local", "popular", "premium"];

interface Source { key: string; name: string; domain: string; categories: string[]; method: string; status: string; note: string }

function CreateForm() {
  const { t } = useT();
  const nav = useNavigate();
  const toast = useToast();
  const [f, setF] = useState({ title: "", address: "", city: "Yerevan", area_m2: "", renovation_stage: "shell", client_name: "", doc_lang: "hy" });
  const create = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      const body: Schemas["ProjectIn"] = { ...f, area_m2: f.area_m2 ? Number(f.area_m2) : null };
      const p = await api<Project>("/projects", { method: "POST", json: body });
      nav(`/app/p/${p.id}/upload`);
    } catch (x) { toast((x as Error).message, true); }
  };
  return (
    <form className="card pad col gap-16" style={{ maxWidth: 720 }} onSubmit={create}>
      <h1>{t("np.title")}</h1>
      <p className="muted">{t("np.lead")}</p>
      <div className="grid g2">
        <div className="field"><label>{t("np.f.title")}</label><input aria-label={t("np.f.title")} className="input" required minLength={2} value={f.title} onChange={(e) => setF({ ...f, title: e.target.value })} placeholder={t("np.f.title_ph")} /></div>
        <div className="field"><label>{t("np.f.address")}</label><input aria-label={t("np.f.address")} className="input" value={f.address} onChange={(e) => setF({ ...f, address: e.target.value })} placeholder={t("np.f.address_ph")} /></div>
        <div className="field"><label>{t("np.f.area")}</label><input aria-label={t("np.f.area")} className="input" inputMode="decimal" value={f.area_m2} onChange={(e) => setF({ ...f, area_m2: e.target.value })} /></div>
        <div className="field"><label>{t("np.f.stage")}</label><select aria-label={t("np.f.stage")} className="select input" value={f.renovation_stage} onChange={(e) => setF({ ...f, renovation_stage: e.target.value })}>{["shell", "white_box", "lived_in"].map((k) => <option key={k} value={k}>{t(`np.stage.${k}`)}</option>)}</select></div>
        <div className="field"><label>{t("np.f.client")}</label><input aria-label={t("np.f.client")} className="input" value={f.client_name} onChange={(e) => setF({ ...f, client_name: e.target.value })} /></div>
        <div className="field"><label>{t("np.f.doc_lang")}</label><select aria-label={t("np.f.doc_lang")} className="select input" value={f.doc_lang} onChange={(e) => setF({ ...f, doc_lang: e.target.value })}>{LANGS.map((l) => <option key={l.code} value={l.code}>{l.name}</option>)}</select></div>
      </div>
      <div className="row"><button className="btn primary lg">{t("np.create")} <ArrowRight size={18} /></button></div>
    </form>
  );
}

export default function NewProject() {
  const { pid } = useParams();
  if (!pid) return <CreateForm />;
  return <Intake pid={pid} />;
}

function Intake({ pid }: { pid: string }) {
  const { t } = useT();
  const nav = useNavigate();
  const toast = useToast();
  const [p, setP] = useState<Project | null>(null);
  const [drag, setDrag] = useState(false);
  const [busy, setBusy] = useState(false);
  const [sources, setSources] = useState<Source[]>([]);
  const fileRef = useRef<HTMLInputElement>(null);
  const [prefs, setPrefs] = useState<Record<string, any>>({ styles: [] as string[], colors: [] as string[], budget_tier: "comfort", family: "", suppliers: "any", keep_items: "", interview: "", budget_amd: "" });
  const [source, setSource] = useState<"external" | "own" | "concept">("external");
  const [ext, setExt] = useState({ all: true, sources: [] as string[], only_priced: true, only_available: false, allow_quote: true, max_price_amd: "", city: "Yerevan" });

  const load = useCallback(() => api<Project>(`/projects/${pid}`).then((x) => {
    setP(x);
    setPrefs((cur) => ({ ...cur, ...x.preferences, styles: x.preferences?.styles || cur.styles, colors: x.preferences?.colors || cur.colors }));
  }), [pid]);
  useEffect(() => { load(); api<Source[]>("/catalog/sources").then(setSources).catch(() => {}); }, [load]);

  const upload = async (files: FileList | File[]) => {
    setBusy(true);
    for (const f of Array.from(files)) {
      try { await uploadAsset(pid, f); } catch (x) { toast(`${f.name}: ${(x as Error).message}`, true); }
    }
    setBusy(false);
    load();
  };
  const remove = async (id: string) => { await api(`/projects/${pid}/assets/${id}`, { method: "DELETE" }); load(); };
  const recognize = async () => {
    setBusy(true);
    try { await api(`/projects/${pid}/recognize`, { method: "POST" }); toast(t("up.recognize_started")); setTimeout(() => nav(`/app/p/${pid}/geometry`), 600); } catch (x) { toast((x as Error).message, true); }
    setBusy(false);
  };
  const demoGeometry = async () => { await api(`/projects/${pid}/use-demo-geometry`, { method: "POST" }); nav(`/app/p/${pid}/geometry`); };
  const generate = async (letAi = false) => {
    if (!p?.base_scene?.confirmed) { nav(`/app/p/${pid}/geometry`); return; }
    const pr = letAi ? { budget_tier: "comfort" } : { ...prefs, budget_amd: prefs.budget_amd ? Number(prefs.budget_amd) : null, keep_items: prefs.keep_items ? String(prefs.keep_items).split(",").map((s: string) => s.trim()) : [] };
    try {
      const job = await api<{ id: string }>(`/projects/${pid}/generate`, { method: "POST", json: { preferences: pr, product_source: source, idempotency_key: `${pid}-${Date.now()}`,
        external_settings: { sources: ext.all ? [] : ext.sources, only_priced: ext.only_priced, only_available: ext.only_available, allow_quote: ext.allow_quote, max_price_amd: ext.max_price_amd ? Number(ext.max_price_amd) : null, city: ext.city } } });
      nav(`/app/p/${pid}/generate/${job.id}`);
    } catch (x) { toast((x as Error).message, true); }
  };
  if (!p) return <Loading />;
  const toggle = (k: "styles" | "colors", v: string) => setPrefs({ ...prefs, [k]: prefs[k].includes(v) ? prefs[k].filter((x: string) => x !== v) : [...prefs[k], v] });
  const confirmed = !!p.base_scene?.confirmed;

  return (
    <div className="grid" style={{ gridTemplateColumns: "minmax(0, 1.25fr) minmax(360px, 0.9fr)", alignItems: "start" }}>
      <div className="col gap-16">
        <div className="stepper">
          <div className="s on"><span className="n">1</span> {t("up.step1")}</div><div className="bar" />
          <div className={`s ${confirmed ? "done" : ""}`}><span className="n">2</span> {t("up.step2")}</div><div className="bar" />
          <div className="s"><span className="n">3</span> {t("up.step3")}</div>
        </div>
        <div><h1>{p.title}</h1><div className="row between wrap mt-8"><h2 style={{ fontWeight: 700 }}>{t("up.h2")} <span className="muted" style={{ fontWeight: 500, fontSize: 16 }}>{t("up.h2_sub")}</span></h2>
          <span className="muted small" style={{ maxWidth: 280 }}>{t("up.hint")}</span></div></div>
        <div className={`dropzone ${drag ? "drag" : ""}`} onDragOver={(e) => { e.preventDefault(); setDrag(true); }} onDragLeave={() => setDrag(false)}
          onDrop={(e) => { e.preventDefault(); setDrag(false); upload(e.dataTransfer.files); }} onClick={() => fileRef.current?.click()} role="button" tabIndex={0}>
          <CloudUpload size={40} color="var(--ink-2)" />
          <h3 className="mt-8">{t("up.drop")}</h3>
          <p className="muted">{t("up.or_click")}</p>
          <p className="muted small mt-16">{t("up.formats")}</p>
          {busy && <div className="mt-8"><span className="spinner" /></div>}
          <input ref={fileRef} type="file" multiple hidden accept=".jpg,.jpeg,.png,.webp,.heic,.mp4,.mov,.pdf,.dwg,.dxf,.ifc,.rvt" onChange={(e) => e.target.files && upload(e.target.files)} />
        </div>
        <div className="row between wrap"><h3>{t("up.files")} <span className="muted">{p.assets?.length || 0}</span></h3>
          <div className="row"><button className="btn sm" onClick={demoGeometry} title={t("up.demo_geo_hint")}>{t("up.demo_geo")}</button>
            <button className="btn sm primary" disabled={!p.assets?.length || busy} onClick={recognize}><ScanLine size={15} /> {t("up.recognize")}</button></div></div>
        <div className="grid g4">
          {p.assets?.map((a) => (
            <div key={a.id} className="col gap-4">
              <div className="file-tile">
                {["photo", "plan_image"].includes(a.kind) ? <img src={fileUrl(a.url)} alt={a.filename} /> : <div className="col" style={{ alignItems: "center" }}><FileText size={30} /><Badge>{a.kind.toUpperCase()}</Badge></div>}
                <button className="x" onClick={() => remove(a.id)} aria-label={t("common.delete")}><X size={14} /></button>
              </div>
              <div className="small nowrap" style={{ overflow: "hidden", textOverflow: "ellipsis" }}>{a.filename}</div>
              <div className="tiny muted">{kb(a.size)}{a.aps?.status ? ` · APS: ${a.aps.status}` : ""}</div>
              {a.quality?.warnings?.length ? <div className="tiny" style={{ color: "#8a5d00" }}>⚠ {t("estimate.has_warnings", { n: a.quality.warnings.length })}</div> : null}
              {a.scan_status && <div className="tiny muted">{a.scan_status === "clean" ? "🛡 " : ""}{t(`scan.${a.scan_status}`)}</div>}
            </div>
          ))}
        </div>
        {p.base_scene && (
          <div className={`alert ${confirmed ? "sage" : "warn"}`}><Info size={18} /><div className="grow">{t("up.geo_state", { v: p.base_scene.version, state: confirmed ? t("up.geo_confirmed") : t("up.geo_needs") })}</div>
            <Link className="btn sm" to={`/app/p/${pid}/geometry`}>{confirmed ? t("common.open") : t("up.check")}</Link></div>
        )}
      </div>

      <aside className="col gap-10">
        <PilotPanel pid={pid} />
        <div className="card pad row" style={{ background: "var(--sage-soft)", borderColor: "#cfd8c3" }}>
          <Sparkles size={22} color="var(--sage-ink)" />
          <div className="grow"><b>{t("up.opt_title")}</b><div className="small muted">{t("up.opt_text")}</div></div>
          <button className="btn" onClick={() => generate(true)}>{t("up.let_ai")}</button>
        </div>
        <Block icon={Armchair} title={t("up.style")} sub={t("up.style_sub")}>
          <div className="grid" style={{ gridTemplateColumns: "repeat(5, 1fr)", gap: 8 }}>
            {Object.keys(STYLE_PALETTES).map((s) => (
              <button key={s} className={`style-tile ${prefs.styles.includes(s) ? "on" : ""}`} onClick={() => toggle("styles", s)}>
                <div className="img" style={{ display: "grid", gridTemplateColumns: "2fr 1fr", gridTemplateRows: "1fr 1fr" }}>
                  <div style={{ gridRow: "1 / 3", background: STYLE_PALETTES[s][0] }} /><div style={{ background: STYLE_PALETTES[s][2] }} /><div style={{ background: STYLE_PALETTES[s][3] }} />
                </div>
                <div className="tiny" style={{ padding: "4px 2px" }}>{styleName(s)}</div>
              </button>
            ))}
          </div>
        </Block>
        <Block icon={Palette} title={t("up.colors")} sub={t("up.colors_sub")}>
          <div className="row">{COLORS.map((c) => <button key={c} className={`swatch ${prefs.colors.includes(c) ? "on" : ""}`} style={{ background: c }} onClick={() => toggle("colors", c)} aria-label={c} />)}</div>
        </Block>
        <Block icon={Wallet} title={t("up.budget")} sub={t("up.budget_sub")}>
          <div className="row wrap">{TIERS.map((k) => <button key={k} className={`chip ${prefs.budget_tier === k ? "on" : ""}`} onClick={() => setPrefs({ ...prefs, budget_tier: k })}>{tierName(k)}</button>)}</div>
          <input className="input mt-8" placeholder={t("up.budget_exact")} inputMode="numeric" value={prefs.budget_amd || ""} onChange={(e) => setPrefs({ ...prefs, budget_amd: e.target.value.replace(/\D/g, "") })} />
        </Block>
        <Block icon={Users} title={t("up.family")} sub={t("up.family_sub")}>
          <div className="row wrap">{FAMILY.map((k) => <button key={k} className={`chip ${prefs.family === k ? "on" : ""}`} onClick={() => setPrefs({ ...prefs, family: k })}>{t(`up.family.${k}`)}</button>)}</div>
          <textarea className="input mt-8" rows={2} placeholder={t("up.interview_ph")} value={prefs.interview || ""} onChange={(e) => setPrefs({ ...prefs, interview: e.target.value })} />
        </Block>
        <Block icon={ShoppingCart} title={t("up.suppliers")} sub={t("up.suppliers_sub")}>
          <div className="row wrap">{SUPP.map((k) => <button key={k} className={`chip ${prefs.suppliers === k ? "on" : ""}`} onClick={() => setPrefs({ ...prefs, suppliers: k })}>{t(`up.sup.${k}`)}</button>)}</div>
        </Block>
        <Block icon={Plus} title={t("up.keep")} sub={t("up.keep_sub")}>
          <input className="input" placeholder={t("up.keep_ph")} value={prefs.keep_items || ""} onChange={(e) => setPrefs({ ...prefs, keep_items: e.target.value })} />
        </Block>

        <div className="card pad col gap-10">
          <div className="row"><Database size={20} /><h3 className="grow">{t("up.source")}</h3></div>
          <label className="row top" style={{ cursor: "pointer" }}>
            <input type="radio" checked={source === "external"} onChange={() => setSource("external")} style={{ marginTop: 3 }} />
            <div className="grow"><div className="row"><b>{t("up.src.external")}</b><Badge tone="terra">{t("up.recommended")}</Badge></div><div className="small muted">{t("up.src.external_sub")}</div></div>
            <Switch on={source === "external"} onChange={(v) => setSource(v ? "external" : "concept")} label={t("up.src.external")} />
          </label>
          {source === "external" && (
            <div className="col gap-6" style={{ paddingLeft: 26 }}>
              <label className="check"><input type="checkbox" checked={ext.all} onChange={(e) => setExt({ ...ext, all: e.target.checked })} /> {t("up.all_stores")}</label>
              {!ext.all && <div className="row wrap">{sources.map((s) => (
                <button key={s.key} className={`chip ${ext.sources.includes(s.key) ? "on" : ""}`} onClick={() => setExt({ ...ext, sources: ext.sources.includes(s.key) ? ext.sources.filter((x) => x !== s.key) : [...ext.sources, s.key] })}>
                  <Globe2 size={13} /> {s.name}{s.status !== "ok" && <span className="tiny muted">· {s.status === "rfq_only" ? "RFQ" : s.status === "needs_feed" ? t("up.stage_feed") : t("up.stage_audit")}</span>}
                </button>))}</div>}
              <label className="check"><input type="checkbox" checked={ext.only_priced} onChange={(e) => setExt({ ...ext, only_priced: e.target.checked })} /> {t("up.only_priced")}</label>
              <label className="check"><input type="checkbox" checked={ext.only_available} onChange={(e) => setExt({ ...ext, only_available: e.target.checked })} /> {t("up.only_available")}</label>
              <label className="check"><input type="checkbox" checked={ext.allow_quote} onChange={(e) => setExt({ ...ext, allow_quote: e.target.checked })} /> {t("up.allow_quote")}</label>
              <div className="row"><input className="input" placeholder={t("up.max_price")} value={ext.max_price_amd} onChange={(e) => setExt({ ...ext, max_price_amd: e.target.value.replace(/\D/g, "") })} />
                <input className="input" value={ext.city} onChange={(e) => setExt({ ...ext, city: e.target.value })} aria-label={t("up.city")} /></div>
              <p className="tiny muted">{t("up.src_note")}</p>
            </div>
          )}
          <label className="row top" style={{ opacity: 0.55 }}><input type="radio" disabled style={{ marginTop: 3 }} /><div><b>{t("up.src.own")}</b><div className="small muted">{t("up.src.own_sub")}</div></div></label>
          <label className="row top" style={{ cursor: "pointer" }}><input type="radio" checked={source === "concept"} onChange={() => setSource("concept")} style={{ marginTop: 3 }} />
            <div><b>{t("up.src.concept")}</b><div className="small muted">{t("up.src.concept_sub")}</div></div></label>
        </div>

        <button className="btn primary lg block" onClick={() => generate()}>
          <Sparkles size={18} /> {confirmed ? (source === "external" ? t("up.cta_find") : t("up.cta_create")) : t("up.cta_check")} <ArrowRight size={18} />
        </button>
        {!confirmed && <p className="tiny muted" style={{ textAlign: "center" }}>{t("up.cta_note")}</p>}
      </aside>
    </div>
  );
}

function Block({ icon: I, title, sub, children }: { icon: LucideIcon; title: string; sub: string; children: React.ReactNode }) {
  return (
    <div className="card pad col gap-10">
      <div className="row top"><I size={22} /><div className="grow"><b>{title}</b><div className="small muted">{sub}</div></div></div>
      {children}
    </div>
  );
}
