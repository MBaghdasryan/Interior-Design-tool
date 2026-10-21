import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { ArrowRight, Box, Building2, Calculator, Check, FileText, Layers, PackageSearch, ScanLine, ShieldCheck, Sofa, Store, Truck, Users } from "lucide-react";
import { api, type Scene } from "../lib/api";
import { amd } from "../lib/format";
import { useT } from "../i18n";
import BeforeAfter from "../components/BeforeAfter";
import { BrandLockup, LangSwitch } from "../components/AppShell";

interface Showcase { scene: Scene; title: string | null; total: number | null; items: number; rooms: number; suppliers: number }

const STEPS = [{ icon: ScanLine, k: "recognize" }, { icon: Layers, k: "layout" }, { icon: Sofa, k: "products" }, { icon: Calculator, k: "estimate" }, { icon: PackageSearch, k: "stock" }, { icon: Truck, k: "delivery" }];

export default function Landing() {
  const { t } = useT();
  const [sc, setSc] = useState<Showcase | null>(null);
  useEffect(() => { api<Showcase>("/public/showcase").then(setSc).catch(() => {}); }, []);
  return (
    <div style={{ background: "var(--bg)" }}>
      <nav className="landing-nav">
        <div className="brand" style={{ padding: 0 }}><BrandLockup size={34} tagline /></div>
        <div className="row gap-24 grow hide-sm" style={{ marginLeft: 24, fontWeight: 600, color: "var(--ink-2)" }}>
          <a href="#how">{t("landing.nav.how")}</a><a href="#products">{t("landing.nav.who")}</a><a href="#how">{t("landing.nav.docs")}</a><a href="#trust">{t("landing.nav.trust")}</a>
        </div>
        <LangSwitch compact />
        <Link to="/login" className="btn">{t("landing.signin")}</Link>
        <Link to="/login" className="btn primary">{t("landing.start")} <ArrowRight size={16} /></Link>
      </nav>

      <section style={{ padding: "0 40px" }} className="hero">
        <div className="card" style={{ overflow: "hidden" }}>
          {sc ? <BeforeAfter scene={sc.scene} height={560} quality="high" /> : <div className="skeleton" style={{ height: 560 }} />}
          <div style={{ padding: "28px 32px 30px" }}>
            <h1>{t("landing.h1")}</h1>
            <p className="muted mt-8" style={{ fontSize: 17 }}>{t("landing.lead")}</p>
            <p className="tiny muted mt-8">{t("landing.render_note")}</p>
            <div className="pipeline mt-24">
              {STEPS.map((s, i) => (
                <div key={s.k} className="row" style={{ flex: i < STEPS.length - 1 ? 1 : undefined }}>
                  <div className={`pipe-step ${i < 2 ? "done" : i === 2 ? "running" : ""}`}><div className="ic"><s.icon size={22} /></div><b>{t(`landing.step.${s.k}`)}</b></div>
                  {i < STEPS.length - 1 && <div className={`pipe-line ${i < 2 ? "done" : ""}`} />}
                </div>
              ))}
            </div>
            <div className="grid g4 mt-24">
              <div className="card flat kpi"><div className="ico"><Layers size={22} /></div><div><div className="v">{t("landing.kpi.rooms", { n: sc?.rooms ?? "—" })}</div><div className="muted small">{t("landing.kpi.rooms_sub")}</div></div></div>
              <div className="card flat kpi"><div className="ico"><Sofa size={22} /></div><div><div className="v">{t("landing.kpi.items", { n: sc?.items || "—" })}</div><div className="muted small">{t("landing.kpi.items_sub")}</div></div></div>
              <div className="card flat kpi"><div className="ico"><Store size={22} /></div><div><div className="v">{t("landing.kpi.suppliers", { n: sc?.suppliers || 8 })}</div><div className="muted small">{t("landing.kpi.suppliers_sub")}</div></div></div>
              <div className="card flat kpi"><div className="ico"><Calculator size={22} /></div><div><div className="v">{sc?.total ? `≈ ${amd(sc.total)}` : t("landing.kpi.estimate")}</div><div className="muted small">{t("landing.kpi.estimate_sub")}</div></div></div>
            </div>
          </div>
        </div>
      </section>

      <section id="how" style={{ padding: "56px 40px 10px" }}>
        <h2>{t("landing.how.h2")}</h2>
        <p className="muted mt-8">{t("landing.how.lead")}</p>
        <div className="grid g3 mt-24">
          {[ScanLine, Sofa, FileText, Box, ShieldCheck, Calculator].map((I, i) => (
            <div key={i} className="card feature"><div className="ico"><I size={22} /></div><h3>{t(`landing.f${i + 1}.h`)}</h3><p className="muted mt-8">{t(`landing.f${i + 1}.p`)}</p></div>
          ))}
        </div>
      </section>

      <section id="products" style={{ padding: "48px 40px" }}>
        <h2>{t("landing.who.h2")}</h2>
        <div className="grid g3 mt-24">
          {([[Building2, "Studio Pro", "studio"], [Store, "Store Partner", "partner"], [Users, "Client Viewer", "client"]] as const).map(([I, h, k]) => (
            <div key={k} className="card pad"><div className="row"><div className="kpi" style={{ padding: 0 }}><div className="ico"><I size={22} /></div></div><div><h3>{h}</h3><div className="muted small">{t(`landing.${k}.sub`)}</div></div></div>
              <div className="col gap-6 mt-16">{[1, 2, 3, 4].map((n) => <div key={n} className="row gap-6"><Check size={16} color="var(--sage-ink)" /> {t(`landing.${k}.l${n}`)}</div>)}</div></div>
          ))}
        </div>
      </section>

      <section id="trust" style={{ padding: "0 40px 60px" }}>
        <div className="alert info"><ShieldCheck size={20} /><div>{t("landing.trust")}</div></div>
        <div className="row mt-24"><Link to="/login" className="btn primary lg">{t("landing.try")} <ArrowRight size={18} /></Link></div>
      </section>
    </div>
  );
}
