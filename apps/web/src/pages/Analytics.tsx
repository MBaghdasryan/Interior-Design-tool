import { useEffect, useState } from "react";
import { BarChart3, Clock, Cpu, FolderKanban, Ruler, Users, Wallet } from "lucide-react";
import { api } from "../lib/api";
import { amd } from "../lib/format";
import { useT } from "../i18n";
import { Empty, Kpi, Loading } from "../components/ui";
import { Bars, ChartCard, Columns } from "../components/Charts";
import { useMe } from "../components/AppShell";

interface A {
  scope: "bureau" | "platform"; months: string[];
  projects: { total: number; by_month: number[]; by_status: Record<string, number>; accuracy: Record<string, number>; median_days_to_approval: number | null };
  estimates: { projects: number; average_amd: number | null; median_amd: number | null; per_m2_amd: number | null; by_group: Record<string, number>; top_suppliers: { name: string; amount_amd: number }[]; sourcing: { real: number; demo: number; concept: number } };
  orders: { count: number; amount_by_month: number[]; by_status: Record<string, number> };
  crm: { by_stage: Record<string, number>; by_source: { source: string; clients: number; won: number; lost: number }[] } | null;
  tasks: { done_by_month: number[]; open: number; overdue: number } | null;
  ai: { projects_with_ai: number; avg_usd: number | null; median_usd: number | null };
  platform?: { orgs: Record<string, number>; users: number; revenue: Record<string, number>; catalogue: { skus: number; priced: number; fresh_7d: number; external_records: number } };
}
const FUNNEL = ["draft", "intake", "recognized", "generating", "ready", "approved", "ordered"];

/** Analytics computed from the organisation's own records (mockup 19); the platform admin sees the whole platform. */
export default function Analytics() {
  const { t, lang } = useT();
  const { me } = useMe();
  const [months, setMonths] = useState(6);
  const [a, setA] = useState<A | null>(null);
  const [err, setErr] = useState("");
  useEffect(() => { setA(null); api<A>(`/analytics?months=${months}`).then(setA).catch((e) => setErr((e as Error).message)); }, [months]);
  if (err) return <div className="alert danger">{err}</div>;
  if (!a) return <Loading />;
  const mlab = a.months.map((k) => new Date(`${k}-01T00:00:00`).toLocaleDateString(lang === "en" ? "en-GB" : lang === "hy" ? "hy-AM" : "ru-RU", { month: "short" }));
  const tbl = (vals: number[], fmt: (n: number) => string = String): [string, string][] => a.months.map((k, i) => [k, fmt(vals[i])]);
  const pct = (n: number, d: number) => (d ? `${Math.round((n / d) * 100)}%` : "—");
  const groups = Object.entries(a.estimates.by_group).filter(([, v]) => v > 0).map(([k, v]) => ({ label: t(`enum.group.${k}`), value: v }));
  const src = a.estimates.sourcing;
  const goods = src.real + src.demo + src.concept;
  return (
    <div className="col gap-16">
      <div className="row between wrap gap-12">
        <div><h1>{t("an.title")}</h1><p className="muted" style={{ margin: 0 }}>{a.scope === "platform" ? t("an.lead_platform") : t("an.lead_bureau", { org: me?.memberships.find((x) => x.org_kind === "bureau")?.org_name || "" })}</p></div>
        <div className="seg" role="group" aria-label={t("an.period")}>{[3, 6, 12].map((n) => <button key={n} className={months === n ? "on" : ""} onClick={() => setMonths(n)}>{t("an.months", { n })}</button>)}</div>
      </div>
      <div className="grid g4">
        <Kpi icon={<FolderKanban size={20} />} value={a.projects.total} label={t("an.k.projects")} series={a.projects.by_month} />
        <Kpi icon={<Wallet size={20} />} value={a.estimates.median_amd ? amd(a.estimates.median_amd) : "—"} label={t("an.k.median_budget")} sub={t("an.k.median_hint", { n: a.estimates.projects })} />
        <Kpi icon={<Ruler size={20} />} value={a.estimates.per_m2_amd ? amd(a.estimates.per_m2_amd) : "—"} label={t("an.k.per_m2")} />
        <Kpi icon={<Clock size={20} />} value={a.projects.median_days_to_approval == null ? "—" : t("an.days", { n: a.projects.median_days_to_approval })} label={t("an.k.to_approval")} />
      </div>
      {!a.projects.total ? <Empty>{t("an.empty")}</Empty> : <>
        <div className="grid g2" style={{ alignItems: "start" }}>
          <ChartCard title={t("an.c.projects")} sub={t("an.c.projects_sub")} table={tbl(a.projects.by_month)}><Columns labels={mlab} values={a.projects.by_month} /></ChartCard>
          <ChartCard title={t("an.c.funnel")} sub={t("an.c.funnel_sub")} table={FUNNEL.map((s) => [t(`enum.project_status.${s}`), String(a.projects.by_status[s] || 0)])}>
            <Bars rows={FUNNEL.map((s) => ({ label: t(`enum.project_status.${s}`), value: a.projects.by_status[s] || 0 }))} /></ChartCard>
          <ChartCard title={t("an.c.groups")} sub={t("an.c.groups_sub")} table={groups.map((g) => [g.label, amd(g.value)])}>{groups.length ? <Bars rows={groups} fmt={(n) => amd(n)} /> : <div className="small muted">{t("an.no_estimates")}</div>}</ChartCard>
          <ChartCard title={t("an.c.suppliers")} sub={t("an.c.suppliers_sub")} table={a.estimates.top_suppliers.map((s) => [s.name, amd(s.amount_amd)])}>
            {a.estimates.top_suppliers.length ? <Bars rows={a.estimates.top_suppliers.map((s) => ({ label: s.name, value: s.amount_amd }))} fmt={(n) => amd(n)} /> : <div className="small muted">{t("an.no_estimates")}</div>}</ChartCard>
          <ChartCard title={t("an.c.orders")} sub={t("an.c.orders_sub", { n: a.orders.count })} table={tbl(a.orders.amount_by_month, (n) => amd(n))}>
            {a.orders.count ? <Columns labels={mlab} values={a.orders.amount_by_month} fmt={(n) => (n >= 1e6 ? `${(n / 1e6).toFixed(1)}M` : n >= 1e3 ? `${Math.round(n / 1e3)}k` : String(n))} /> : <div className="small muted">{t("an.no_orders")}</div>}</ChartCard>
          <ChartCard title={t("an.c.quality")} sub={t("an.c.quality_sub")} table={[[t("an.q.real"), String(src.real)], [t("an.q.demo"), String(src.demo)], [t("an.q.concept"), String(src.concept)],
            ...Object.entries(a.projects.accuracy).map(([k, v]) => [t(`enum.accuracy.${k}`).split(" · ")[0], String(v)] as [string, string])]}>
            <Bars rows={[{ label: t("an.q.real"), value: src.real }, { label: t("an.q.demo"), value: src.demo }, { label: t("an.q.concept"), value: src.concept }]} fmt={(n) => `${n} · ${pct(n, goods)}`} />
            <div className="divider" />
            <Bars rows={Object.entries(a.projects.accuracy).map(([k, v]) => ({ label: t(`enum.accuracy.${k}`).split(" · ")[0], value: v }))} />
          </ChartCard>
          {a.crm && <ChartCard title={t("an.c.crm")} sub={t("an.c.crm_sub")} table={a.crm.by_source.map((s) => [t(`crm.src.${s.source}`), `${s.clients} · ${pct(s.won, s.won + s.lost)}`])}>
            {a.crm.by_source.length ? <table className="table compact"><thead><tr><th>{t("crm.f.source")}</th><th className="right">{t("an.clients")}</th><th className="right">{t("an.won")}</th><th className="right">{t("crm.k.conversion")}</th></tr></thead>
              <tbody>{a.crm.by_source.map((s) => <tr key={s.source}><td className="small">{t(`crm.src.${s.source}`)}</td><td className="right">{s.clients}</td><td className="right">{s.won}</td><td className="right">{pct(s.won, s.won + s.lost)}</td></tr>)}</tbody></table>
              : <div className="small muted">{t("an.no_clients")}</div>}</ChartCard>}
          {a.tasks && <ChartCard title={t("an.c.tasks")} sub={t("an.c.tasks_sub", { open: a.tasks.open, overdue: a.tasks.overdue })} table={tbl(a.tasks.done_by_month)}>{a.tasks.done_by_month.some(Boolean) ? <Columns labels={mlab} values={a.tasks.done_by_month} /> : <div className="small muted">{t("an.no_tasks")}</div>}</ChartCard>}
        </div>
        <div className="grid g3">
          <Kpi icon={<Cpu size={20} />} value={a.ai.median_usd == null ? "—" : `$${a.ai.median_usd.toFixed(2)}`} label={t("an.k.ai")} sub={t("an.k.ai_hint", { n: a.ai.projects_with_ai })} />
          {a.platform && <><Kpi icon={<Users size={20} />} value={`${a.platform.orgs.bureau} / ${a.platform.orgs.supplier}`} label={t("an.k.orgs")} sub={t("an.k.users", { n: a.platform.users })} />
            <Kpi icon={<BarChart3 size={20} />} value={pct(a.platform.catalogue.fresh_7d, a.platform.catalogue.skus)} label={t("an.k.fresh")} sub={t("an.k.fresh_hint", { n: a.platform.catalogue.skus, p: a.platform.catalogue.priced })} /></>}
        </div>
        {a.platform && <ChartCard title={t("an.c.revenue")} sub={t("an.c.revenue_sub")} table={Object.entries(a.platform.revenue).map(([k, v]) => [t(`fin.stream.${k}`), amd(v)])}>
          <Bars rows={Object.entries(a.platform.revenue).map(([k, v]) => ({ label: t(`fin.stream.${k}`), value: v }))} fmt={(n) => amd(n)} /></ChartCard>}
      </>}
      <p className="tiny muted">{t("an.note")}</p>
    </div>
  );
}
