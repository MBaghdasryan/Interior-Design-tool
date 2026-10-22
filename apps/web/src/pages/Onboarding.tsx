import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { ArrowLeft, ArrowRight, Building2, FolderPlus, UserRound } from "lucide-react";
import { api, type Me } from "../lib/api";
import { roleName } from "../lib/format";
import { useT } from "../i18n";
import { BRAND, useMe } from "../components/AppShell";
import { useToast } from "../components/ui";

const SELF_ROLES: Record<string, string[]> = { bureau: ["bureau_admin", "designer"], supplier: ["supplier_admin", "supplier_catalog", "manufacturer"] };

/** Three steps after sign-up: organisation (album title block) → own role → first project. */
export default function Onboarding() {
  const { t } = useT();
  const { me, cfg, reload } = useMe();
  const nav = useNavigate();
  const toast = useToast();
  const ms = me?.memberships.find((x) => x.org_kind === "bureau" || x.org_kind === "supplier");
  const kind = ms?.org_kind || "bureau";
  const [step, setStep] = useState(1);
  const [org, setOrg] = useState({ org_name: ms?.org_name || "", city: "", phone: "", contact_email: me?.email || "" });
  const [role, setRole] = useState(ms?.role || SELF_ROLES[kind][0]);
  const save = async (body: Record<string, unknown>) => {
    try { await api<Me>("/auth/onboarding", { method: "POST", json: body }); return true; } catch (x) { toast((x as Error).message, true); return false; }
  };
  const finish = async (to: string) => { if (await save({ done: true })) { await reload(); nav(to); } };
  const steps = [{ icon: Building2, label: t("onb.org") }, { icon: UserRound, label: t("onb.role") }, { icon: FolderPlus, label: t("onb.first") }];
  return (
    <div className="col gap-16" style={{ maxWidth: 640, margin: "0 auto" }}>
      <div><h1>{t("onb.title", { brand: cfg?.brand_name || BRAND })}</h1><p className="muted mt-8">{t("onb.step", { n: step })}</p></div>
      <div className="row gap-6">{steps.map((s, i) => (
        <div key={i} className={`chip ${step === i + 1 ? "on" : ""}`} aria-current={step === i + 1 ? "step" : undefined}><s.icon size={15} /> {s.label}</div>
      ))}</div>
      <div className="card pad col gap-12">
        {step === 1 && <>
          <p className="small muted">{t("onb.org_hint")}</p>
          <div className="field"><label htmlFor="o-name">{t("reg.org_name")}</label><input id="o-name" className="input" value={org.org_name} onChange={(e) => setOrg({ ...org, org_name: e.target.value })} /></div>
          <div className="grid g2">
            <div className="field"><label htmlFor="o-city">{t("onb.city")}</label><input id="o-city" className="input" value={org.city} onChange={(e) => setOrg({ ...org, city: e.target.value })} /></div>
            <div className="field"><label htmlFor="o-phone">{t("onb.phone")}</label><input id="o-phone" className="input" value={org.phone} onChange={(e) => setOrg({ ...org, phone: e.target.value })} /></div>
          </div>
          <div className="field"><label htmlFor="o-mail">{t("onb.contact_email")}</label><input id="o-mail" className="input" type="email" value={org.contact_email} onChange={(e) => setOrg({ ...org, contact_email: e.target.value })} /></div>
          <div className="row between"><button className="btn ghost" onClick={() => finish("/app")}>{t("onb.skip")}</button>
            <button className="btn primary" onClick={async () => { if (await save(org)) setStep(2); }}>{t("onb.next")} <ArrowRight size={16} /></button></div>
        </>}
        {step === 2 && <>
          <p className="small muted">{t("onb.role_hint")}</p>
          <div className="row gap-6 wrap">{SELF_ROLES[kind].map((r) => <button key={r} className={`chip ${role === r ? "on" : ""}`} aria-pressed={role === r} onClick={() => setRole(r)}>{roleName(r)}</button>)}</div>
          <div className="row between"><button className="btn ghost" onClick={() => setStep(1)}><ArrowLeft size={16} /> {t("onb.back")}</button>
            <button className="btn primary" onClick={async () => { if (await save({ role })) setStep(3); }}>{t("onb.next")} <ArrowRight size={16} /></button></div>
        </>}
        {step === 3 && <>
          <p>{kind === "supplier" ? t("onb.first_supplier") : t("onb.first_hint")}</p>
          <div className="row between"><button className="btn ghost" onClick={() => setStep(2)}><ArrowLeft size={16} /> {t("onb.back")}</button>
            {kind === "supplier"
              ? <button className="btn primary" onClick={() => finish("/app/supplier")}>{t("onb.open_catalog")} <ArrowRight size={16} /></button>
              : <button className="btn primary" onClick={() => finish("/app/new")}>{t("onb.start_project")} <ArrowRight size={16} /></button>}</div>
        </>}
      </div>
    </div>
  );
}
