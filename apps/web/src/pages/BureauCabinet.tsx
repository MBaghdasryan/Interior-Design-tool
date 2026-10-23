import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { Building2, Save, Users } from "lucide-react";
import { api, type Project } from "../lib/api";
import { amd, roleName } from "../lib/format";
import { useT } from "../i18n";
import { AccuracyBadge, Badge, Loading, useToast } from "../components/ui";
import { projectLink } from "./Dashboard";
import AiUsageCard from "../components/AiUsageCard";
import { useMe } from "../components/AppShell";

interface Ov { org: { name: string; settings: { title_block?: Record<string, string> } }; members: { name: string; email: string; role: string }[]; projects: Project[]; status_counts: Record<string, number>; pipeline_value: number }

export default function BureauCabinet() {
  const { t } = useT();
  const toast = useToast();
  const [ov, setOv] = useState<Ov | null>(null);
  const [tb, setTb] = useState<Record<string, string>>({});
  useEffect(() => { api<Ov>("/bureau/overview").then((o) => { setOv(o); setTb(o.org.settings.title_block || {}); }).catch((e) => toast(e.message, true)); }, [toast]);
  const save = async () => { try { await api("/bureau/settings", { method: "PUT", json: { title_block: tb } }); toast(t("bur.saved")); } catch (x) { toast((x as Error).message, true); } };
  if (!ov) return <Loading />;
  return (
    <div className="col gap-16">
      <div><h1><Building2 size={26} /> {ov.org.name}</h1><p className="muted">{t("bur.lead")}</p></div>
      <div className="grid g4">
        <div className="card kpi"><div><div className="v">{ov.projects.length}</div><div className="muted small">{t("bur.projects")}</div></div></div>
        <div className="card kpi"><div><div className="v">{ov.status_counts.ready || 0}</div><div className="muted small">{t("bur.waiting")}</div></div></div>
        <div className="card kpi"><div><div className="v">{ov.status_counts.approved || 0}</div><div className="muted small">{t("bur.approved")}</div></div></div>
        <div className="card kpi"><div><div className="v">{amd(ov.pipeline_value)}</div><div className="muted small">{t("bur.pipeline")}</div></div></div>
      </div>
      <AiUsageCardForRole />
      <div className="grid g2" style={{ alignItems: "start" }}>
        <div className="card pad col gap-10">
          <h3>{t("bur.titleblock")}</h3>
          <p className="small muted">{t("bur.titleblock_lead")}</p>
          {["company", "tagline", "phone", "address", "email"].map((k) => (
            <div key={k} className="field"><label>{t(`bur.f.${k}`)}</label><input className="input" aria-label={t(`bur.f.${k}`)} value={tb[k] || ""} onChange={(e) => setTb({ ...tb, [k]: e.target.value })} /></div>
          ))}
          <button className="btn primary" onClick={save}><Save size={16} /> {t("common.save")}</button>
        </div>
        <div className="col gap-16">
          <div className="card pad col gap-6"><h3><Users size={18} /> {t("bur.team")}</h3>{ov.members.map((m) => <div key={m.email + m.role} className="row between small"><span><b>{m.name}</b> <span className="muted">{m.email}</span></span><Badge>{roleName(m.role)}</Badge></div>)}</div>
          <div className="card pad col gap-6"><h3>{t("dash.projects")}</h3>{ov.projects.map((p) => <Link key={p.id} to={projectLink(p)} className="row between small" style={{ padding: "6px 0" }}><span>{p.title}</span><AccuracyBadge level={p.accuracy_level} /></Link>)}</div>
        </div>
      </div>
    </div>
  );
}

function AiUsageCardForRole() {
  const { me } = useMe();
  const { t } = useT();
  // the card is per bureau organisation; platform staff see all organisations under Platform → AI providers
  if (!me?.memberships.some((x) => x.org_kind === "bureau")) return <div className="alert info small">{t("aicost.platform_hint")}</div>;
  return <AiUsageCard canEdit={!!me?.roles.includes("bureau_admin") || !!me?.roles.includes("platform_admin")} />;
}
