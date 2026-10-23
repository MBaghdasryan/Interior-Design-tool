import { useEffect, useState } from "react";
import { Copy, Link2, MousePointerClick, Send, UserPlus, Wallet } from "lucide-react";
import { api } from "../lib/api";
import { amd, dt } from "../lib/format";
import { useT } from "../i18n";
import { Badge, Empty, Kpi, Loading, useToast } from "../components/ui";
import { ChartCard, Columns } from "../components/Charts";

interface P { code: string; link: string; months: string[]; clicks_by_month: number[]; funnel: { clicks: number; signups: number; projects: number; payments: number };
  referred: { org: string; kind: string; joined: string | null; projects: number; paid_amd: number; stage: string }[]; paid_amd: number; reward_pct: number; reward_amd: number | null }

/** Partner programme (mockup 23): personal link, funnel clicks → registrations → projects → payments; reward only once the platform publishes a rate. */
export default function Partner() {
  const { t, lang } = useT();
  const toast = useToast();
  const [d, setD] = useState<P | null>(null);
  useEffect(() => { api<P>("/partner").then(setD).catch((e) => toast((e as Error).message, true)); }, [toast]);
  if (!d) return <Loading />;
  const f = d.funnel;
  const pct = (a: number, b: number) => (b ? `${Math.round((a / b) * 1000) / 10}%` : "—");
  const share = encodeURIComponent(d.link);
  const mlab = d.months.map((k) => new Date(`${k}-01T00:00:00`).toLocaleDateString(lang === "en" ? "en-GB" : lang === "hy" ? "hy-AM" : "ru-RU", { month: "short" }));
  const steps: [string, number, string][] = [["clicks", f.clicks, "100%"], ["signups", f.signups, pct(f.signups, f.clicks)], ["projects", f.projects, pct(f.projects, f.signups)], ["payments", f.payments, pct(f.payments, f.projects)]];
  return (
    <div className="col gap-16">
      <div><h1>{t("prt.title")}</h1><p className="muted" style={{ margin: 0 }}>{t("prt.lead")}</p></div>
      <div className="grid g4">
        <Kpi icon={<MousePointerClick size={20} />} value={f.clicks} label={t("prt.k.clicks")} series={d.clicks_by_month} />
        <Kpi icon={<UserPlus size={20} />} value={f.signups} label={t("prt.k.signups")} />
        <Kpi icon={<Wallet size={20} />} value={amd(d.paid_amd)} label={t("prt.k.paid")} />
        <Kpi icon={<Wallet size={20} />} value={d.reward_amd == null ? "—" : amd(d.reward_amd)} label={t("prt.k.reward")} sub={d.reward_pct ? t("prt.rate", { n: d.reward_pct }) : t("prt.no_rate")} />
      </div>
      <div className="grid g2" style={{ alignItems: "start" }}>
        <section className="card pad col gap-10" aria-labelledby="prt-link">
          <h3 id="prt-link" className="row gap-6"><Link2 size={18} /> {t("prt.link")}</h3>
          <p className="small muted" style={{ margin: 0 }}>{t("prt.link_hint")}</p>
          <div className="row gap-6"><input className="input grow mono" readOnly value={d.link} aria-label={t("prt.link")} onFocus={(e) => e.target.select()} />
            <button className="btn primary" onClick={() => { navigator.clipboard?.writeText(d.link); toast(t("common.link_copied")); }}><Copy size={15} /> {t("prt.copy")}</button></div>
          <div className="row gap-6 wrap">
            <a className="btn sm" target="_blank" rel="noreferrer" href={`https://t.me/share/url?url=${share}`}><Send size={14} /> Telegram</a>
            <a className="btn sm" target="_blank" rel="noreferrer" href={`https://wa.me/?text=${share}`}>WhatsApp</a>
            <a className="btn sm" target="_blank" rel="noreferrer" href={`https://www.facebook.com/sharer/sharer.php?u=${share}`}>Facebook</a>
          </div>
          <div className="tiny muted">{t("prt.privacy")}</div>
        </section>
        <section className="card pad col gap-10" aria-labelledby="prt-funnel">
          <h3 id="prt-funnel">{t("prt.funnel")}</h3>
          <div className="funnel">{steps.map(([k, n, p]) => <div key={k} className="fstep"><b className="mono">{n}</b><span className="small">{t(`prt.f.${k}`)}</span><span className="tiny muted">{p}</span></div>)}</div>
        </section>
      </div>
      <ChartCard title={t("prt.clicks_chart")} table={d.months.map((k, i) => [k, String(d.clicks_by_month[i])])}>{d.clicks_by_month.some(Boolean) ? <Columns labels={mlab} values={d.clicks_by_month} /> : <div className="small muted">{t("prt.no_clicks")}</div>}</ChartCard>
      <section className="card col" aria-labelledby="prt-ref">
        <h3 id="prt-ref" style={{ padding: "14px 14px 0" }}>{t("prt.referred")}</h3>
        {!d.referred.length ? <Empty>{t("prt.no_referred")}</Empty> : <table className="table compact"><thead><tr><th>{t("mg.col.org")}</th><th>{t("prt.col.joined")}</th><th className="right">{t("mg.col.projects")}</th><th className="right">{t("prt.col.paid")}</th><th>{t("prt.col.stage")}</th></tr></thead>
          <tbody>{d.referred.map((r) => <tr key={r.org + r.joined}><td className="small"><b>{r.org}</b> <span className="muted">· {t(`mg.kind.${r.kind}`)}</span></td><td className="tiny muted">{dt(r.joined)}</td><td className="right">{r.projects}</td><td className="right mono small">{amd(r.paid_amd)}</td>
            <td><Badge tone={r.stage === "payment" ? "sage" : r.stage === "project" ? "info" : ""}>{t(`prt.f.${r.stage === "payment" ? "payments" : r.stage === "project" ? "projects" : "signups"}`)}</Badge></td></tr>)}</tbody></table>}
      </section>
      <p className="tiny muted">{t("prt.note")}</p>
    </div>
  );
}
