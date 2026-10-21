import { Fragment, useState } from "react";
import { ExternalLink, FileSpreadsheet, RefreshCw } from "lucide-react";
import type { Estimate } from "../lib/api";
import { amd, catName, dt, GROUP_COLORS, lineName, pct } from "../lib/format";
import { tOr, useT } from "../i18n";
import { PriceStatus } from "./ui";

type Notice = { code: string; params: Record<string, unknown> };
export function Notices({ est }: { est: Estimate & { notices?: Notice[] } }) {
  const { lang } = useT();
  const list = est.notices?.length ? est.notices.map((n, i) => tOr(`notice.${n.code}`, est.disclaimers[i] || n.code, n.params, lang)) : est.disclaimers;
  return <div className="col gap-6">{list.map((d) => <div key={d} className="alert info small">{d}</div>)}</div>;
}

export function EstimateSummary({ est }: { est: Estimate }) {
  const { t } = useT();
  return (
    <div className="col gap-6">
      {est.sections.filter((s) => s.total > 0 || s.quote_required).map((s) => (
        <div key={s.group} className="legend-row"><i className="dot" style={{ background: GROUP_COLORS[s.group] || "#999", width: 10, height: 10, borderRadius: 3 }} />
          <span>{t(`enum.group.${s.group}`)}{s.quote_required ? <span className="tiny muted"> · {t("estimate.n_on_request", { n: s.quote_required })}</span> : null}</span><b className="mono right">{amd(s.total)}</b><span className="muted right mono">{pct(s.share)}</span></div>
      ))}
      <div className="progress mt-8" style={{ height: 10, display: "flex" }}>{est.sections.map((s) => <i key={s.group} style={{ width: `${s.share * 100}%`, background: GROUP_COLORS[s.group] || "#999", borderRadius: 0 }} />)}</div>
    </div>
  );
}

export default function EstimateView({ est, onRecheck, xlsxUrl }: { est: Estimate; onRecheck?: () => void; xlsxUrl?: string }) {
  const { t } = useT();
  const [open, setOpen] = useState<Record<string, boolean>>({ furniture: true });
  const tt = est.totals;
  return (
    <div className="col gap-16">
      <div className="grid g4">
        <div className="card flat pad"><div className="muted small">{t("estimate.known_total")}</div><div style={{ fontSize: 22, fontWeight: 800 }} className="mono">{amd(tt.known)}</div></div>
        <div className="card flat pad"><div className="muted small">{t("estimate.range")}</div><div style={{ fontSize: 16, fontWeight: 800 }} className="mono">{amd(tt.range_low, "")} – {amd(tt.range_high)}</div><div className="tiny muted">{t("estimate.range_hint", { n: tt.quote_required_lines })}</div></div>
        <div className="card flat pad"><div className="muted small">{t("estimate.confirmed_vs_estimated")}</div><div style={{ fontWeight: 800 }} className="mono">{amd(tt.confirmed, "")} / {amd(tt.estimated, "")}</div></div>
        <div className="card flat pad"><div className="muted small">{t("estimate.demo_catalog")}</div><div style={{ fontWeight: 800, color: tt.demo ? "var(--danger)" : undefined }} className="mono">{amd(tt.demo)}</div></div>
      </div>
      {est.budget && <div className={`alert ${est.budget.within ? "sage" : "warn"}`}>{t("estimate.budget_target", { target: amd(est.budget.target), delta: amd(est.budget.delta) })}</div>}
      <div className="row wrap">
        {onRecheck && <button className="btn" onClick={onRecheck}><RefreshCw size={15} /> {t("estimate.recheck")}</button>}
        {xlsxUrl && <a className="btn" href={xlsxUrl}><FileSpreadsheet size={15} /> XLSX</a>}
        <span className="muted small grow right">{t("estimate.generated_at", { when: dt(est.generated_at) })}</span>
      </div>
      <div className="card" style={{ overflow: "auto" }}>
        <table className="table compact">
          <thead><tr><th>№</th><th>{t("common.name")}</th><th>{t("common.supplier")}</th><th className="right">{t("common.qty")}</th><th className="right">{t("common.price")}</th><th className="right">{t("common.sum")}</th><th>{t("common.status")}</th><th>{t("common.checked")}</th><th /></tr></thead>
          <tbody>
            {est.sections.map((s) => (
              <Fragment key={s.group}>
                <tr onClick={() => setOpen({ ...open, [s.group]: !open[s.group] })} style={{ cursor: "pointer" }}>
                  <td colSpan={5} style={{ background: "var(--bg-2)", fontWeight: 800 }}><i className="dot" style={{ background: GROUP_COLORS[s.group] }} /> {t(`enum.group.${s.group}`)} <span className="muted small">({s.lines})</span></td>
                  <td className="right mono" style={{ background: "var(--bg-2)", fontWeight: 800 }}>{amd(s.total, "")}</td><td colSpan={3} style={{ background: "var(--bg-2)" }} className="small muted">{open[s.group] ? t("estimate.collapse") : t("estimate.expand")}</td>
                </tr>
                {open[s.group] && est.lines.filter((l) => l.group === s.group).map((l) => (
                  <tr key={l.id}>
                    <td className="muted small">{l.id}</td>
                    <td><div style={{ fontWeight: 600 }}>{lineName(l)}</div><div className="tiny muted">{l.group === "works" ? t("enum.group.works") : catName(l.category)}{l.sku ? ` · ${l.sku}` : ""}{l.area_m2 ? ` · ${l.area_m2} ${t("common.m2")}` : ""}</div>
                      {l.warnings?.length ? <div className="tiny" style={{ color: "#8a5d00" }}>⚠ {t("estimate.has_warnings", { n: l.warnings.length })}</div> : null}</td>
                    <td className="small">{l.supplier || "—"}</td>
                    <td className="right mono nowrap">{l.qty} {t(`unit.${l.unit}`)}</td>
                    <td className="right mono">{amd(l.unit_price, "")}</td>
                    <td className="right mono" style={{ fontWeight: 700 }}>{l.total === null ? <span className="muted">{t("common.on_request")}</span> : amd(l.total, "")}</td>
                    <td><PriceStatus s={l.price_status} /></td>
                    <td className="tiny muted">{l.checked_at ? dt(l.checked_at) : "—"}</td>
                    <td>{l.url ? <a href={l.url} target="_blank" rel="noreferrer" title={t("common.open_at_supplier")}><ExternalLink size={14} /></a> : null}</td>
                  </tr>
                ))}
              </Fragment>
            ))}
          </tbody>
        </table>
      </div>
      <Notices est={est} />
    </div>
  );
}
