import { useCallback, useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { ChevronDown, ChevronRight, ClipboardList, Factory, Search, Truck, Wallet, Wrench } from "lucide-react";
import { api } from "../lib/api";
import { amd, dt } from "../lib/format";
import { useT } from "../i18n";
import { Badge, Empty, Kpi, Loading } from "../components/ui";

interface Stage { key: string; state: "done" | "current" | "planned"; at: string | null }
interface Order { id: string; number: string; project_id: string; project_title: string; city: string; supplier_id: string | null; supplier_name: string; status: string;
  payment_status: string; amount_amd: number; positions: number; created_at: string; stages: Stage[]; history: { at: string; from: string; to: string; by: string; note?: string }[];
  items: { name: string; qty: number; unit: string }[] }
interface Reg { items: Order[]; kpi: { active: number; in_production: number; delivering: number; installing: number; closed: number; amount_amd: number; series: { active: number[]; all: number[] } };
  suppliers: { key: string; name: string; count: number; amount_amd: number }[] }
const STATUS_TONE: Record<string, string> = { requested: "warn", confirmed: "info", in_production: "info", delivering: "info", installing: "info", closed: "sage", cancelled: "", disputed: "danger", refunded: "" };
const PAY_TONE: Record<string, string> = { paid: "sage", pending: "warn", none: "", refunded: "" };

/** All orders of the organisation across projects (mockup 32): KPIs, grouped by supplier, stage chain, order timeline. */
export default function Orders() {
  const { t } = useT();
  const [d, setD] = useState<Reg | null>(null);
  const [status, setStatus] = useState("");
  const [supplier, setSupplier] = useState("");
  const [days, setDays] = useState(0);
  const [q, setQ] = useState("");
  const [sel, setSel] = useState<string | null>(null);
  const [closed, setClosed] = useState<Set<string>>(new Set());
  const load = useCallback(() => {
    const p = new URLSearchParams();
    if (status) p.set("status", status);
    if (supplier) p.set("supplier_id", supplier);
    if (days) p.set("days", String(days));
    if (q) p.set("q", q);
    api<Reg>(`/orders?${p}`).then(setD).catch(() => setD({ items: [], kpi: { active: 0, in_production: 0, delivering: 0, installing: 0, closed: 0, amount_amd: 0, series: { active: [], all: [] } }, suppliers: [] }));
  }, [status, supplier, days, q]);
  useEffect(() => { const tm = setTimeout(load, 200); return () => clearTimeout(tm); }, [load]);
  const groups = useMemo(() => {
    const g = new Map<string, Order[]>();
    for (const o of d?.items || []) { const k = o.supplier_id || o.supplier_name; g.set(k, [...(g.get(k) || []), o]); }
    return [...g.entries()];
  }, [d]);
  if (!d) return <Loading />;
  const cur = d.items.find((o) => o.id === sel) || d.items[0];
  return (
    <div className="col gap-16">
      <div><h1>{t("ord.title")}</h1><p className="muted" style={{ margin: 0 }}>{t("ord.lead")}</p></div>
      <div className="grid g5">
        <Kpi icon={<ClipboardList size={20} />} value={d.kpi.active} label={t("ord.k.active")} series={d.kpi.series.active} />
        <Kpi icon={<Factory size={20} />} value={d.kpi.in_production} label={t("ord.k.production")} />
        <Kpi icon={<Truck size={20} />} value={d.kpi.delivering} label={t("ord.k.delivering")} />
        <Kpi icon={<Wrench size={20} />} value={d.kpi.installing} label={t("ord.k.installing")} />
        <Kpi icon={<Wallet size={20} />} value={amd(d.kpi.amount_amd)} label={t("ord.k.amount")} series={d.kpi.series.all} tone="sage" />
      </div>
      <div className="dash-grid">
        <section className="card col" aria-labelledby="ord-h">
          <div className="row between wrap gap-8" style={{ padding: 14 }}>
            <h3 id="ord-h">{t("ord.by_supplier", { n: d.items.length })}</h3>
            <div className="row gap-6 wrap">
              <select className="select input" aria-label={t("common.status")} value={status} onChange={(e) => setStatus(e.target.value)}>
                <option value="">{t("ord.all_statuses")}</option><option value="active">{t("ord.active_only")}</option>
                {["requested", "confirmed", "in_production", "delivering", "installing", "closed", "disputed", "cancelled"].map((s) => <option key={s} value={s}>{t(`enum.order.${s}`)}</option>)}</select>
              <select className="select input" aria-label={t("common.supplier")} value={supplier} onChange={(e) => setSupplier(e.target.value)}>
                <option value="">{t("ord.all_suppliers")}</option>{d.suppliers.map((s) => <option key={s.key} value={s.key}>{s.name}</option>)}</select>
              <select className="select input" aria-label={t("ord.period")} value={days} onChange={(e) => setDays(Number(e.target.value))}>
                {[0, 7, 30, 90, 365].map((n) => <option key={n} value={n}>{n ? t("ord.last_days", { n }) : t("ord.all_time")}</option>)}</select>
              <label className="row gap-4 input" style={{ height: 38 }}><Search size={15} /><input aria-label={t("common.search")} placeholder={t("ord.search")} value={q} onChange={(e) => setQ(e.target.value)} style={{ border: 0, outline: 0, background: "transparent" }} /></label>
            </div>
          </div>
          {!d.items.length ? <Empty>{t("ord.empty")}</Empty> : <div style={{ overflow: "auto" }}>
            <table className="table compact ord-table">
              <thead><tr><th>{t("ord.col.no")}</th><th>{t("ord.col.project")}</th><th className="right">{t("ord.col.items")}</th><th className="right">{t("ord.col.amount")}</th><th>{t("ord.col.payment")}</th>
                {["confirmed", "production", "delivery", "installation", "closed"].map((k) => <th key={k} className="center">{t(`ord.stage.${k}`)}</th>)}<th>{t("common.status")}</th></tr></thead>
              {groups.map(([k, list]) => {
                const open = !closed.has(k);
                return <tbody key={k}>
                  <tr className="grp" onClick={() => { const s = new Set(closed); if (open) s.add(k); else s.delete(k); setClosed(s); }}>
                    <td colSpan={5}><b className="row gap-6">{open ? <ChevronDown size={15} /> : <ChevronRight size={15} />} {list[0].supplier_name} <span className="muted">({list.length})</span></b></td>
                    <td colSpan={5} /><td className="right mono"><b>{amd(list.reduce((s, o) => s + o.amount_amd, 0))}</b></td></tr>
                  {open && list.map((o) => <tr key={o.id} className={cur?.id === o.id ? "on" : ""} onClick={() => setSel(o.id)} style={{ cursor: "pointer" }}>
                    <td><button className="linklike mono" onClick={() => setSel(o.id)}>#{o.number}</button></td>
                    <td className="small"><Link to={`/app/p/${o.project_id}/procurement`} onClick={(e) => e.stopPropagation()}>{o.project_title}</Link></td>
                    <td className="right small">{o.positions}</td><td className="right mono small">{amd(o.amount_amd)}</td>
                    <td><Badge tone={PAY_TONE[o.payment_status]}>{t(`ord.pay.${o.payment_status}`)}</Badge></td>
                    {o.stages.map((s) => <td key={s.key} className="center"><span className={`stg ${s.state}`} title={s.at ? dt(s.at) : t(`ord.st.${s.state}`)} /></td>)}
                    <td><Badge tone={STATUS_TONE[o.status]}>{t(`enum.order.${o.status}`)}</Badge></td>
                  </tr>)}
                </tbody>;
              })}
            </table></div>}
        </section>
        <aside className="card pad col gap-10" aria-labelledby="otl-h">
          {cur ? <>
            <div className="row between"><h3 id="otl-h">{t("ord.timeline", { n: cur.number })}</h3><Badge tone={STATUS_TONE[cur.status]}>{t(`enum.order.${cur.status}`)}</Badge></div>
            <div className="small muted">{cur.project_title}{cur.city ? ` · ${cur.city}` : ""} · {t("ord.positions", { n: cur.positions })} · {amd(cur.amount_amd)}</div>
            <ol className="stages">
              <li className="done"><span className="dot2">✓</span><div><b className="small">{t("ord.created")}</b><div className="tiny muted">{dt(cur.created_at)}</div></div></li>
              {cur.stages.map((s) => <li key={s.key} className={s.state === "done" ? "done" : s.state === "current" ? "now" : ""}><span className="dot2">{s.state === "done" ? "✓" : ""}</span>
                <div><b className="small">{t(`ord.stage.${s.key}`)}</b><div className="tiny muted">{s.at ? dt(s.at) : t(`ord.st.${s.state}`)}</div></div></li>)}
            </ol>
            <b className="small">{t("ord.items")}</b>
            {cur.items.slice(0, 6).map((it, i) => <div key={i} className="row between small"><span>{it.name}</span><span className="muted">× {it.qty}</span></div>)}
            <Link className="btn sm" to={`/app/p/${cur.project_id}/procurement`}>{t("ord.open_project")}</Link>
          </> : <div className="small muted">{t("ord.pick")}</div>}
        </aside>
      </div>
      <p className="tiny muted">{t("ord.note")}</p>
    </div>
  );
}
