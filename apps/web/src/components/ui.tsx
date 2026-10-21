import { createContext, useCallback, useContext, useState, type ReactNode } from "react";
import { X } from "lucide-react";
import { ACCURACY_TONE, PRICE_TONE } from "../lib/format";
import { useT } from "../i18n";

export function Badge({ tone = "", children, title }: { tone?: string; children: ReactNode; title?: string }) {
  return <span className={`badge ${tone}`} title={title}>{children}</span>;
}

export function PriceStatus({ s }: { s: string }) {
  const { t } = useT();
  return <Badge tone={PRICE_TONE[s] ?? ""}>{t(`enum.price.${s}`)}</Badge>;
}

export function AccuracyBadge({ level }: { level: string }) {
  const { t } = useT();
  return <Badge tone={ACCURACY_TONE[level] || "warn"} title={t(`enum.accuracy_hint.${level}`)}>{t(`enum.accuracy.${level}`)}</Badge>;
}

export function StepStatus({ s }: { s: string }) {
  const { t } = useT();
  return <Badge tone={s === "done" ? "sage" : s === "warning" ? "warn" : s === "failed" ? "danger" : ""}>{t(`enum.step.${s}`)}</Badge>;
}

export function Loading({ label }: { label?: string }) {
  const { t } = useT();
  return <div className="row" style={{ padding: 24, color: "var(--ink-3)" }}><span className="spinner" /> {label || t("common.loading")}</div>;
}

export function Empty({ children }: { children: ReactNode }) {
  return <div className="empty">{children}</div>;
}

export function Progress({ value }: { value: number }) {
  return <div className="progress" role="progressbar" aria-valuenow={Math.round(value * 100)}><i style={{ width: `${Math.round(value * 100)}%` }} /></div>;
}

export function Drawer({ open, onClose, title, children, footer }: { open: boolean; onClose: () => void; title: ReactNode; children: ReactNode; footer?: ReactNode }) {
  const { t } = useT();
  if (!open) return null;
  return (
    <>
      <div className="drawer-back" onClick={onClose} />
      <aside className="drawer" role="dialog" aria-modal="true">
        <div className="hd"><div className="grow"><h3>{title}</h3></div><button className="icon-btn" onClick={onClose} aria-label={t("common.close")}><X size={18} /></button></div>
        <div className="bd">{children}</div>
        {footer && <div className="ft">{footer}</div>}
      </aside>
    </>
  );
}

export function Modal({ open, onClose, children }: { open: boolean; onClose: () => void; children: ReactNode }) {
  if (!open) return null;
  return <div className="modal" onClick={onClose}><div onClick={(e) => e.stopPropagation()}>{children}</div></div>;
}

export function Switch({ on, onChange, label }: { on: boolean; onChange: (v: boolean) => void; label?: string }) {
  return <button type="button" role="switch" aria-checked={on} aria-label={label} className={`switch ${on ? "on" : ""}`} onClick={() => onChange(!on)} />;
}

const ToastCtx = createContext<(msg: string, err?: boolean) => void>(() => {});
export function ToastProvider({ children }: { children: ReactNode }) {
  const [t, setT] = useState<{ msg: string; err: boolean } | null>(null);
  const show = useCallback((msg: string, err = false) => { setT({ msg, err }); setTimeout(() => setT(null), err ? 6000 : 3200); }, []);
  return <ToastCtx.Provider value={show}>{children}{t && <div className={`toast ${t.err ? "err" : ""}`} role="status">{t.msg}</div>}</ToastCtx.Provider>;
}
export const useToast = () => useContext(ToastCtx);
