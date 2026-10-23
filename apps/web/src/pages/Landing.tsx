import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { ArrowRight, Box, Menu, Building2, Calculator, Check, CheckCircle2, FileText, Image as ImageIcon, Layers, PackageSearch, ScanLine, Send, ShieldCheck, Sofa,
  Sparkles, Store, Truck, Users } from "lucide-react";
import { api, type Scene } from "../lib/api";
import { amd } from "../lib/format";
import { useT } from "../i18n";
import BeforeAfter from "../components/BeforeAfter";
import { BrandLockup, LangSwitch } from "../components/AppShell";
import { PlanCard, amdN, type PublicPricing } from "../components/Pricing";

interface Showcase { scene: Scene; title: string | null; total: number | null; items: number; rooms: number; suppliers: number }

const STEPS = [{ icon: ScanLine, k: "recognize" }, { icon: Layers, k: "layout" }, { icon: Sofa, k: "products" }, { icon: Calculator, k: "estimate" }, { icon: PackageSearch, k: "stock" }, { icon: Truck, k: "delivery" }];
const LEVELS = [{ icon: Box, k: "concept" }, { icon: ImageIcon, k: "verified" }, { icon: Truck, k: "production" }] as const;

export default function Landing() {
  const { t } = useT();
  const [sc, setSc] = useState<Showcase | null>(null);
  useEffect(() => { api<Showcase>("/public/showcase").then(setSc).catch(() => {}); }, []);
  const links = <>
    <a href="#how">{t("landing.nav.how")}</a><a href="#products">{t("landing.nav.designers")}</a><a href="#suppliers">{t("landing.nav.suppliers")}</a>
    <a href="#pricing">{t("landing.nav.pricing")}</a><a href="#trust">{t("landing.nav.trust")}</a>
  </>;
  return (
    <div style={{ background: "var(--bg)" }}>
      <nav className="landing-nav" aria-label={t("landing.nav.label")}>
        <div className="brand" style={{ padding: 0 }}><BrandLockup size={34} tagline /></div>
        <div className="land-links">{links}</div>
        <details className="land-more">
          <summary className="icon-btn" aria-label={t("nav.menu")}><Menu size={18} /></summary>
          <div className="land-more-pop card" onClick={(e) => (e.currentTarget.parentElement as HTMLDetailsElement).removeAttribute("open")}>{links}</div>
        </details>
        <LangSwitch compact />
        <Link to="/login" className="btn">{t("landing.signin")}</Link>
        <Link to="/register" className="btn primary">{t("landing.start")} <ArrowRight size={16} /></Link>
      </nav>

      <section className="hero land-hero">
        <div className="col gap-16">
          <span className="pill"><Sparkles size={14} /> {t("landing.pill")}</span>
          <h1>{t("landing.h1")}</h1>
          <p className="muted" style={{ fontSize: 18, margin: 0 }}>{t("landing.lead")}</p>
          <div className="row gap-12 wrap">
            <Link to="/register" className="btn primary lg"><Sparkles size={18} /> {t("landing.cta_free")} <ArrowRight size={18} /></Link>
            <a href="#how" className="btn outline-terra lg">{t("landing.cta_example")}</a>
          </div>
          <div className="row gap-16 wrap small">{[1, 2, 3, 4].map((n) => <span key={n} className="row gap-6"><CheckCircle2 size={16} color="var(--sage-ink)" /> {t(`landing.check${n}`)}</span>)}</div>
        </div>
        <div className="card" style={{ overflow: "hidden" }}>
          {sc ? <BeforeAfter scene={sc.scene} height={440} quality="high" /> : <div className="skeleton" style={{ height: 440 }} />}
          <p className="tiny muted" style={{ margin: 0, padding: "8px 14px" }}>{t("landing.render_note")}</p>
        </div>
      </section>

      <section className="land-sec">
        <div className="card levels">
          {LEVELS.map((l, i) => (
            <div key={l.k} className="row gap-12 level">
              <div className={`lvl-ico ${i === 1 ? "sage" : ""}`}><l.icon size={24} /></div>
              <div><h3>{t(`enum.accuracy.${l.k}`).split(" · ")[0]}</h3><p className="small muted" style={{ margin: 0 }}>{t(`landing.level.${l.k}`)}</p></div>
              {i < LEVELS.length - 1 && <ArrowRight className="hide-sm" size={22} color="var(--ink-3)" />}
            </div>))}
        </div>
      </section>

      <section id="how" className="land-sec">
        <h2>{t("landing.how.h2")}</h2>
        <p className="muted mt-8">{t("landing.how.lead")}</p>
        <div className="pipeline mt-24">
          {STEPS.map((s, i) => (
            <div key={s.k} className="row" style={{ flex: i < STEPS.length - 1 ? 1 : undefined }}>
              <div className={`pipe-step ${i < 2 ? "done" : i === 2 ? "running" : ""}`}><div className="ic"><s.icon size={22} /></div><b>{t(`landing.step.${s.k}`)}</b></div>
              {i < STEPS.length - 1 && <div className={`pipe-line ${i < 2 ? "done" : ""}`} />}
            </div>
          ))}
        </div>
        <div className="grid g4 mt-24">
          <div className="card flat kpi"><div className="ico"><Layers size={22} /></div><div><div className="v">{t("landing.kpi.rooms", { n: sc?.rooms ?? "—" })}</div><div className="small muted">{t("landing.kpi.rooms_sub")}</div></div></div>
          <div className="card flat kpi"><div className="ico"><Sofa size={22} /></div><div><div className="v">{t("landing.kpi.items", { n: sc?.items || "—" })}</div><div className="small muted">{t("landing.kpi.items_sub")}</div></div></div>
          <div className="card flat kpi"><div className="ico"><Store size={22} /></div><div><div className="v">{t("landing.kpi.suppliers", { n: sc?.suppliers || "—" })}</div><div className="small muted">{t("landing.kpi.suppliers_sub")}</div></div></div>
          <div className="card flat kpi"><div className="ico"><Calculator size={22} /></div><div><div className="v">{sc?.total ? `≈ ${amd(sc.total)}` : t("landing.kpi.estimate")}</div><div className="small muted">{t("landing.kpi.estimate_sub")}</div></div></div>
        </div>
        <div className="grid g3 mt-24">
          {[ScanLine, Sofa, FileText, Box, ShieldCheck, Calculator].map((I, i) => (
            <div key={i} className="card feature"><div className="ico"><I size={22} /></div><h3>{t(`landing.f${i + 1}.h`)}</h3><p className="muted mt-8">{t(`landing.f${i + 1}.p`)}</p></div>
          ))}
        </div>
      </section>

      <section id="products" className="land-sec">
        <h2>{t("landing.who.h2")}</h2>
        <div className="grid g3 mt-24">
          {([[Building2, "Studio Pro", "studio"], [Store, "Store Partner", "partner"], [Users, "Client Viewer", "client"]] as const).map(([I, h, k]) => (
            <div key={k} className="card pad"><div className="row"><div className="kpi" style={{ padding: 0 }}><div className="ico"><I size={22} /></div></div><div><h3>{h}</h3><div className="muted small">{t(`landing.${k}.sub`)}</div></div></div>
              <div className="col gap-6 mt-16">{[1, 2, 3, 4].map((n) => <div key={n} className="row gap-6"><Check size={16} color="var(--sage-ink)" /> {t(`landing.${k}.l${n}`)}</div>)}</div></div>
          ))}
        </div>
      </section>

      <PricingSection />
      <SupplierSection />

      <section id="trust" className="land-sec">
        <div className="alert info"><ShieldCheck size={20} /><div>{t("landing.trust")}</div></div>
        <div className="row mt-24"><Link to="/register" className="btn primary lg">{t("landing.try")} <ArrowRight size={18} /></Link></div>
      </section>

      <footer className="land-foot">
        <div className="col gap-8"><BrandLockup size={30} tagline /><p className="small" style={{ opacity: 0.75, margin: 0 }}>{t("landing.foot.tag")}</p></div>
        <div className="col gap-6"><b>{t("landing.foot.product")}</b><a href="#how">{t("landing.nav.how")}</a><a href="#pricing">{t("landing.nav.pricing")}</a><a href="#trust">{t("landing.nav.trust")}</a></div>
        <div className="col gap-6"><b>{t("landing.foot.designers")}</b><Link to="/register">{t("landing.foot.register")}</Link><Link to="/login">{t("landing.signin")}</Link></div>
        <div className="col gap-6"><b>{t("landing.foot.suppliers")}</b><a href="#suppliers">{t("landing.foot.apply")}</a><a href="#pricing">{t("landing.foot.terms")}</a></div>
        <div className="col gap-8" style={{ marginLeft: "auto" }}><LangSwitch compact /><span className="tiny" style={{ opacity: 0.7 }}>© 2026 Renovara</span></div>
      </footer>
    </div>
  );
}

function PricingSection() {
  const { t } = useT();
  const [pr, setPr] = useState<PublicPricing | null>(null);
  const [tab, setTab] = useState<"pros" | "suppliers" | "credits">("pros");
  const [interval, setInterval] = useState<"month" | "year">("month");
  useEffect(() => { api<PublicPricing>("/public/pricing").then(setPr).catch(() => {}); }, []);
  if (!pr) return null;
  const plans = tab === "pros" ? pr.bureau_plans : pr.supplier_plans;
  return (
    <section id="pricing" className="land-sec">
      <div className="row between wrap gap-12">
        <div><h2>{t("price.h2")}</h2><p className="muted mt-8">{t("price.lead")}</p></div>
        {tab !== "credits" && <div className="seg" role="group" aria-label={t("bill.interval")}>{(["month", "year"] as const).map((k) => <button key={k} className={interval === k ? "on" : ""} aria-pressed={interval === k} onClick={() => setInterval(k)}>{t(`bil.interval.${k}`)}</button>)}</div>}
      </div>
      <div className="tabs mt-16" role="tablist">{(["pros", "suppliers", "credits"] as const).map((k) => <button key={k} role="tab" aria-selected={tab === k} className={`tab ${tab === k ? "on" : ""}`} onClick={() => setTab(k)}>{t(`price.tab.${k}`)}</button>)}</div>
      {tab !== "credits" ? <div className="price-grid mt-16">
        {plans.map((p) => <PlanCard key={p.key} plan={p} interval={interval} highlight={p.key === "designer_pro" || p.key === "supplier_growth"}
          action={p.custom ? <a className="btn block" href="#suppliers">{t("price.contact")}</a>
            : p.audience === "supplier" || p.audience === "manufacturer" ? <a className="btn block primary" href="#suppliers">{t("price.apply")}</a>
              : <Link className={`btn block ${p.price_amd_month ? "primary" : ""}`} to="/register">{p.price_amd_month ? t("price.start") : t("price.start_free")}</Link>} />)}
      </div> : <div className="col gap-12 mt-16">
        <div className="price-grid">{pr.credit_packs.map((c) => <div key={c.key} className="card pad col gap-6"><h3>{t("bil.pack_n", { n: c.credits })}</h3><b style={{ fontSize: 24 }}>{amdN(c.price_amd)}</b>
          <span className="tiny muted">{t("bill.per_credit", { v: (c.price_amd / c.credits).toFixed(2) })} · {t("bill.valid", { n: c.validity_months ?? 12 })}</span></div>)}</div>
        <div className="card"><table className="table compact"><thead><tr><th>{t("price.op")}</th><th className="right">{t("price.credits")}</th></tr></thead>
          <tbody>{Object.entries(pr.credit_costs).map(([k, v]) => <tr key={k}><td>{t(`credit.op.${k}`)}</td><td className="right mono">{v}</td></tr>)}</tbody></table></div>
        <p className="tiny muted">{t("price.credits_note")}</p>
      </div>}
      <p className="tiny muted mt-16">{t("price.trial", { days: pr.trial.days, credits: pr.trial.credits, n: pr.trial.max_projects })} {t("price.vat_note")}</p>
    </section>
  );
}

const CATS = ["furniture", "lighting", "plumbing", "finishing", "doors", "appliances", "decor", "custom"];

function SupplierSection() {
  const { t, lang } = useT();
  const [f, setF] = useState({ company: "", contact_name: "", email: "", phone: "", website: "", city: "", kind: "store", sku_count: "", message: "", categories: [] as string[], consent: false, hp: "" });
  const [state, setState] = useState<"idle" | "busy" | "done" | "error">("idle");
  const [err, setErr] = useState("");
  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setState("busy");
    try {
      await api("/public/supplier-applications", { method: "POST", json: { ...f, sku_count: f.sku_count ? Number(f.sku_count) : null, locale: lang } });
      setState("done");
    } catch (x) { setErr((x as Error).message); setState("error"); }
  };
  const field = (k: "company" | "contact_name" | "email" | "phone" | "website" | "city", type = "text", required = false) => (
    <label className="field"><span>{t(`join.f.${k}`)}{required ? " *" : ""}</span><input className="input" type={type} required={required} value={f[k]} onChange={(e) => setF({ ...f, [k]: e.target.value })} /></label>);
  return (
    <section id="suppliers" className="land-sec">
      <div className="sup-grid">
        <div className="col gap-12">
          <span className="pill"><Store size={14} /> {t("landing.nav.suppliers")}</span>
          <h2>{t("join.h2")}</h2>
          <p className="muted" style={{ margin: 0 }}>{t("join.lead")}</p>
          <div className="col gap-8">{[1, 2, 3, 4, 5].map((n) => <div key={n} className="row gap-8"><CheckCircle2 size={18} color="var(--sage-ink)" /> {t(`join.b.${n}`)}</div>)}</div>
          <ol className="col gap-6 small muted" style={{ paddingLeft: 18, margin: 0 }}>{[1, 2, 3, 4].map((n) => <li key={n}>{t(`join.step.${n}`)}</li>)}</ol>
        </div>
        <div className="card pad">
          {state === "done" ? <div className="col gap-8" role="status"><CheckCircle2 size={28} color="var(--sage-ink)" /><h3>{t("join.done_h")}</h3><p className="muted" style={{ margin: 0 }}>{t("join.done_p")}</p></div> : (
            <form className="col gap-10" onSubmit={submit} aria-label={t("join.form")}>
              <h3>{t("join.form")}</h3>
              <div className="grid g2">{field("company", "text", true)}{field("contact_name", "text", true)}{field("email", "email", true)}{field("phone", "tel")}{field("website", "url")}{field("city")}
                <label className="field"><span>{t("join.f.kind")}</span><select className="select input" value={f.kind} onChange={(e) => setF({ ...f, kind: e.target.value })}>{["store", "manufacturer", "installer"].map((k) => <option key={k} value={k}>{t(`sob.kind.${k}`)}</option>)}</select></label>
                <label className="field"><span>{t("join.f.sku_count")}</span><input className="input" inputMode="numeric" value={f.sku_count} onChange={(e) => setF({ ...f, sku_count: e.target.value.replace(/\D/g, "") })} /></label></div>
              <fieldset className="col gap-4" style={{ border: 0, padding: 0, margin: 0 }}><legend className="small muted">{t("join.f.categories")}</legend>
                <div className="row gap-4 wrap">{CATS.map((c) => { const on = f.categories.includes(c); return <button key={c} type="button" className={`chip ${on ? "on" : ""}`} aria-pressed={on} onClick={() => setF({ ...f, categories: on ? f.categories.filter((x) => x !== c) : [...f.categories, c] })}>{t(`enum.group.${c}`)}</button>; })}</div></fieldset>
              <label className="field"><span>{t("join.f.message")}</span><textarea className="input" rows={3} value={f.message} onChange={(e) => setF({ ...f, message: e.target.value })} /></label>
              <input type="text" name="website2" tabIndex={-1} autoComplete="off" aria-hidden="true" style={{ position: "absolute", left: -9999 }} value={f.hp} onChange={(e) => setF({ ...f, hp: e.target.value })} />
              <label className="check small"><input type="checkbox" required checked={f.consent} onChange={(e) => setF({ ...f, consent: e.target.checked })} /> {t("join.consent")}</label>
              {state === "error" && <div className="alert danger small" role="alert">{err}</div>}
              <button className="btn primary" disabled={state === "busy"}><Send size={16} /> {t("join.submit")}</button>
            </form>)}
        </div>
      </div>
    </section>
  );
}
