import { useEffect, useState } from "react";
import { Cpu } from "lucide-react";
import { api } from "../lib/api";
import { useT } from "../i18n";

interface Cost { total_usd: number; calls: number; by_task: { task: string; calls: number; cost_usd: number }[] }

/** AI spend of this project (estimate from token / image counts) — the variable AI part of its unit cost. */
export default function ProjectAiCost({ pid }: { pid: string }) {
  const { t } = useT();
  const [c, setC] = useState<Cost | null>(null);
  useEffect(() => { api<Cost>(`/projects/${pid}/ai-cost`).then(setC).catch(() => {}); }, [pid]);
  if (!c) return null;
  return (
    <details className="small" style={{ marginTop: 8 }}>
      <summary className="row gap-6" style={{ display: "inline-flex", cursor: "pointer" }}><Cpu size={15} /> {t("aicost.project", { usd: c.total_usd.toFixed(2), n: c.calls })}</summary>
      <table className="table compact" style={{ maxWidth: 420 }}><tbody>
        {c.by_task.map((r) => <tr key={r.task}><td className="small">{t(`aicost.task.${r.task}`)}</td><td className="right small">{r.calls}</td><td className="right mono small">${r.cost_usd.toFixed(3)}</td></tr>)}
      </tbody></table>
      <div className="tiny muted">{t("ai.estimate_note")}</div>
    </details>
  );
}
