import { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { Building2, Save } from "lucide-react";
import { api, ApiError, type Project } from "../lib/api";
import { amd } from "../lib/format";
import { useT } from "../i18n";
import { AccuracyBadge, Empty, Loading, useToast } from "../components/ui";
import { projectLink } from "./Dashboard";
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
  useEffect(() => {
    setOv(null); setErr("");
    if (isPlatform && !orgId && !ownBureau) return;
    api<Ov>(withQs("/bureau/overview", qs)).then((o) => { setOv(o); setTb(o.org.settings.title_block || {}); }).catch((e: ApiError) => setErr(e.message));
  }, [qs, isPlatform, orgId, ownBureau]);
  const save = async () => { try { await api(withQs("/bureau/settings", qs), { method: "PUT", json: { title_block: tb } }); toast(t("bur.saved")); } catch (x) { toast((x as Error).message, true); } };
  const picker = isPlatform && <OrgPicker kind="bureau" value={orgId} onChange={(v) => setSp(v ? { org: v } : {})} />;
  if (isPlatform && !orgId && !ownBureau) return <div className="col gap-16"><h1><Building2 size={26} /> {t("nav.bureau")}</h1>{picker}<Empty>{t("mg.pick_bureau")}</Empty></div>;
  if (err) return <div className="col gap-16">{picker}<div className="alert danger">{err}</div></div>;
  if (!ov) return <div className="col gap-16">{picker}<Loading /></div>;
  return (
    <ScopeCtx.Provider value={{ qs }}>
      <div className="col gap-16">
        <div className="row between wrap gap-12"><div><h1><Building2 size={26} /> {ov.org.name}</h1><p className="muted">{t("bur.lead")}</p></div>{picker}</div>
        {orgId && <div className="alert info small">{t("mg.viewing_as_platform", { name: ov.org.name })}</div>}
        <div className="grid g4">
          <div className="card kpi"><div><div className="v">{ov.projects.length}</div><div className="muted small">{t("bur.projects")}</div></div></div>
          <div className="card kpi"><div><div className="v">{ov.status_counts.ready || 0}</div><div className="muted small">{t("bur.waiting")}</div></div></div>
          <div className="card kpi"><div><div className="v">{ov.status_counts.approved || 0}</div><div className="muted small">{t("bur.approved")}</div></div></div>
          <div className="card kpi"><div><div className="v">{amd(ov.pipeline_value)}</div><div className="muted small">{t("bur.pipeline")}</div></div></div>
        </div>
        {orgId || ownBureau ? <AiUsageCard canEdit={canManage} /> : null}
        <div className="grid g2" style={{ alignItems: "start" }}>
          <div className="col gap-16">
            {canManage ? <TeamCard orgId={orgId} /> : <div className="card pad col gap-6"><h3>{t("bur.team")}</h3>{ov.members.map((m) => <div key={m.email + m.role} className="small">{m.name} <span className="muted">{m.email}</span></div>)}</div>}
            <div className="card pad col gap-10">
              <h3>{t("bur.titleblock")}</h3>
              <p className="small muted">{t("bur.titleblock_lead")}</p>
              {["company", "tagline", "phone", "address", "email"].map((k) => (
                <div key={k} className="field"><label>{t(`bur.f.${k}`)}</label><input className="input" aria-label={t(`bur.f.${k}`)} value={tb[k] || ""} disabled={!canManage} onChange={(e) => setTb({ ...tb, [k]: e.target.value })} /></div>
              ))}
              {canManage && <button className="btn primary" onClick={save}><Save size={16} /> {t("common.save")}</button>}
            </div>
          </div>
          <div className="card pad col gap-6"><h3>{t("dash.projects")}</h3>{!ov.projects.length && <div className="small muted">{t("mg.no_projects")}</div>}
            {ov.projects.map((p) => <Link key={p.id} to={projectLink(p)} className="row between small" style={{ padding: "6px 0" }}><span>{p.title}</span><AccuracyBadge level={p.accuracy_level} /></Link>)}</div>
        </div>
      </div>
    </ScopeCtx.Provider>
  );
}
