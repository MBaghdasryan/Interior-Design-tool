import { useEffect, useState } from "react";
import { api } from "../lib/api";
import { useT } from "../i18n";
import { Badge } from "./ui";

interface Cap { key: string; status: "supported" | "needs_keys" | "in_development"; formats: string[]; live_verified: boolean }
const TONE = { supported: "sage", needs_keys: "warn", in_development: "info" } as const;

/** What Renovara really does with RVT / IFC / DWG files (Autodesk APS), stated per capability. */
export default function ApsCapabilities({ compact = false }: { compact?: boolean }) {
  const { t } = useT();
  const [caps, setCaps] = useState<Cap[]>([]);
  useEffect(() => { api<{ capabilities: Cap[] }>("/aps/status").then((s) => setCaps(s.capabilities || [])).catch(() => {}); }, []);
  if (!caps.length) return null;
  return (
    <div className="col gap-6" aria-label={t("aps.cap.title")} role="group">
      {!compact && <b className="small">{t("aps.cap.title")}</b>}
      <div className="row gap-6 wrap">
        {caps.map((c) => (
          <span key={c.key} title={`${c.formats.map((f) => f.toUpperCase()).join(", ")}${c.status === "supported" && !c.live_verified ? ` — ${t("aps.cap.not_live_verified")}` : ""}`}>
            <Badge tone={TONE[c.status]}>{t(`aps.cap.${c.key}`)}: {t(`aps.cap.status.${c.status}`)}</Badge>
          </span>
        ))}
      </div>
      {caps.some((c) => c.status === "supported" && !c.live_verified) && <div className="tiny muted">{t("aps.cap.not_live_verified")}</div>}
    </div>
  );
}
