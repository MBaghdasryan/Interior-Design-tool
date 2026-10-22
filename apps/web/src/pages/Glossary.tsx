import { useCallback, useEffect, useState } from "react";
import { Check, Download, Search, X } from "lucide-react";
import { api } from "../lib/api";
import { dt } from "../lib/format";
import { useT } from "../i18n";
import { Badge, Empty, Loading, useToast } from "../components/ui";

interface Term { term_key: string; table: string; key: string; hy: string; ru: string; en: string; proposed: string | null; comment: string; status: string; author: string; reviewed_by: string; updated_at: string | null }
interface Resp { items: Term[]; total: number; counts: Record<string, number>; tables: string[] }
const TONE: Record<string, string> = { original: "", proposed: "warn", approved: "sage", rejected: "danger" };

/** Armenian terminology review: approved corrections are applied to the album immediately. */
export default function Glossary() {
  const { t } = useT();
  const toast = useToast();
  const [q, setQ] = useState("");
  const [status, setStatus] = useState("");
  const [table, setTable] = useState("");
  const [data, setData] = useState<Resp | null>(null);
  const [edit, setEdit] = useState<Record<string, { hy: string; comment: string }>>({});
  const load = useCallback(() => {
    const p = new URLSearchParams({ q, status, table });
    api<Resp>(`/glossary?${p}`).then(setData).catch((x) => toast((x as Error).message, true));
  }, [q, status, table, toast]);
  useEffect(() => { const tm = setTimeout(load, 250); return () => clearTimeout(tm); }, [load]);
  const run = async (fn: () => Promise<unknown>, ok: string) => { try { await fn(); toast(ok); load(); } catch (x) { toast((x as Error).message, true); } };
  if (!data) return <Loading />;
  return (
    <div className="col gap-16">
      <div className="row between wrap"><div><h1>{t("gls.title")}</h1><p className="muted">{t("gls.lead")}</p></div>
        <a className="btn" href="/api/v1/glossary/export.xlsx"><Download size={15} /> XLSX</a></div>
      <div className="row gap-6 wrap small">
        <Badge>{t("gls.total", { n: data.total })}</Badge>
        {(["proposed", "approved", "rejected"] as const).map((s) => <Badge key={s} tone={TONE[s]}>{t(`gls.status.${s}`)}: {data.counts[s] || 0}</Badge>)}
      </div>
      <div className="card pad row gap-8 wrap">
        <div className="row grow" style={{ minWidth: 220 }}><Search size={16} /><input className="input" aria-label={t("common.search")} placeholder={t("gls.search")} value={q} onChange={(e) => setQ(e.target.value)} /></div>
        <select className="select input" aria-label={t("gls.filter_status")} value={status} onChange={(e) => setStatus(e.target.value)}>
          <option value="">{t("gls.all")}</option>{["original", "proposed", "approved", "rejected"].map((s) => <option key={s} value={s}>{t(`gls.status.${s}`)}</option>)}</select>
        <select className="select input" aria-label={t("gls.filter_table")} value={table} onChange={(e) => setTable(e.target.value)}>
          <option value="">{t("gls.all")}</option>{data.tables.map((x) => <option key={x} value={x}>{t(`gls.table.${x}`)}</option>)}</select>
      </div>
      {!data.items.length ? <Empty>{t("common.nothing_found")}</Empty> : (
        <div className="card" style={{ overflow: "auto" }}>
          <table className="table compact">
            <thead><tr><th>{t("gls.col.term")}</th><th>{t("gls.col.ru_en")}</th><th>{t("gls.col.hy")}</th><th>{t("gls.col.proposal")}</th><th /></tr></thead>
            <tbody>{data.items.slice(0, 300).map((x) => {
              const ed = edit[x.term_key] ?? { hy: x.proposed ?? x.hy, comment: x.comment };
              return (
                <tr key={x.term_key}>
                  <td className="tiny muted" style={{ maxWidth: 160 }}>{t(`gls.table.${x.table}`)}<div className="mono">{x.key}</div></td>
                  <td className="small" style={{ maxWidth: 260 }}>{x.ru}<div className="tiny muted">{x.en}</div></td>
                  <td className="small" style={{ maxWidth: 260 }}><b>{x.hy}</b><div><Badge tone={TONE[x.status]}>{t(`gls.status.${x.status}`)}</Badge></div>
                    {x.author && <div className="tiny muted">{x.author}{x.updated_at ? ` · ${dt(x.updated_at)}` : ""}</div>}</td>
                  <td style={{ minWidth: 260 }} className="col gap-4">
                    <input className="input" lang="hy" aria-label={t("gls.col.proposal")} value={ed.hy} onChange={(e) => setEdit({ ...edit, [x.term_key]: { ...ed, hy: e.target.value } })} />
                    <input className="input" aria-label={t("gls.comment")} placeholder={t("gls.comment")} value={ed.comment} onChange={(e) => setEdit({ ...edit, [x.term_key]: { ...ed, comment: e.target.value } })} />
                  </td>
                  <td className="col gap-4">
                    <button className="btn sm" disabled={!edit[x.term_key]} onClick={() => run(async () => { await api(`/glossary/${encodeURIComponent(x.term_key)}`, { method: "PUT", json: ed }); const n = { ...edit }; delete n[x.term_key]; setEdit(n); }, t("gls.saved"))}>{t("common.save")}</button>
                    {x.status === "proposed" && <>
                      <button className="btn sm primary" onClick={() => run(() => api(`/glossary/${encodeURIComponent(x.term_key)}/decision`, { method: "POST", json: { decision: "approved" } }), t("gls.status.approved"))}><Check size={14} /> {t("gls.approve")}</button>
                      <button className="btn sm ghost" onClick={() => run(() => api(`/glossary/${encodeURIComponent(x.term_key)}/decision`, { method: "POST", json: { decision: "rejected" } }), t("gls.status.rejected"))}><X size={14} /> {t("gls.reject")}</button></>}
                  </td>
                </tr>);
            })}</tbody>
          </table>
          {data.items.length > 300 && <div className="small muted" style={{ padding: 12 }}>{t("gls.refine", { n: data.items.length })}</div>}
        </div>)}
    </div>
  );
}
