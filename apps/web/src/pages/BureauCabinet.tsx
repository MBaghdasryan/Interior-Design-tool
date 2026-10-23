import { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { Building2, CheckCircle2, FolderKanban, Hourglass, Plus, Save, Wallet } from "lucide-react";
import { api, ApiError, type Project } from "../lib/api";
import { amd } from "../lib/format";
import { useT } from "../i18n";
import { Empty, Kpi, Loading, monthly, useToast } from "../components/ui";
import { ProjectsBoard } from "./Dashboard";
import AiUsageCard from "../components/AiUsageCard";
import { useMe } from "../components/AppShell";
import { OrgPicker, TeamCard } from "../components/Management";
import { ScopeCtx, withQs } from "../lib/scope";

interface Ov { org: { id: string; name: string; settings: { title_block?: Record<string, string> } }; members: { name: string; email: string; role: string }[]; projects: Project[]; status_counts: Record<string, number>; pipeline_value: number }

/** Bureau cabinet. Platform staff pick any bureau (?org=…) and work in it as its head would. */
export default function BureauCabinet() {
  const { t } = useT();
  const toast = useToast();
  const { me } = useMe();
  const [sp, setSp] = useSearchParams();
  const isPlatform = !!me?.roles.some((r) => r === "platform_admin" || r === "platform_ops");
  const ownBureau = !!me?.memberships.some((x) => x.org_kind === "bureau");
  const orgId = isPlatform ? sp.get("org") || "" : "";
  const qs = orgId ? `org_id=${encodeURIComponent(orgId)}` : "";
  const [ov, setOv] = useState<Ov | null>(null);
  const [err, setErr] = useState("");
  const [tb, setTb] = useState<Record<string, string>>({});
  const canManage = !!me?.roles.includes("bureau_admin") || !!me?.roles.includes("platform_admin");
  const reload = () => api<Ov>(withQs("/bureau/overview", qs)).then(setOv).catch(() => {});
  useEffect(() => {
    setOv(null); setErr("");
    if (isPlatform && !orgId && !ownBureau) return;
    api<Ov>(withQs("/bureau/overview", qs)).then((o) => { setOv(o); setTb(o.org.settings.title_block || {}); }).catch((e: ApiError) => setErr(e.message));
  }, [qs, isPlatform, orgId, ownBureau]);
  const active = ov ? ov.projects.filter((p) => !["approved", "ordered"].includes(p.status)).length : 0;
  const save = async () => { try { await api(withQs("/bureau/settings", qs), { method: "PUT", json: { title_block: tb } }); toast(t("bur.saved")); } catch (x) { toast((x as Error).message, true); } };
  const picker = isPlatform && <OrgPicker kind="bureau" value={orgId} onChange={(v) => setSp(v ? { org: v } : {})} />;
  if (isPlatform && !orgId && !ownBureau) return <div className="col gap-16"><h1><Building2 size={26} /> {t("nav.bureau")}</h1>{picker}<Empty>{t("mg.pick_bureau")}</Empty></div>;
  if (err) return <div className="col gap-16">{picker}<div className="alert danger">{err}</div></div>;
  if (!ov) return <div className="col gap-16">{picker}<Loading /></div>;
  return (
    <ScopeCtx.Provider value={{ qs }}>
      <div className="col gap-16">
        <div className="row between wrap gap-12">
          <div><h1>{t("bur.hello", { name: me?.name.split(" ")[0] || "" })}</h1><p className="muted" style={{ margin: 0 }}><Building2 size={15} /> {ov.org.name} · {t("dash.lead_n", { n: active })}</p></div>
          <div className="row gap-8 wrap">{picker}{!orgId && <Link to="/app/new" className="btn primary lg"><Plus size={18} /> {t("nav.new")}</Link>}</div>
        </div>
        {orgId && <div className="alert info small">{t("mg.viewing_as_platform", { name: ov.org.name })}</div>}
        <div className="grid g4">
          <Kpi icon={<FolderKanban size={20} />} value={ov.projects.length} label={t("bur.projects")} series={monthly(ov.projects, (p) => p.created_at)} sub={t("dash.k.by_month")} />
          <Kpi icon={<Wallet size={20} />} value={amd(ov.pipeline_value)} label={t("bur.pipeline")} series={monthly(ov.projects, (p) => p.updated_at, 6, (p) => p.total || 0)} tone="sage" sub={t("dash.k.budget_hint")} />
          <Kpi icon={<Hourglass size={20} />} value={ov.status_counts.ready || 0} label={t("bur.waiting")} />
          <Kpi icon={<CheckCircle2 size={20} />} value={(ov.status_counts.approved || 0) + (ov.status_counts.ordered || 0)} label={t("bur.approved")} />
        </div>
        {ov.projects.length ? <ProjectsBoard items={ov.projects} onChanged={reload} /> : <Empty>{t("mg.no_projects")}</Empty>}
        <div className="grid g2" style={{ alignItems: "start" }}>
          {canManage ? <TeamCard orgId={orgId} /> : <div className="card pad col gap-6"><h3>{t("bur.team")}</h3>{ov.members.map((m) => <div key={m.email + m.role} className="small">{m.name} <span className="muted">{m.email}</span></div>)}</div>}
          <div className="col gap-16">
            {orgId || ownBureau ? <AiUsageCard canEdit={canManage} /> : null}
            <div className="card pad col gap-10">
              <h3>{t("bur.titleblock")}</h3>
              <p className="small muted">{t("bur.titleblock_lead")}</p>
              {["company", "tagline", "phone", "address", "email"].map((k) => (
                <div key={k} className="field"><label>{t(`bur.f.${k}`)}</label><input className="input" aria-label={t(`bur.f.${k}`)} value={tb[k] || ""} disabled={!canManage} onChange={(e) => setTb({ ...tb, [k]: e.target.value })} /></div>
              ))}
              {canManage && <button className="btn primary" onClick={save}><Save size={16} /> {t("common.save")}</button>}
            </div>
          </div>
        </div>
      </div>
    </ScopeCtx.Provider>
  );
}
