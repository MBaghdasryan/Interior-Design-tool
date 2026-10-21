import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { AlertTriangle, ArrowRight, Calculator, Check, Database, Layers, PackageSearch, RefreshCw, ScanLine, Sofa, Sparkles, Store, Truck, X } from "lucide-react";
import { api, streamJob, type Job, type Scene } from "../lib/api";
import { stepDetail, stepTitle } from "../lib/messages";
import { useT } from "../i18n";
import Scene3D from "../components/Scene3D";
import { Badge, Progress, useToast } from "../components/ui";

const PIPE = [
  { keys: ["rooms", "geometry", "normalize"], icon: ScanLine, k: "recognize" },
  { keys: ["conflicts", "brief", "layout"], icon: Layers, k: "layout" },
  { keys: ["cat_needs", "cat_search", "cat_compare", "style", "products"], icon: Sofa, k: "products" },
  { keys: ["dims", "materials"], icon: Calculator, k: "estimate" },
  { keys: ["cat_availability", "cat_snapshot", "prices"], icon: PackageSearch, k: "stock" },
  { keys: ["delivery", "visuals", "assemble"], icon: Truck, k: "assemble" },
];

function stepState(job: Job | null, keys: string[]) {
  const st = (job?.steps || []).filter((s) => keys.includes(s.key));
  if (!st.length) return "pending";
  if (st.some((s) => s.status === "failed")) return "failed";
  if (st.some((s) => s.status === "running")) return "running";
  if (st.every((s) => ["done", "warning", "skipped"].includes(s.status))) return st.some((s) => s.status === "warning") ? "warning" : "done";
  if (st.some((s) => ["done", "warning"].includes(s.status))) return "running";
  return "pending";
}

export default function Generation() {
  const { t } = useT();
  const { pid, jid } = useParams();
  const nav = useNavigate();
  const toast = useToast();
  const [job, setJob] = useState<Job | null>(null);
  const [base, setBase] = useState<Scene | null>(null);
  useEffect(() => { api<{ scene: Scene }>(`/projects/${pid}/geometry`).then((g) => setBase(g.scene)); }, [pid]);
  useEffect(() => streamJob(pid!, jid!, setJob), [pid, jid]);
  useEffect(() => { if (job?.status === "succeeded") { const tm = setTimeout(() => nav(`/app/p/${pid}`), 1800); return () => clearTimeout(tm); } }, [job?.status, nav, pid]);
  const c = job?.counters || {};
  const catalog = (job?.steps || []).filter((s) => s.phase === "catalog");
  const design = (job?.steps || []).filter((s) => s.phase === "design");
  const retry = async () => { try { setJob(await api(`/projects/${pid}/jobs/${jid}/retry`, { method: "POST" })); streamJob(pid!, jid!, setJob); } catch (x) { toast((x as Error).message, true); } };

  return (
    <div className="col gap-16">
      <div className="card" style={{ overflow: "hidden" }}>
        <div style={{ position: "relative" }}>
          {base ? <Scene3D scene={base} height={380} interactive autoRotate cutaway /> : <div className="skeleton" style={{ height: 380 }} />}
          <div style={{ position: "absolute", top: 16, right: 16 }} className="card pad row gap-6">
            <Sparkles size={18} color="var(--terra-ink)" />
            <div><b style={{ color: "var(--terra-ink)" }}>{job?.status === "succeeded" ? t("gen.done") : job?.status === "failed" ? t("gen.stopped") : t("gen.active")}</b><div className="tiny muted">{t("gen.creating")}</div></div>
          </div>
          <span className="label-pill" style={{ left: 16, background: "rgba(46,46,46,.85)" }}>{t("gen.source_geo")}</span>
        </div>
        <div style={{ padding: "24px 28px" }}>
          <h1>{t("landing.h1")}</h1>
          <p className="muted mt-8">{t("gen.lead")}</p>
          <div className="pipeline mt-24">
            {PIPE.map((p, i) => {
              const s = stepState(job, p.keys);
              return (
                <div key={p.k} className="row" style={{ flex: i < PIPE.length - 1 ? 1 : undefined }}>
                  <div className={`pipe-step ${s}`}><div className="ic">{s === "done" ? <Check size={22} /> : s === "failed" ? <X size={22} /> : <p.icon size={22} />}</div><b>{t(`gen.step.${p.k}`)}</b></div>
                  {i < PIPE.length - 1 && <div className={`pipe-line ${s === "done" || s === "warning" ? "done" : ""}`} />}
                </div>
              );
            })}
          </div>
          <div className="mt-16"><Progress value={job?.progress || 0} /></div>
          <div className="grid g4 mt-24">
            <div className="card flat kpi"><div className="ico"><Layers size={22} /></div><div><div className="v">{t("gen.kpi.rooms", { n: c.rooms ?? "…" })}</div><div className="muted small">{c.area_m2 ? `${c.area_m2} ${t("common.m2")}` : t("gen.kpi.recognizing")}</div></div></div>
            <div className="card flat kpi"><div className="ico"><Sofa size={22} /></div><div><div className="v">{t("gen.kpi.products", { n: c.products ?? c.found ?? "…" })}</div><div className="muted small">{t("gen.kpi.products_sub")}{c.demo_fallback ? ` · ${t("gen.demo_n", { n: c.demo_fallback })}` : ""}</div></div></div>
            <div className="card flat kpi"><div className="ico"><Store size={22} /></div><div><div className="v">{t("gen.kpi.sources", { a: c.sources_checked ?? "—", b: c.sources_total ?? "—" })}</div><div className="muted small">{t("gen.kpi.sources_sub")}</div></div></div>
            <div className="card flat kpi"><div className="ico"><Calculator size={22} /></div><div><div className="v">{job?.status === "succeeded" ? t("gen.kpi.estimate") : "…"}</div><div className="muted small">{t("gen.kpi.estimate_sub")}</div></div></div>
          </div>
        </div>
      </div>

      <div className="grid g2" style={{ alignItems: "start" }}>
        {catalog.length > 0 && (
          <div className="card pad">
            <div className="row"><Database size={18} /><h3 className="grow">{t("gen.phase1")}</h3><Badge tone="info">{t("up.src.external")}</Badge></div>
            <div className="grid g3 mt-16 small">
              {([["found", c.found], ["validated", c.validated], ["rfq", c.quote_required], ["no_price", c.no_price], ["doubtful", c.stale_or_doubtful]] as [string, number | undefined][]).map(([k, v]) => (
                <div key={k}><b className="mono" style={{ fontSize: 18 }}>{v ?? 0}</b><div className="muted">{t(`gen.${k}`)}</div></div>
              ))}
              <div><b className="mono" style={{ fontSize: 18 }}>{c.needs_covered ?? 0}/{c.needs_total ?? 0}</b><div className="muted">{t("gen.covered")}</div></div>
            </div>
            <StepList steps={catalog} />
          </div>
        )}
        <div className="card pad">
          <div className="row"><Sparkles size={18} /><h3 className="grow">{catalog.length ? t("gen.phase2") : t("gen.phase_design")}</h3></div>
          <StepList steps={design} />
        </div>
      </div>
      {job?.status === "failed" && <div className="alert danger"><AlertTriangle size={18} /><div className="grow">{job.error}</div><button className="btn sm" onClick={retry}><RefreshCw size={14} /> {t("common.retry")}</button></div>}
      {job?.status === "succeeded" && <div className="row"><button className="btn primary lg" onClick={() => nav(`/app/p/${pid}`)}>{t("gen.view")} <ArrowRight size={18} /></button></div>}
    </div>
  );
}

function StepList({ steps }: { steps: Job["steps"] }) {
  const { t } = useT();
  return (
    <div className="step-list mt-16">
      {steps.map((s) => (
        <div key={s.key} className="it">
          <span>{s.status === "done" ? <Check size={18} color="var(--sage-ink)" /> : s.status === "warning" ? <AlertTriangle size={18} color="var(--warn)" /> : s.status === "running" ? <span className="spinner" /> : s.status === "failed" ? <X size={18} color="var(--danger)" /> : <span className="dot" style={{ background: "var(--line-2)", margin: 5 }} />}</span>
          <div><b style={{ color: s.status === "pending" ? "var(--ink-3)" : undefined }}>{stepTitle(s)}</b>{stepDetail(s) && <div className="small muted">{stepDetail(s)}</div>}</div>
          <span className="tiny muted">{t(`enum.step.${s.status}`)}</span>
        </div>
      ))}
    </div>
  );
}
