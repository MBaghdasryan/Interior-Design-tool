import { useState, type ReactNode } from "react";
import { Table2 } from "lucide-react";
import { useT } from "../i18n";

/** Single-series charts (one hue, value labels, hover tooltip, table view) — no categorical palette needed. */
export function ChartCard({ title, sub, table, children }: { title: string; sub?: string; table: [string, string][]; children: ReactNode }) {
  const { t } = useT();
  const [asTable, setAsTable] = useState(false);
  return (
    <section className="card pad col gap-8 chart-card" aria-label={title}>
      <div className="row between"><div><b>{title}</b>{sub && <div className="tiny muted">{sub}</div>}</div>
        <button className={`icon-btn ${asTable ? "on" : ""}`} aria-pressed={asTable} aria-label={t("an.table")} title={t("an.table")} onClick={() => setAsTable(!asTable)}><Table2 size={15} /></button></div>
      {asTable ? <table className="table compact"><tbody>{table.map(([k, v]) => <tr key={k}><td className="small">{k}</td><td className="right mono small">{v}</td></tr>)}</tbody></table> : children}
    </section>
  );
}

export function Columns({ labels, values, fmt = String, height = 160 }: { labels: string[]; values: number[]; fmt?: (n: number) => string; height?: number }) {
  const max = Math.max(1, ...values);
  const [hover, setHover] = useState<number | null>(null);
  return (
    <div className="cols" style={{ height }} role="img" aria-label={labels.map((l, i) => `${l}: ${fmt(values[i])}`).join(", ")}>
      {values.map((v, i) => (
        <div key={labels[i]} className="col-slot" onMouseEnter={() => setHover(i)} onMouseLeave={() => setHover(null)}>
          {hover === i && <div className="tip">{labels[i]} · <b>{fmt(v)}</b></div>}
          <span className="val tiny">{v ? fmt(v) : ""}</span>
          <i style={{ height: `${v ? Math.max(3, (v / max) * 100) : 0}%` }} />
          <span className="lab tiny muted">{labels[i]}</span>
        </div>))}
    </div>
  );
}

export function Bars({ rows, fmt = String }: { rows: { label: string; value: number }[]; fmt?: (n: number) => string }) {
  const max = Math.max(1, ...rows.map((r) => r.value));
  const [hover, setHover] = useState<string | null>(null);
  return (
    <div className="hbars">
      {rows.map((r) => (
        <div key={r.label} className="hbar" onMouseEnter={() => setHover(r.label)} onMouseLeave={() => setHover(null)}>
          <span className="small lab">{r.label}</span>
          <span className="track">{hover === r.label && <span className="tip">{r.label} · <b>{fmt(r.value)}</b></span>}<i style={{ width: `${r.value ? Math.max(1.5, (r.value / max) * 100) : 0}%` }} /></span>
          <span className="small mono val">{fmt(r.value)}</span>
        </div>))}
    </div>
  );
}
