import { useEffect, useMemo, useState } from "react";
import { Link, Navigate } from "react-router-dom";
import { ArrowRight, Check, CheckCircle2, FolderKanban, ImageOff, Layers, Plus, Trash2, Wallet } from "lucide-react";
import { api, type Project } from "../lib/api";
import { amd, dt, m2 } from "../lib/format";
import { useT } from "../i18n";
import { AccuracyBadge, Badge, Empty, Kpi, Loading, monthly, useToast } from "../components/ui";
import { useMe } from "../components/AppShell";

const TONE: Record<string, string> = { draft: "", intake: "info", recognized: "info", generating: "terra", ready: "sage", approved: "dark", ordered: "dark" };
// project lifecycle as the stage timeline of the dashboard (mockup 20)
const STAGES = ["intake", "recognized", "generating", "ready", "approved", "ordered"] as const;
const stageIndex = (s: string) => Math.max(0, STAGES.indexOf((s === "draft" ? "intake" : s) as (typeof STAGES)[number]));
const ACTIVE = new Set(["draft", "intake", "recognized", "generating", "ready"]);

export function projectLink(p: Project) {
  if (p.status === "draft" || p.status === "intake" || p.status === "recognized") return `/app/p/${p.id}/upload`;
  if (p.status === "generating" && p.last_pipeline_job) return `/app/p/${p.id}/generate/${p.last_pipeline_job.id}`;
  return `/app/p/${p.id}`;
}

/** Deletes a project after confirmation; the server refuses projects with placed orders. */
export function useDeleteProject(onDone: () => void) {
  const { t } = useT();
  const toast = useToast();
  return async (p: Project) => {
    if (!confirm(t("dash.confirm_delete", { title: p.title }))) return;
    try { await api(`/projects/${p.id}`, { method: "DELETE" }); toast(t("dash.deleted")); onDone(); } catch (x) { toast((x as Error).message, true); }
  };
}

export default function Dashboard({ listOnly = false }: { listOnly?: boolean }) {
  const { t } = useT();
  const { me } = useMe();
  const [items, setItems] = useState<Project[] | null>(null);
  const load = () => api<Project[]>("/projects").then(setItems).catch(() => setItems([]));
  useEffect(() => { load(); }, []);
  const roles = new Set(me?.roles || []);
  const stats = useMemo(() => {
    const xs = items || [];
    return {
      total: xs.length, active: xs.filter((p) => ACTIVE.has(p.status)).length, approved: xs.filter((p) => !ACTIVE.has(p.status)).length,
      budget: xs.reduce((s, p) => s + (p.total || 0), 0),
      sTotal: monthly(xs, (p) => p.created_at), sActive: monthly(xs.filter((p) => ACTIVE.has(p.status)), (p) => p.updated_at),
      sBudget: monthly(xs, (p) => p.updated_at, 6, (p) => p.total || 0), sApproved: monthly(xs.filter((p) => !ACTIVE.has(p.status)), (p) => p.updated_at),
    };
  }, [items]);
  // suppliers and the catalogue operator do not design projects: their home is their cabinet
  if (!roles.has("platform_admin") && (roles.has("supplier_admin") || roles.has("supplier_catalog") || roles.has("manufacturer"))) return <Navigate to="/app/supplier" replace />;
  if (!roles.has("platform_admin") && roles.has("platform_ops")) return <Navigate to="/app/admin?tab=sources" replace />;
  return (
    <div className="col gap-16">
      <div className="row between wrap gap-12">
        <div>
          <h1>{listOnly ? t("dash.projects") : t("dash.hello", { name: me?.name.split(" ")[0] })}</h1>
          <p className="muted mt-8">{items && t("dash.lead_n", { n: stats.active })}</p>
        </div>
        <Link to="/app/new" className="btn primary lg"><Plus size={18} /> {t("nav.new")}</Link>
      </div>
      {!listOnly && items && items.length > 0 && <div className="grid g4">
        <Kpi icon={<FolderKanban size={20} />} value={stats.total} label={t("dash.k.total")} series={stats.sTotal} sub={t("dash.k.by_month")} />
        <Kpi icon={<Layers size={20} />} value={stats.active} label={t("dash.k.active")} series={stats.sActive} tone="sage" sub={t("dash.k.by_month_updated")} />
        <Kpi icon={<Wallet size={20} />} value={amd(stats.budget)} label={t("dash.k.budget")} series={stats.sBudget} sub={t("dash.k.budget_hint")} />
        <Kpi icon={<CheckCircle2 size={20} />} value={stats.approved} label={t("dash.k.approved")} series={stats.sApproved} tone="sage" sub={t("dash.k.by_month_updated")} />
      </div>}
      {!items ? <Loading /> : !items.length ? <Empty>{t("dash.empty")} <Link to="/app/new" className="btn sm primary">{t("dash.create_first")}</Link></Empty>
        : <ProjectsBoard items={items} listOnly={listOnly} onChanged={load} />}
    </div>
  );
}

/** Project cards with cover, progress and delete, plus the stage timeline of the hovered project (mockups 15 and 20). */
export function ProjectsBoard({ items, listOnly = false, onChanged }: { items: Project[]; listOnly?: boolean; onChanged: () => void }) {
  const { t } = useT();
  const [sel, setSel] = useState<string>("");
  const del = useDeleteProject(onChanged);
  const focus = items.find((p) => p.id === sel) || items[0];
  const recent = items.slice(0, listOnly ? 200 : 6);
  return (
        <div className={listOnly ? "" : "dash-grid"}>
          <section className={listOnly ? "" : "card pad col gap-12"} aria-labelledby="recent-h">
            {!listOnly && <div className="row between"><h3 id="recent-h">{t("dash.recent")}</h3><Link to="/app/projects" className="small">{t("dash.all_projects")} <ArrowRight size={13} /></Link></div>}
            <div className="grid g3">
              {recent.map((p) => {
                const k = stageIndex(p.status);
                return (
                  <article key={p.id} className="card pcard" onMouseEnter={() => setSel(p.id)} onFocus={() => setSel(p.id)}>
                    <div className="img" style={p.cover ? { backgroundImage: `url(${p.cover})` } : undefined}>
                      <Link to={projectLink(p)} className="cover-link" aria-label={p.title} />
                      {!p.cover && <ImageOff size={26} aria-hidden />}
                      <div className="tools"><button className="icon-btn" style={{ background: "var(--surface)" }} aria-label={`${t("dash.delete")}: ${p.title}`} title={t("dash.delete")} onClick={() => del(p)}><Trash2 size={15} /></button></div>
                    </div>
                    <Link to={projectLink(p)} className="bd" style={{ color: "inherit" }}>
                      <b>{p.title}</b>
                      <div className="tiny muted">{[p.city, m2(p.area_m2)].filter(Boolean).join(" · ")} · <span style={{ color: "var(--sage-ink)" }}>{t(`enum.project_status.${p.status}`)}</span></div>
                      <div className="row between tiny"><span>{t("dash.progress")}</span><b>{Math.round(((k + 1) / STAGES.length) * 100)}%</b></div>
                      <div className={`bar ${k < 3 ? "terra" : ""}`}><i style={{ width: `${((k + 1) / STAGES.length) * 100}%` }} /></div>
                      <div className="row between mt-8" style={{ marginTop: "auto" }}><AccuracyBadge level={p.accuracy_level} /><b className="mono small">{p.total ? amd(p.total) : ""}</b></div>
                      <div className="tiny muted">{p.client_name ? `${t("dash.client")}: ${p.client_name} · ` : ""}{dt(p.updated_at)}</div>
                    </Link>
                  </article>
                );
              })}
            </div>
          </section>
          {!listOnly && focus && <aside className="card pad col gap-10" aria-labelledby="stages-h">
            <h3 id="stages-h">{t("dash.stages")}</h3>
            <div className="small muted">{focus.title}</div>
            <ol className="stages mt-8">
              {STAGES.map((s, i) => {
                const k = stageIndex(focus.status);
                return <li key={s} className={i < k ? "done" : i === k ? "now" : ""}><span className="dot2">{i < k && <Check size={12} />}</span><div><b className="small">{t(`dash.stage.${s}`)}</b></div></li>;
              })}
            </ol>
            <div className="row gap-6 wrap"><Badge tone={TONE[focus.status]}>{t(`enum.project_status.${focus.status}`)}</Badge>{focus.variants ? <Badge>{t("dash.variants", { n: focus.variants })}</Badge> : null}</div>
            <Link className="btn sm" to={projectLink(focus)}>{t("dash.open")} <ArrowRight size={14} /></Link>
          </aside>}
        </div>
  );
}
