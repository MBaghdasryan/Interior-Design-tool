import { useCallback, useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Bell, CheckCheck } from "lucide-react";
import { api } from "../lib/api";
import { dt } from "../lib/format";
import { useT } from "../i18n";

export const NOTIF_KINDS = ["job_done", "job_failed", "client_comment", "client_approved", "client_changes", "rfq_reply", "price_stale", "catalog_alert"] as const;
interface Notif { id: string; kind: string; params: Record<string, string | number>; link: string; read: boolean; created_at: string }

/** Top-bar bell: unread counter (polled every minute), dropdown with the latest 50, mark read / all read. */
export default function NotificationBell() {
  const { t } = useT();
  const nav = useNavigate();
  const [open, setOpen] = useState(false);
  const [data, setData] = useState<{ items: Notif[]; unread: number }>({ items: [], unread: 0 });
  const box = useRef<HTMLDivElement>(null);
  const load = useCallback(() => { api<{ items: Notif[]; unread: number }>("/notifications").then(setData).catch(() => {}); }, []);
  useEffect(() => { load(); const id = setInterval(load, 60_000); return () => clearInterval(id); }, [load]);
  useEffect(() => {
    if (!open) return;
    const close = (e: MouseEvent | KeyboardEvent) => { if (e instanceof KeyboardEvent ? e.key === "Escape" : !box.current?.contains(e.target as Node)) setOpen(false); };
    document.addEventListener("mousedown", close);
    document.addEventListener("keydown", close);
    return () => { document.removeEventListener("mousedown", close); document.removeEventListener("keydown", close); };
  }, [open]);
  const text = (n: Notif) => t(`notif.kind.${n.kind}`, { ...n.params, job: n.params.job ? t(`notif.job.${n.params.job}`) : "" });
  const go = async (n: Notif) => {
    if (!n.read) await api(`/notifications/${n.id}/read`, { method: "POST" }).catch(() => {});
    setOpen(false);
    load();
    if (n.link) nav(n.link);
  };
  return (
    <div className="notif-wrap" ref={box}>
      <button className="icon-btn notif-btn" aria-label={t("notif.bell", { n: data.unread })} aria-expanded={open} aria-haspopup="true" onClick={() => { setOpen(!open); if (!open) load(); }}>
        <Bell size={18} />{data.unread > 0 && <span className="notif-count" aria-hidden>{data.unread > 99 ? "99+" : data.unread}</span>}
      </button>
      {open && <div className="notif-panel card" role="region" aria-label={t("common.notifications")}>
        <div className="row between notif-head"><b>{t("common.notifications")}</b>
          {data.unread > 0 && <button className="btn sm ghost" onClick={async () => { await api("/notifications/read-all", { method: "POST" }).catch(() => {}); load(); }}><CheckCheck size={15} /> {t("notif.read_all")}</button>}</div>
        {data.items.length === 0 ? <div className="muted small notif-empty">{t("notif.empty")}</div> :
          <ul className="notif-list">{data.items.map((n) => (
            <li key={n.id}><button className={`notif-item ${n.read ? "" : "unread"}`} onClick={() => go(n)}>
              <span className="small">{text(n)}</span>
              <span className="tiny muted">{n.params.project ? `${n.params.project} · ` : ""}{dt(n.created_at)}</span>
            </button></li>))}</ul>}
      </div>}
    </div>
  );
}
