import { useCallback, useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { ArrowLeft, Box, Download, FileArchive, FileSpreadsheet, FileText, Layers, Loader2, PenTool } from "lucide-react";
import { api, fileUrl, streamJob, type Doc, type Job, type Project, type Variant } from "../lib/api";
import { dt, kb, variantTitle } from "../lib/format";
import { stepDetail, stepTitle } from "../lib/messages";
import { LANGS, useT } from "../i18n";
import ApsViewer from "../components/ApsViewer";
import { Badge, Empty, Loading, Progress, StepStatus, useToast } from "../components/ui";
import ApsCapabilities from "../components/ApsCapabilities";
import { useMe } from "../components/AppShell";

const ICON: Record<string, typeof FileText> = { album_pdf: FileText, dwg: PenTool, dxf: PenTool, xlsx: FileSpreadsheet, csv: FileSpreadsheet, glb: Box, json: FileArchive };
const SECTIONS = [1, 2, 3, 4, 5];

export default function Documents() {
  const { t } = useT();
  const { pid } = useParams();
  const toast = useToast();
  const { cfg } = useMe();
  const [variants, setVariants] = useState<Variant[]>([]);
  const [vid, setVid] = useState("");
  const [lang, setLang] = useState("hy");
  const [sections, setSections] = useState<number[]>([]);
  const [docs, setDocs] = useState<Doc[]>([]);
  const [job, setJob] = useState<Job | null>(null);
  const [viewUrn, setViewUrn] = useState<string | null>(null);
  const [project, setProject] = useState<Project | null>(null);

  const load = useCallback(async () => {
    const p = await api<Project>(`/projects/${pid}`);
    setProject(p); setLang(p.doc_lang || "hy");
    const vs: Variant[] = p.variants || [];
    setVariants(vs);
    setVid((cur) => cur || (vs.find((v) => v.status === "approved") || vs.find((v) => v.status === "selected") || vs[0])?.id || "");
    setDocs(await api<Doc[]>(`/projects/${pid}/documents`));
  }, [pid]);
  useEffect(() => { load(); }, [load]);

  const run = async (kind: "album" | "dwg") => {
    try {
      const j = await api<Job>(`/projects/${pid}/documents/${kind}`, { method: "POST", json: { variant_id: vid, lang, sections } });
      setJob(j);
      if (!["succeeded", "failed"].includes(j.status)) streamJob(pid!, j.id, (x) => { setJob(x); if (x.status === "succeeded") load(); });
      else load();
    } catch (x) { toast((x as Error).message, true); }
  };
  if (!project) return <Loading />;
  const byTime = docs.reduce<Record<string, Doc[]>>((a, d) => { (a[d.created_at.slice(0, 16)] ||= []).push(d); return a; }, {});
  const album = docs.find((d) => d.kind === "album_pdf");

  return (
    <div className="col gap-16">
      <div className="row"><Link to={`/app/p/${pid}`} className="icon-btn" aria-label={t("common.back")}><ArrowLeft size={18} /></Link><div><h1>{t("doc.title")}</h1><div className="muted">{t("doc.lead")}</div></div></div>
      <div className="grid" style={{ gridTemplateColumns: "minmax(0,1fr) 380px", alignItems: "start" }}>
        <div className="card pad col gap-16">
          <h3>{t("doc.make")}</h3>
          <div className="grid g3">
            <div className="field"><label>{t("common.variant")}</label><select aria-label={t("common.variant")} className="select input" value={vid} onChange={(e) => setVid(e.target.value)}>{variants.map((v) => <option key={v.id} value={v.id}>{variantTitle(v)}{v.status === "approved" ? t("doc.approved_suffix") : ""}</option>)}</select></div>
            <div className="field"><label>{t("doc.album_lang")}</label><select aria-label={t("doc.album_lang")} className="select input" value={lang} onChange={(e) => setLang(e.target.value)}>{LANGS.map((l) => <option key={l.code} value={l.code}>{l.name}</option>)}</select></div>
            <div className="field"><label>{t("doc.sections")}</label><div className="row wrap">{SECTIONS.map((n) => <button key={n} className={`chip ${sections.length === 0 || sections.includes(n) ? "on" : ""}`} title={t(`doc.sec.${n}`)}
              onClick={() => setSections((s) => (s.length === 0 ? SECTIONS.filter((x) => x !== n) : s.includes(n) ? s.filter((x) => x !== n) : [...s, n]))}>{t(`doc.sec.${n}`).split(" ")[0]}</button>)}</div></div>
          </div>
          <div className="row wrap">
            <button className="btn primary lg" disabled={!vid || job?.status === "running"} onClick={() => run("album")}><Layers size={18} /> {t("doc.album_btn")}</button>
            <button className="btn lg" disabled={!vid || !cfg?.aps_enabled} onClick={() => run("dwg")} title={cfg?.aps_enabled ? "" : t("adm.aps_hint")}><PenTool size={18} /> {t("doc.dwg_btn")}</button>
            {!cfg?.aps_enabled && <Badge tone="warn">{t("doc.aps_off")}</Badge>}
            <ApsCapabilities />
          </div>
          {job && (
            <div className="card flat pad col gap-6">
              <div className="row between"><b className="row gap-6">{job.status === "running" || job.status === "queued" ? <Loader2 size={16} /> : null}{job.kind === "album" ? t("doc.album") : "DWG"}: {t(`enum.job.${job.status}`)}</b><span className="small muted">{Math.round(job.progress * 100)}%</span></div>
              <Progress value={job.progress} />
              {job.steps.map((s) => <div key={s.key} className="small row gap-6"><StepStatus s={s.status} />{stepTitle(s)} <span className="muted">{stepDetail(s)}</span></div>)}
              {job.error && <div className="alert danger small">{job.error}</div>}
            </div>
          )}
          {album?.meta.sheets && (
            <div>
              <h3>{t("doc.composition", { n: album.meta.sheets.length + 2 })}</h3>
              <div className="grid g3 mt-8">
                {SECTIONS.map((n) => {
                  const sh = album.meta.sheets!.filter((s) => s.section === n);
                  if (!sh.length) return null;
                  return <div key={n} className="card flat pad"><b className="small">{t(`doc.sec.${n}`)}</b>{sh.map((s) => <div key={s.code} className="tiny row gap-6"><span className="mono" style={{ width: 52 }}>{s.code}</span>{s.title}</div>)}</div>;
                })}
              </div>
            </div>
          )}
          {album && <iframe title={t("doc.album")} src={fileUrl(album.url)} style={{ width: "100%", height: 640, border: "1px solid var(--line)", borderRadius: 12 }} />}
        </div>
        <aside className="col gap-16">
          <div className="card pad col gap-10">
            <h3>{t("doc.files")}</h3>
            {!docs.length && <Empty>{t("doc.none")}</Empty>}
            {Object.entries(byTime).map(([when, ds]) => (
              <div key={when} className="col gap-6"><div className="tiny muted">{dt(ds[0].created_at)}</div>
                {ds.map((d) => {
                  const I = ICON[d.kind] || FileText;
                  return <div key={d.id} className="row top">
                    <I size={18} /><div className="grow"><b className="small">{t(`doc.kind.${d.kind}`)}</b><div className="tiny muted">{d.filename} · {kb(d.size)}</div></div>
                    {d.meta.aps?.urn && <button className="btn sm ghost" onClick={() => setViewUrn(d.meta.aps!.urn!)}>{t("doc.view")}</button>}
                    <a className="icon-btn" href={fileUrl(d.url)} aria-label={t("common.download")}><Download size={16} /></a>
                  </div>;
                })}
              </div>
            ))}
          </div>
          <div className="card pad small col gap-6">
            <b>{t("doc.what")}</b>
            {Object.keys(ICON).map((k) => <div key={k}><b>{t(`doc.kind.${k}`)}</b> — <span className="muted">{t(`doc.hint.${k}`)}</span></div>)}
            <div className="muted">{t("doc.roadmap")}</div>
          </div>
        </aside>
      </div>
      {viewUrn && <div className="card pad"><div className="row between mb-8"><h3>{t("doc.viewer")}</h3><button className="btn sm" onClick={() => setViewUrn(null)}>{t("common.close")}</button></div><ApsViewer urn={viewUrn} /></div>}
    </div>
  );
}
