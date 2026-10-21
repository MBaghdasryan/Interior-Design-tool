import { useCallback, useEffect, useState } from "react";
import { Activity, Bot, Boxes, Globe2, PenTool, ScrollText, Workflow } from "lucide-react";
import { api, type Job } from "../lib/api";
import { dt } from "../lib/format";
import { useT } from "../i18n";
import { Badge, Loading, Switch, useToast } from "../components/ui";

interface Src { id: string; key: string; name: string; domain: string; enabled: boolean; live_enabled?: boolean; connector_type?: string; categories: string[]; method: string; connector_status: string; policy_status?: string; policy: Record<string, any>; rate_limit_s: number; notes: string; last_check_at: string | null; success_rate: number | null; avg_latency_ms: number | null; records: number; pending_review: number; last_errors: string[] }
interface Ai { providers: Record<string, { available: boolean; model: string }>; usage: { task: string; provider: string; model: string; calls: number; input_tokens: number; output_tokens: number; cost_usd: number; avg_latency_ms: number; failures: number }[] }
type Tab = "sources" | "jobs" | "ai" | "aps" | "audit";

export default function PlatformAdmin() {
  const { t } = useT();
  const toast = useToast();
  const [tab, setTab] = useState<Tab>("sources");
  const [stats, setStats] = useState<Record<string, any> | null>(null);
  const [src, setSrc] = useState<Src[]>([]);
  const [jobs, setJobs] = useState<(Job & { attempts?: number })[]>([]);
  const [ai, setAi] = useState<Ai | null>(null);
  const [aps, setAps] = useState<Record<string, any> | null>(null);
  const [audit, setAudit] = useState<{ action: string; entity: string; data: Record<string, unknown>; created_at: string }[]>([]);
  const load = useCallback(() => {
    api("/admin/stats").then(setStats);
    api<Src[]>("/admin/sources").then(setSrc);
    api<Job[]>("/admin/jobs").then(setJobs);
    api<Ai>("/admin/ai").then(setAi);
    api("/aps/status").then(setAps);
    api("/admin/audit").then(setAudit);
  }, []);
  useEffect(() => { load(); }, [load]);
  const patch = async (s: Src, body: Partial<Src>) => { await api(`/admin/sources/${s.id}`, { method: "PATCH", json: body }); load(); };
  const test = async (s: Src) => { const r = await api<{ status: string; message: string }>(`/admin/sources/${s.id}/test`, { method: "POST" }); toast(`${s.name}: ${t(`enum.source_status.${r.status}`)}`); load(); };
  const apsAction = async (path: string) => { try { const r = await api(path, { method: "POST" }); toast(JSON.stringify(r)); } catch (x) { toast((x as Error).message, true); } };
  if (!stats) return <Loading />;
  const tabs: [Tab, typeof Bot][] = [["sources", Globe2], ["jobs", Workflow], ["ai", Bot], ["aps", PenTool], ["audit", ScrollText]];
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
              <tbody>{src.map((s) => (
                <tr key={s.id}>
                  <td><Switch on={s.enabled} onChange={(v) => patch(s, { enabled: v })} label={s.name} /></td>
                  <td><b>{s.name}</b><div className="tiny muted">{s.domain}</div></td>
                  <td><Badge tone="info">{s.connector_type || s.method}</Badge>{s.live_enabled && <Badge tone="sage">live</Badge>}</td>
                  <td><Badge tone={s.connector_status === "ok" ? "sage" : s.connector_status === "unreachable" ? "danger" : "warn"}>{t(`enum.source_status.${s.connector_status}`)}</Badge></td>
                  <td className="tiny">{s.policy_status ? t(`enum.policy.${s.policy_status}`) : "—"}{s.policy.search_disallowed ? <div>{t("adm.search_disallowed")}</div> : null}{s.policy.jsonld_product ? <div>JSON-LD ✓</div> : null}</td>
                  <td><input className="input" style={{ width: 70, height: 30 }} defaultValue={s.rate_limit_s} aria-label={t("adm.col.rate")} onBlur={(e) => Number(e.target.value) !== s.rate_limit_s && patch(s, { rate_limit_s: Number(e.target.value) })} /> s</td>
                  <td className="right">{s.records}</td><td className="right">{s.pending_review}</td>
                  <td className="small">{s.success_rate === null ? "—" : `${Math.round(s.success_rate * 100)}%`}{s.avg_latency_ms ? <div className="tiny muted">{s.avg_latency_ms} ms</div> : null}</td>
                  <td className="tiny muted">{dt(s.last_check_at)}{s.last_errors[0] && <div style={{ color: "var(--danger)" }}>{s.last_errors[0]}</div>}</td>
                  <td><button className="btn sm" onClick={() => test(s)}>{t("adm.test")}</button></td>
                </tr>))}</tbody>
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
        <tbody>{audit.map((a, i) => <tr key={i}><td className="small nowrap">{dt(a.created_at)}</td><td><b className="small">{a.action}</b></td><td className="small">{a.entity}</td><td className="tiny mono">{JSON.stringify(a.data).slice(0, 120)}</td></tr>)}</tbody></table></div>}
    </div>
  );
}
