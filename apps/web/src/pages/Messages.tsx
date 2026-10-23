import { useCallback, useEffect, useRef, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { Eye, Lock, MessagesSquare, Send } from "lucide-react";
import { api } from "../lib/api";
import { dt } from "../lib/format";
import { useT } from "../i18n";
import { Badge, Empty, Loading, useToast } from "../components/ui";

interface Msg { id: string; body: string; author: string; from_client: boolean; mine: boolean; visibility: string; at: string }
interface Inbox { items: { project_id: string; title: string; client_name: string; last: Msg; unread: number }[]; unread: number }

/** One conversation per project: team-only notes and messages the client sees in the portal (mockup 31). */
export function ProjectChat({ pid, height = 460 }: { pid: string; height?: number | string }) {
  const { t } = useT();
  const toast = useToast();
  const [msgs, setMsgs] = useState<Msg[] | null>(null);
  const [body, setBody] = useState("");
  const [vis, setVis] = useState<"team" | "client">("team");
  const end = useRef<HTMLDivElement>(null);
  const load = useCallback(() => api<Msg[]>(`/projects/${pid}/messages`).then((m) => { setMsgs(m); api(`/projects/${pid}/messages/read`, { method: "POST" }).catch(() => {}); }).catch(() => setMsgs([])), [pid]);
  useEffect(() => { load(); const iv = setInterval(load, 15000); return () => clearInterval(iv); }, [load]);
  useEffect(() => { end.current?.scrollIntoView({ block: "end" }); }, [msgs]);
  const send = async () => {
    if (!body.trim()) return;
    try { await api(`/projects/${pid}/messages`, { method: "POST", json: { body, visibility: vis } }); setBody(""); load(); } catch (x) { toast((x as Error).message, true); }
  };
  if (!msgs) return <Loading />;
  return (
    <div className="chat" style={{ height }}>
      <div className="chat-log">
        {!msgs.length && <div className="small muted" style={{ padding: 16 }}>{t("msg.empty")}</div>}
        {msgs.map((m) => <div key={m.id} className={`bubble ${m.mine ? "mine" : ""} ${m.from_client ? "client" : ""} ${m.visibility === "team" ? "team" : ""}`}>
          <div className="tiny muted">{m.author}{m.from_client ? ` · ${t("msg.client")}` : ""} · {dt(m.at)} {m.visibility === "team" ? <span title={t("msg.team_only")}><Lock size={11} /></span> : <span title={t("msg.visible_client")}><Eye size={11} /></span>}</div>
          <div className="small" style={{ whiteSpace: "pre-wrap" }}>{m.body}</div>
        </div>)}
        <div ref={end} />
      </div>
      <div className="chat-input">
        <div className="seg" role="group" aria-label={t("msg.visibility")}>
          <button className={vis === "team" ? "on" : ""} onClick={() => setVis("team")}><Lock size={13} /> {t("msg.to_team")}</button>
          <button className={vis === "client" ? "on" : ""} onClick={() => setVis("client")}><Eye size={13} /> {t("msg.to_client")}</button></div>
        <textarea className="input grow" rows={2} aria-label={t("msg.write")} placeholder={vis === "client" ? t("msg.ph_client") : t("msg.ph_team")} value={body} onChange={(e) => setBody(e.target.value)}
          onKeyDown={(e) => { if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) send(); }} />
        <button className="btn primary" disabled={!body.trim()} onClick={send}><Send size={15} /> {t("common.send")}</button>
      </div>
    </div>
  );
}

/** Inbox across projects with unread counters. */
export default function Messages() {
  const { t } = useT();
  const [sp, setSp] = useSearchParams();
  const [box, setBox] = useState<Inbox | null>(null);
  const load = useCallback(() => api<Inbox>("/messages/inbox").then(setBox).catch(() => setBox({ items: [], unread: 0 })), []);
  useEffect(() => { load(); const iv = setInterval(load, 20000); return () => clearInterval(iv); }, [load]);
  const pid = sp.get("project") || box?.items[0]?.project_id || "";
  if (!box) return <Loading />;
  const cur = box.items.find((x) => x.project_id === pid);
  return (
    <div className="col gap-16">
      <div><h1>{t("msg.title")}</h1><p className="muted" style={{ margin: 0 }}>{t("msg.lead")}</p></div>
      {!box.items.length && !sp.get("project") ? <Empty><MessagesSquare size={22} /> {t("msg.inbox_empty")}</Empty> : (
        <div className="msg-grid">
          <aside className="card col" aria-label={t("msg.title")}>
            {box.items.map((x) => <button key={x.project_id} className={`inbox-row ${x.project_id === pid ? "on" : ""}`} onClick={() => { setSp({ project: x.project_id }); setTimeout(load, 500); }}>
              <div className="row between"><b className="small">{x.title}</b>{x.unread > 0 && <Badge tone="terra">{x.unread}</Badge>}</div>
              <div className="tiny muted clamp2">{x.last.author}: {x.last.body}</div>
              <div className="tiny muted">{dt(x.last.at)}</div>
            </button>)}
          </aside>
          <section className="card col">
            <div className="row between" style={{ padding: "12px 14px", borderBottom: "1px solid var(--line)" }}>
              <b>{cur?.title || ""}{cur?.client_name ? <span className="muted small"> · {cur.client_name}</span> : null}</b>
              {pid && <Link className="btn sm" to={`/app/p/${pid}`}>{t("dash.open")}</Link>}</div>
            {pid ? <ProjectChat key={pid} pid={pid} height={560} /> : null}
          </section>
        </div>)}
    </div>
  );
}
