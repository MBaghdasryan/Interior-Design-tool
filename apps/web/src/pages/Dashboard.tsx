import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { ArrowRight, FolderKanban, PlusCircle, Sparkles } from "lucide-react";
import { api, type Project } from "../lib/api";
import { amd, dt, m2 } from "../lib/format";
import { useT } from "../i18n";
import { AccuracyBadge, Badge, Empty, Loading } from "../components/ui";
import { useMe } from "../components/AppShell";

const TONE: Record<string, string> = { draft: "", intake: "info", recognized: "info", generating: "terra", ready: "sage", approved: "dark", ordered: "dark" };

export function projectLink(p: Project) {
  if (p.status === "draft" || p.status === "intake" || p.status === "recognized") return `/app/p/${p.id}/upload`;
  if (p.status === "generating" && p.last_pipeline_job) return `/app/p/${p.id}/generate/${p.last_pipeline_job.id}`;
  return `/app/p/${p.id}`;
}

export default function Dashboard({ listOnly = false }: { listOnly?: boolean }) {
  const { t } = useT();
  const { me } = useMe();
  const [items, setItems] = useState<Project[] | null>(null);
  useEffect(() => { api<Project[]>("/projects").then(setItems).catch(() => setItems([])); }, []);
  return (
    <div className="col gap-24">
      {!listOnly && (
        <div className="card pad row between wrap" style={{ background: "linear-gradient(120deg, #fffdfa, #f6e6dd)" }}>
          <div><h1>{t("dash.hello", { name: me?.name.split(" ")[0] })}</h1><p className="muted mt-8">{t("dash.lead")}</p></div>
          <Link to="/app/new" className="btn primary lg"><Sparkles size={18} /> {t("nav.new")}</Link>
        </div>
      )}
      <div className="row between"><h2>{t("dash.projects")}</h2><Link to="/app/new" className="btn"><PlusCircle size={16} /> {t("common.create")}</Link></div>
      {!items ? <Loading /> : !items.length ? <Empty>{t("dash.empty")} <Link to="/app/new" className="btn sm primary">{t("dash.create_first")}</Link></Empty> : (
        <div className="grid g3">
          {items.map((p) => (
            <Link key={p.id} to={projectLink(p)} className="card pad col gap-6" style={{ minHeight: 170 }}>
              <div className="row between"><FolderKanban size={20} color="var(--terra-ink)" /><Badge tone={TONE[p.status]}>{t(`enum.project_status.${p.status}`)}</Badge></div>
              <h3 className="mt-8">{p.title}</h3>
              <div className="muted small">{p.address || p.city} · {m2(p.area_m2)}</div>
              <div className="row wrap mt-8"><AccuracyBadge level={p.accuracy_level} />{p.variants ? <Badge>{t("dash.variants", { n: p.variants })}</Badge> : null}</div>
              <div className="row between mt-8" style={{ marginTop: "auto" }}><b className="mono">{p.total ? amd(p.total) : ""}</b><span className="muted tiny">{dt(p.updated_at)} <ArrowRight size={12} /></span></div>
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}
