import { useCallback, useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { ArrowLeft, Download, Plus, Ruler, Trash2 } from "lucide-react";
import { api, type Project } from "../lib/api";
import { amd, dt } from "../lib/format";
import { useT } from "../i18n";
import { Badge, Empty, Loading, useToast } from "../components/ui";

interface ModDef { family: string; w: [number, number, number]; h: [number, number, number]; d: [number, number, number]; doors: number | string; drawers: number }
interface Lib { families: string[]; modules: Record<string, ModDef>; body: string[]; fronts: string[]; hardware: string[]; manufacturers: { id: string; name: string; has_rates: boolean; lead_time_days: number | null }[] }
interface Mod { type: string; w: number; h: number; d: number; body: string; front: string; qty: number }
interface Cfg { id: string; name: string; family: string; supplier_id: string | null; spec: { available_length_mm: number | null; modules: Mod[] }; spec_version: number; status: string;
  issues: { code: string; module: number | null; params: Record<string, string | number> }[]; pricing: { status: string; total_amd: number | null; lead_time_days: number | null; missing?: string[];
  breakdown: { item: string; qty: number; unit: string; amount: number }[] }; order_id: string | null; production_ready: boolean }
interface Ver { version: number; author: string; created_at: string; total_amd: number | null; modules: number }

/** Custom furniture configurator: modules within production ranges, manufacturer pricing, versioned specs, drawings. */
export default function CustomFurniture() {
  const { t, lang } = useT();
  const { pid } = useParams();
  const toast = useToast();
  const [lib, setLib] = useState<Lib | null>(null);
  const [rows, setRows] = useState<Cfg[]>([]);
  const [cur, setCur] = useState<Cfg | null>(null);
  const [draft, setDraft] = useState<{ name: string; family: string; supplier_id: string; available_length_mm: string; modules: Mod[] }>({ name: "", family: "kitchen", supplier_id: "", available_length_mm: "", modules: [] });
  const [vers, setVers] = useState<Ver[]>([]);
  const [proj, setProj] = useState<Project | null>(null);
  const load = useCallback(async () => {
    setRows(await api<Cfg[]>(`/projects/${pid}/custom`));
  }, [pid]);
  useEffect(() => { api<Lib>("/custom/library").then(setLib); api<Project>(`/projects/${pid}`).then(setProj); load(); }, [pid, load]);
  const open = async (c: Cfg) => {
    setCur(c);
    setDraft({ name: c.name, family: c.family, supplier_id: c.supplier_id || "", available_length_mm: c.spec.available_length_mm ? String(c.spec.available_length_mm) : "", modules: c.spec.modules });
    setVers(await api<Ver[]>(`/projects/${pid}/custom/${c.id}/versions`));
  };
  const save = async () => {
    const body = { name: draft.name || t("cst.untitled"), family: draft.family, supplier_id: draft.supplier_id || null,
      available_length_mm: draft.available_length_mm ? Number(draft.available_length_mm) : null, modules: draft.modules };
    try {
      const c = await api<Cfg>(cur ? `/projects/${pid}/custom/${cur.id}` : `/projects/${pid}/custom`, { method: cur ? "PUT" : "POST", json: body });
      toast(t("cst.saved", { v: c.spec_version }));
      await load();
      await open(c);
    } catch (x) { toast((x as Error).message, true); }
  };
  const order = async () => { if (!cur) return; try { await api(`/projects/${pid}/custom/${cur.id}/order`, { method: "POST" }); toast(t("cst.ordered")); await load(); } catch (x) { toast((x as Error).message, true); } };
  if (!lib) return <Loading />;
  const types = Object.entries(lib.modules).filter(([, v]) => v.family === draft.family);
  const addModule = () => {
    const [k, v] = types[0];
    setDraft({ ...draft, modules: [...draft.modules, { type: k, w: v.w[0] + v.w[2] * Math.round((v.w[1] - v.w[0]) / v.w[2] / 3), h: v.h[0], d: v.d[0], body: lib.body[0], front: lib.fronts[1] || lib.fronts[0], qty: 1 }] });
  };
  const setMod = (i: number, patch: Partial<Mod>) => setDraft({ ...draft, modules: draft.modules.map((m, j) => (j === i ? { ...m, ...patch } : m)) });
  const issueText = (i: Cfg["issues"][number]) => `${i.module !== null ? `M${i.module + 1}: ` : ""}${t(`cst.issue.${i.code.split(".")[1]}`, { ...i.params, dim: i.params.dim ? t(`cst.dim.${i.params.dim}`) : "" })}`;
  return (
    <div className="col gap-16">
      <div className="row"><Link to={`/app/p/${pid}`} className="icon-btn" aria-label={t("common.back")}><ArrowLeft size={18} /></Link>
        <div><h1>{t("cst.title")}</h1><div className="muted">{t("cst.lead")}</div></div></div>
      {proj && proj.accuracy_level !== "production" && <div className="alert warn small"><Ruler size={16} /> {t("cst.not_production")}</div>}
      <div className="grid" style={{ gridTemplateColumns: "minmax(220px, 1fr) 3fr", alignItems: "start", gap: 16 }}>
        <div className="card pad col gap-8">
          <button className="btn sm primary" onClick={() => { setCur(null); setVers([]); setDraft({ name: "", family: "kitchen", supplier_id: "", available_length_mm: "", modules: [] }); }}><Plus size={14} /> {t("cst.new")}</button>
          {!rows.length && <Empty>{t("cst.empty")}</Empty>}
          {rows.map((c) => <button key={c.id} className={`btn ghost ${cur?.id === c.id ? "on" : ""}`} style={{ justifyContent: "space-between" }} onClick={() => open(c)}>
            <span>{c.name}</span><Badge tone={c.status === "valid" ? "sage" : c.status === "ordered" ? "info" : "warn"}>{t(`cst.status.${c.status}`)}</Badge></button>)}
        </div>
        <div className="col gap-12">
          <section className="card pad col gap-10" aria-labelledby="cst-ed">
            <h3 id="cst-ed">{cur ? t("cst.edit", { v: cur.spec_version }) : t("cst.new")}</h3>
            <div className="grid g4">
              <label className="col gap-4"><span className="tiny muted">{t("cst.name")}</span><input className="input" value={draft.name} onChange={(e) => setDraft({ ...draft, name: e.target.value })} /></label>
              <label className="col gap-4"><span className="tiny muted">{t("cst.family")}</span><select className="select input" value={draft.family} onChange={(e) => setDraft({ ...draft, family: e.target.value, modules: [] })}>{lib.families.map((f) => <option key={f} value={f}>{t(`cst.fam.${f}`)}</option>)}</select></label>
              <label className="col gap-4"><span className="tiny muted">{t("cst.manufacturer")}</span><select className="select input" value={draft.supplier_id} onChange={(e) => setDraft({ ...draft, supplier_id: e.target.value })}>
                <option value="">{t("cst.no_manufacturer")}</option>{lib.manufacturers.map((mf) => <option key={mf.id} value={mf.id}>{mf.name}{mf.has_rates ? "" : ` (${t("cst.no_rates")})`}</option>)}</select></label>
              {draft.family === "kitchen" && <label className="col gap-4"><span className="tiny muted">{t("cst.available")}</span><input className="input" inputMode="numeric" value={draft.available_length_mm} onChange={(e) => setDraft({ ...draft, available_length_mm: e.target.value })} /></label>}
            </div>
            <div style={{ overflow: "auto" }}><table className="table compact">
              <thead><tr><th>#</th><th>{t("cst.module")}</th><th>{t("cst.dim.w")}</th><th>{t("cst.dim.h")}</th><th>{t("cst.dim.d")}</th><th>{t("cst.body")}</th><th>{t("cst.front")}</th><th>{t("cst.qty")}</th><th /></tr></thead>
              <tbody>{draft.modules.map((md, i) => { const def = lib.modules[md.type]; return <tr key={i}>
                <td className="small">M{i + 1}</td>
                <td><select className="select input" aria-label={t("cst.module")} value={md.type} onChange={(e) => setMod(i, { type: e.target.value })}>{types.map(([k]) => <option key={k} value={k}>{t(`cst.mod.${k}`)}</option>)}</select></td>
                {(["w", "h", "d"] as const).map((k) => <td key={k}><input className="input" style={{ width: 80 }} inputMode="numeric" aria-label={t(`cst.dim.${k}`)} title={def ? `${def[k][0]}–${def[k][1]}, ${t("cst.step")} ${def[k][2]}` : ""} value={md[k]} onChange={(e) => setMod(i, { [k]: Number(e.target.value) || 0 })} /></td>)}
                <td><select className="select input" aria-label={t("cst.body")} value={md.body} onChange={(e) => setMod(i, { body: e.target.value })}>{lib.body.map((b) => <option key={b} value={b}>{t(`cst.mat.${b}`)}</option>)}</select></td>
                <td><select className="select input" aria-label={t("cst.front")} value={md.front} onChange={(e) => setMod(i, { front: e.target.value })}>{lib.fronts.map((b) => <option key={b} value={b}>{t(`cst.mat.${b}`)}</option>)}</select></td>
                <td><input className="input" style={{ width: 56 }} inputMode="numeric" aria-label={t("cst.qty")} value={md.qty} onChange={(e) => setMod(i, { qty: Number(e.target.value) || 1 })} /></td>
                <td><button className="icon-btn" aria-label={t("common.delete")} onClick={() => setDraft({ ...draft, modules: draft.modules.filter((_, j) => j !== i) })}><Trash2 size={14} /></button></td></tr>; })}</tbody></table></div>
            <div className="row gap-6"><button className="btn sm ghost" onClick={addModule}><Plus size={14} /> {t("cst.add_module")}</button>
              <button className="btn primary" disabled={!draft.modules.length || cur?.status === "ordered"} onClick={save}>{t("cst.save")}</button></div>
          </section>
          {cur && <section className="card pad col gap-8" aria-labelledby="cst-res">
            <div className="row between wrap"><h3 id="cst-res">{t("cst.result", { v: cur.spec_version })}</h3>
              <div className="row gap-6">{!cur.issues.length && <><a className="btn sm" href={`/api/v1/projects/${pid}/custom/${cur.id}/drawing.dxf`}><Download size={14} /> DXF</a>
                <a className="btn sm" href={`/api/v1/projects/${pid}/custom/${cur.id}/drawing.pdf?lang=${lang}`} target="_blank" rel="noreferrer"><Download size={14} /> PDF</a></>}</div></div>
            {cur.issues.length > 0 && <div className="alert danger small col gap-4">{cur.issues.map((i, k) => <div key={k}>{issueText(i)}</div>)}</div>}
            {cur.pricing.status === "priced" && <div className="col gap-4">
              <b className="mono">{amd(cur.pricing.total_amd)}</b>{cur.pricing.lead_time_days && <span className="tiny muted">{t("common.days", { n: cur.pricing.lead_time_days })}</span>}
              <table className="table compact"><tbody>{cur.pricing.breakdown.map((b) => <tr key={b.item}><td className="small">{b.item.startsWith("hardware:") ? t(`cst.hw.${b.item.slice(9)}`) : b.item.includes(":") ? `${t(`cst.part.${b.item.split(":")[0]}`)} · ${t(`cst.mat.${b.item.split(":")[1]}`)}` : t(`cst.part.${b.item}`)}</td>
                <td className="right small mono">{b.qty} {b.unit}</td><td className="right small mono">{amd(b.amount)}</td></tr>)}</tbody></table></div>}
            {cur.pricing.status === "quote_required" && <div className="alert info small">{t("cst.quote_required")}</div>}
            <div className="row gap-6 wrap">
              {!cur.order_id && <button className="btn ghost" onClick={async () => { await api(`/projects/${pid}/custom/${cur.id}`, { method: "DELETE" }).catch(() => {}); setCur(null); setVers([]); load(); }}><Trash2 size={14} /> {t("common.delete")}</button>}
              {cur.order_id ? <Link className="btn" to={`/app/p/${pid}/procurement`}>{t("cst.to_order")}</Link>
                : <button className="btn primary" disabled={cur.pricing.status !== "priced" || !cur.production_ready} title={cur.production_ready ? "" : t("cst.not_production")} onClick={order}>{t("cst.order")}</button>}
            </div>
            {vers.length > 0 && <details className="tiny muted"><summary>{t("cst.versions", { n: vers.length })}</summary>
              {vers.map((v) => <div key={v.version}>v{v.version} · {dt(v.created_at)} · {v.author} · {v.modules} · {v.total_amd ? amd(v.total_amd) : "—"}</div>)}</details>}
          </section>}
        </div>
      </div>
    </div>
  );
}
