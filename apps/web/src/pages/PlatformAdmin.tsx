import { Fragment, useCallback, useEffect, useState } from "react";
import { Activity, Bot, Boxes, Globe2, PenTool, ScrollText, ShieldAlert, Workflow } from "lucide-react";
import { api, apiPage, type Job } from "../lib/api";
import { dt } from "../lib/format";
import { useT } from "../i18n";
import { Badge, Loading, Switch, useToast } from "../components/ui";

interface Src { id: string; key: string; name: string; domain: string; enabled: boolean; live_enabled?: boolean; connector_type?: string; categories: string[]; method: string; connector_status: string; policy_status?: string; policy: Record<string, any>; rate_limit_s: number; notes: string; last_check_at: string | null; success_rate: number | null; avg_latency_ms: number | null; records: number; pending_review: number; last_errors: string[] }
interface Hist { runs: { at: string; kind: string; status: string; found: number; validated: number; latency_ms: number; errors: string[] }[]; alerts: { at: string; reason: string; detail: string }[]; index: { cursor?: number; total?: number; passes?: number; last_run_at?: string }; schedule: { index_interval_min: number | null; price_ttl_h: number | null } }
interface Ai { providers: Record<string, { available: boolean; model: string }>; usage: { task: string; provider: string; model: string; calls: number; input_tokens: number; output_tokens: number; cost_usd: number; avg_latency_ms: number; failures: number }[] }
type Tab = "sources" | "jobs" | "ai" | "aps" | "audit" | "quarantine";
interface Quarantined { at: string; project_id: string; filename: string; sha256: string; signature: string }

export default function PlatformAdmin() {
  const { t } = useT();
  const toast = useToast();
  const [tab, setTab] = useState<Tab>("sources");
  const [stats, setStats] = useState<Record<string, any> | null>(null);
  const [src, setSrc] = useState<Src[]>([]);
  const [jobs, setJobs] = useState<(Job & { attempts?: number })[]>([]);
  const [ai, setAi] = useState<Ai | null>(null);
  const [aps, setAps] = useState<Record<string, any> | null>(null);
  const [quar, setQuar] = useState<Quarantined[]>([]);
  const [hist, setHist] = useState<{ sid: string; data: Hist } | null>(null);
  type AuditRow = { action: string; entity: string; data: Record<string, unknown>; created_at: string };
  const [audit, setAudit] = useState<AuditRow[]>([]);
  const [auditNext, setAuditNext] = useState<string | null>(null);
  const moreAudit = async (cursor: string | null) => {
    const r = await apiPage<AuditRow>("/admin/audit?limit=100", cursor);
    setAudit((prev) => (cursor ? [...prev, ...r.items] : r.items));
    setAuditNext(r.next);
  };
  const load = useCallback(() => {
    api("/admin/stats").then(setStats);
    api<Src[]>("/admin/sources").then(setSrc);
    api<Job[]>("/admin/jobs").then(setJobs);
    api<Ai>("/admin/ai").then(setAi);
    api("/aps/status").then(setAps);
    moreAudit(null).catch(() => {});
    api<Quarantined[]>("/admin/quarantine").then(setQuar).catch(() => {});
  }, []);
  useEffect(() => { load(); }, [load]);
  const patch = async (s: Src, body: Partial<Src>) => { await api(`/admin/sources/${s.id}`, { method: "PATCH", json: body }); load(); };
  const index = async (s: Src) => {
    try { await api(`/admin/sources/${s.id}/index`, { method: "POST", json: { batch: 60 } }); toast(t("adm.index_started", { name: s.name })); }
    catch (x) { toast((x as Error).message, true); }
  };
  const test = async (s: Src) => { const r = await api<{ status: string; message: string }>(`/admin/sources/${s.id}/test`, { method: "POST" }); toast(`${s.name}: ${t(`enum.source_status.${r.status}`)}`); load(); };
  const history = async (s: Src) => { if (hist?.sid === s.id) return setHist(null); setHist({ sid: s.id, data: await api<Hist>(`/admin/sources/${s.id}/history`) }); };
  const apsAction = async (path: string) => { try { const r = await api(path, { method: "POST" }); toast(JSON.stringify(r)); } catch (x) { toast((x as Error).message, true); } };
  if (!stats) return <Loading />;
  const tabs: [Tab, typeof Bot][] = [["sources", Globe2], ["jobs", Workflow], ["ai", Bot], ["aps", PenTool], ["audit", ScrollText], ["quarantine", ShieldAlert]];
  return (
    <div className="col gap-16">
      <h1>{t("adm.title")}</h1>
      <div className="grid g4">
        <div className="card kpi"><div className="ico"><Boxes size={22} /></div><div><div className="v">{stats.products}</div><div className="small muted">{t("adm.skus", { n: stats.demo_products })}</div></div></div>
        <div className="card kpi"><div className="ico"><Globe2 size={22} /></div><div><div className="v">{stats.external_records}</div><div className="small muted">{t("adm.ext_records")}</div></div></div>
        <div className="card kpi"><div className="ico"><Workflow size={22} /></div><div><div className="v">{stats.projects} / {stats.variants}</div><div className="small muted">{t("adm.projects_variants")}</div></div></div>
        <div className="card kpi"><div className="ico"><Activity size={22} /></div><div><div className="v">{stats.jobs_failed}</div><div className="small muted">{t("adm.failed_jobs")}</div></div></div>
      </div>
      <div className="tabs">{tabs.map(([k, I]) => <button key={k} className={`tab ${tab === k ? "on" : ""}`} onClick={() => setTab(k)}><I size={16} /> {t(`adm.tab.${k}`)}</button>)}</div>
      {tab === "sources" && (
        <div className="col gap-10">
          <div className="alert info small">{stats.integrations.external_fetch_live ? t("adm.live_on") : t("adm.live_off")}</div>
          <div className="card" style={{ overflow: "auto" }}>
            <table className="table compact">
              <thead><tr><th>{t("adm.col.on")}</th><th>{t("adm.col.source")}</th><th>{t("adm.col.connector")}</th><th>{t("common.status")}</th><th>{t("adm.col.policy")}</th><th>{t("adm.col.rate")}</th><th className="right">{t("adm.col.records")}</th><th className="right">{t("adm.col.review")}</th><th>{t("adm.col.success")}</th><th>{t("adm.col.check")}</th><th /></tr></thead>
              <tbody>{src.map((s) => (<Fragment key={s.id}>
                <tr>
                  <td><Switch on={s.enabled} onChange={(v) => patch(s, { enabled: v })} label={s.name} /></td>
                  <td><b>{s.name}</b><div className="tiny muted">{s.domain}</div></td>
                  <td><Badge tone="info">{s.connector_type || s.method}</Badge>{s.live_enabled && <Badge tone="sage">live</Badge>}</td>
                  <td><Badge tone={s.connector_status === "ok" ? "sage" : s.connector_status === "unreachable" ? "danger" : "warn"}>{t(`enum.source_status.${s.connector_status}`)}</Badge></td>
                  <td className="tiny">{s.policy_status ? t(`enum.policy.${s.policy_status}`) : "—"}{s.policy.search_disallowed ? <div>{t("adm.search_disallowed")}</div> : null}{s.policy.jsonld_product ? <div>JSON-LD ✓</div> : null}</td>
                  <td><input className="input" style={{ width: 70, height: 30 }} defaultValue={s.rate_limit_s} aria-label={t("adm.col.rate")} onBlur={(e) => Number(e.target.value) !== s.rate_limit_s && patch(s, { rate_limit_s: Number(e.target.value) })} /> s</td>
                  <td className="right">{s.records}</td><td className="right">{s.pending_review}</td>
                  <td className="small">{s.success_rate === null ? "—" : `${Math.round(s.success_rate * 100)}%`}{s.avg_latency_ms ? <div className="tiny muted">{s.avg_latency_ms} ms</div> : null}</td>
                  <td className="tiny muted">{dt(s.last_check_at)}{s.last_errors[0] && <div style={{ color: "var(--danger)" }}>{s.last_errors[0]}</div>}</td>
                  <td className="row gap-4"><button className="btn sm" onClick={() => test(s)}>{t("adm.test")}</button>
                    {s.connector_type === "jsonld_index" && <button className="btn sm" title={t("adm.index_hint")} onClick={() => index(s)}>{t("adm.index")}</button>}
                    <button className="btn sm ghost" aria-expanded={hist?.sid === s.id} onClick={() => history(s)}>{t("adm.history")}</button></td>
                </tr>
                {hist?.sid === s.id && <tr><td colSpan={11}><SourceHistory h={hist.data} /></td></tr>}
              </Fragment>))}</tbody>
            </table>
          </div>
        </div>
      )}
      {tab === "jobs" && <div className="card" style={{ overflow: "auto" }}><table className="table compact"><thead><tr><th>{t("adm.col.job")}</th><th>{t("common.status")}</th><th>{t("adm.col.progress")}</th><th>{t("adm.col.attempts")}</th><th>{t("adm.col.error")}</th></tr></thead>
        <tbody>{jobs.map((j) => <tr key={j.id}><td><b>{j.kind}</b><div className="tiny muted">{j.id.slice(0, 8)}</div></td><td><Badge tone={j.status === "succeeded" ? "sage" : j.status === "failed" ? "danger" : "info"}>{t(`enum.job.${j.status}`)}</Badge></td><td>{Math.round(j.progress * 100)}%</td><td>{j.attempts}</td><td className="small" style={{ color: "var(--danger)" }}>{j.error}</td></tr>)}</tbody></table></div>}
      {tab === "ai" && ai && <div className="col gap-10">
        <div className="grid g4">{Object.entries(ai.providers).map(([k, v]) => <div key={k} className="card pad"><b>{k}</b><div className="small muted">{v.model}</div><Badge tone={v.available ? "sage" : ""}>{v.available ? t("adm.ai_connected") : t("adm.ai_nokey")}</Badge></div>)}</div>
        <div className="alert info small">{t("adm.ai_note")}</div>
        <table className="table compact card"><thead><tr><th>{t("adm.col.task")}</th><th>{t("adm.col.provider")}</th><th>{t("adm.col.model")}</th><th className="right">{t("adm.col.calls")}</th><th className="right">{t("adm.col.tokens")}</th><th className="right">$</th><th className="right">{t("adm.col.latency")}</th><th className="right">{t("adm.col.failures")}</th></tr></thead>
          <tbody>{ai.usage.map((u, i) => <tr key={i}><td>{u.task}</td><td>{u.provider}</td><td className="small">{u.model}</td><td className="right">{u.calls}</td><td className="right mono">{u.input_tokens}/{u.output_tokens}</td><td className="right mono">{u.cost_usd}</td><td className="right">{u.avg_latency_ms} ms</td><td className="right">{u.failures}</td></tr>)}</tbody></table>
      </div>}
      {tab === "aps" && aps && <div className="card pad col gap-10">
        <div className="row"><h3>Autodesk Platform Services</h3><Badge tone={aps.enabled ? "sage" : "warn"}>{aps.enabled ? t("adm.aps_connected") : t("adm.aps_off")}</Badge></div>
        <div className="small">{t("adm.aps_line", { bucket: aps.bucket || "—", region: aps.region, activity: aps.design_automation_activity || "—" })}</div>
        <div className="small muted">{t("adm.aps_caps")}</div>
        <div className="row"><button className="btn" disabled={!aps.enabled} onClick={() => apsAction("/aps/test")}>{t("adm.aps_test")}</button><button className="btn" disabled={!aps.enabled} onClick={() => apsAction("/aps/setup-design-automation")}>{t("adm.aps_setup")}</button></div>
        {!aps.enabled && <div className="alert warn small">{t("adm.aps_hint")}</div>}
      </div>}
      {tab === "audit" && <div className="card" style={{ overflow: "auto", maxHeight: 600 }}><table className="table compact"><thead><tr><th>{t("adm.col.time")}</th><th>{t("adm.col.action")}</th><th>{t("adm.col.entity")}</th><th>{t("adm.col.data")}</th></tr></thead>
        <tbody>{audit.map((a, i) => <tr key={i}><td className="small nowrap">{dt(a.created_at)}</td><td><b className="small">{a.action}</b></td><td className="small">{a.entity}</td><td className="tiny mono">{JSON.stringify(a.data).slice(0, 120)}</td></tr>)}</tbody></table>
        {auditNext && <div className="row" style={{ justifyContent: "center", padding: 10 }}><button className="btn sm" onClick={() => moreAudit(auditNext)}>{t("common.load_more")}</button></div>}</div>}
      {tab === "quarantine" && <div className="card" style={{ overflow: "auto" }}>{quar.length === 0 ? <p className="pad muted">{t("adm.quarantine_empty")}</p> :
        <table className="table compact"><thead><tr><th>{t("adm.col.time")}</th><th>{t("adm.col.source")}</th><th>{t("adm.col.signature")}</th><th>SHA-256</th></tr></thead>
          <tbody>{quar.map((q) => <tr key={q.sha256 + q.at}><td className="small nowrap">{dt(q.at)}</td><td className="small">{q.filename}</td><td><b className="small">{q.signature}</b></td><td className="tiny mono">{q.sha256.slice(0, 16)}…</td></tr>)}</tbody></table>}</div>}
    </div>
  );
}

function SourceHistory({ h }: { h: Hist }) {
  const { t } = useT();
  return (
    <div className="col gap-8" style={{ padding: "6px 4px 12px" }}>
      <div className="row gap-12 wrap tiny muted">
        {h.schedule.index_interval_min && <span>{t("adm.hist.schedule", { n: h.schedule.index_interval_min })}</span>}
        {h.schedule.price_ttl_h && <span>{t("adm.hist.ttl", { n: h.schedule.price_ttl_h })}</span>}
        {h.index.total ? <span>{t("adm.hist.cursor", { cursor: h.index.cursor ?? 0, total: h.index.total, passes: h.index.passes ?? 0 })}</span> : null}
      </div>
      <b className="small">{t("adm.hist.alerts")}</b>
      {h.alerts.length ? h.alerts.map((a) => <div key={a.at + a.reason} className="small"><Badge tone="danger">{t(`notif.reason.${a.reason}`)}</Badge> <span className="tiny muted">{dt(a.at)} · {a.detail}</span></div>)
        : <div className="small muted">{t("adm.hist.no_alerts")}</div>}
      <table className="table compact">
        <thead><tr><th>{t("adm.hist.at")}</th><th>{t("adm.hist.kind")}</th><th>{t("common.status")}</th><th className="right">{t("adm.hist.found")}</th><th className="right">{t("adm.hist.validated")}</th><th className="right">ms</th><th>{t("adm.col.error")}</th></tr></thead>
        <tbody>{h.runs.map((r, i) => <tr key={i}><td className="tiny">{dt(r.at)}</td><td className="small">{r.kind}</td><td><Badge tone={r.status === "ok" ? "sage" : r.status === "error" || r.status === "blocked" ? "danger" : ""}>{r.status}</Badge></td>
          <td className="right">{r.found}</td><td className="right">{r.validated}</td><td className="right tiny">{r.latency_ms}</td><td className="tiny" style={{ color: "var(--danger)" }}>{r.errors[0]}</td></tr>)}</tbody>
      </table>
    </div>
  );
}
