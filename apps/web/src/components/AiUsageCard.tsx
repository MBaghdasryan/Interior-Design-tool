import { useEffect, useState } from "react";
import { Cpu } from "lucide-react";
import { api } from "../lib/api";
import { useT } from "../i18n";
import { useToast } from "./ui";

interface Usage { limits: { daily_usd: number; monthly_usd: number }; today_usd: number; month_usd: number; by_task: { task: string; provider: string; calls: number; cost_usd: number }[] }
const usd = (v: number) => `$${v.toFixed(2)}`;

/** Organisation AI spend against its daily / monthly budget (estimates from token and image counts). */
export default function AiUsageCard({ canEdit }: { canEdit: boolean }) {
  const { t } = useT();
  const toast = useToast();
  const [u, setU] = useState<Usage | null>(null);
  const [lim, setLim] = useState({ daily_usd: 0, monthly_usd: 0 });
  useEffect(() => { api<Usage>("/bureau/ai-usage").then((x) => { setU(x); setLim(x.limits); }).catch(() => {}); }, []);
  if (!u) return null;
  const bar = (v: number, cap: number) => <div className="progress" aria-hidden><i style={{ width: `${cap ? Math.min(100, (v / cap) * 100) : 0}%`, background: cap && v >= cap ? "var(--danger)" : undefined }} /></div>;
  const save = async () => { try { const x = await api<Usage>("/bureau/ai-budget", { method: "PUT", json: lim }); setU(x); toast(t("acc.saved")); } catch (e) { toast((e as Error).message, true); } };
  return (
    <div className="card pad col gap-10">
      <h3 className="row gap-6"><Cpu size={18} /> {t("ai.usage_title")}</h3>
      <div className="grid g2">
        <div><div className="small muted">{t("ai.today")}</div><b className="mono">{usd(u.today_usd)}</b> <span className="tiny muted">/ {u.limits.daily_usd ? usd(u.limits.daily_usd) : "∞"}</span>{bar(u.today_usd, u.limits.daily_usd)}</div>
        <div><div className="small muted">{t("ai.month")}</div><b className="mono">{usd(u.month_usd)}</b> <span className="tiny muted">/ {u.limits.monthly_usd ? usd(u.limits.monthly_usd) : "∞"}</span>{bar(u.month_usd, u.limits.monthly_usd)}</div>
      </div>
      {u.by_task.length > 0 && <table className="table compact"><thead><tr><th>{t("ai.task")}</th><th>{t("ai.provider")}</th><th className="right">{t("ai.calls")}</th><th className="right">USD</th></tr></thead>
        <tbody>{u.by_task.map((r) => <tr key={r.task + r.provider}><td className="small">{r.task}</td><td className="small">{r.provider}</td><td className="right small">{r.calls}</td><td className="right mono small">{usd(r.cost_usd)}</td></tr>)}</tbody></table>}
      {canEdit && <div className="row gap-6 wrap">
        <label className="small">{t("ai.limit_day")} <input className="input" style={{ width: 90 }} type="number" min={0} value={lim.daily_usd} onChange={(e) => setLim({ ...lim, daily_usd: Number(e.target.value) })} /></label>
        <label className="small">{t("ai.limit_month")} <input className="input" style={{ width: 90 }} type="number" min={0} value={lim.monthly_usd} onChange={(e) => setLim({ ...lim, monthly_usd: Number(e.target.value) })} /></label>
        <button className="btn sm" onClick={save}>{t("common.save")}</button>
      </div>}
      <p className="tiny muted">{t("ai.estimate_note")}</p>
    </div>
  );
}
