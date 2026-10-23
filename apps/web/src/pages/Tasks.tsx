import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { AlertTriangle, CalendarClock, CheckCircle2, Clock, ListTodo, Plus, Trash2, Users } from "lucide-react";
import { api } from "../lib/api";
import { dt } from "../lib/format";
import { useT } from "../i18n";
import { Badge, Drawer, Empty, Kpi, Loading, useToast } from "../components/ui";

interface Task { id: string; title: string; description: string; status: string; priority: string; due_at: string | null; overdue: boolean; estimate_h: number | null;
  assignee_id: string | null; assignee_name: string; project_id: string | null; project_title: string; created_at: string }
interface TList { items: Task[]; members: { id: string; name: string }[]; projects: { id: string; title: string }[] }
interface Load { members: { user_id: string; name: string; role: string; todo: number; in_progress: number; review: number; overdue: number; due_week: number; planned_h: number; done_30d: number; projects: number }[]; unassigned: number }
const COLS = ["todo", "in_progress", "review", "done"];
const PRIO: Record<string, string> = { high: "danger", normal: "", low: "info" };
type Form = { id?: string; title: string; description: string; assignee_id: string; status: string; priority: string; due_at: string; estimate_h: string; project_id: string };

/** Tasks board and team workload (mockup 27). */
export default function Tasks() {
  const { t } = useT();
  const toast = useToast();
  const [tab, setTab] = useState<"board" | "workload">("board");
  const [who, setWho] = useState("");
  const [d, setD] = useState<TList | null>(null);
  const [w, setW] = useState<Load | null>(null);
  const [form, setForm] = useState<Form | null>(null);
  const load = useCallback(() => {
    api<TList>(`/tasks?${new URLSearchParams(who ? { assignee: who } : {})}`).then(setD).catch((e) => toast((e as Error).message, true));
    api<Load>("/team/workload").then(setW).catch(() => {});
  }, [who, toast]);
  useEffect(() => { load(); }, [load]);
  const run = async (fn: () => Promise<unknown>) => { try { await fn(); load(); } catch (x) { toast((x as Error).message, true); } };
  const save = () => form && run(async () => {
    const body = { title: form.title, description: form.description, assignee_id: form.assignee_id || null, status: form.status, priority: form.priority,
      due_at: form.due_at ? new Date(form.due_at).toISOString() : null, estimate_h: form.estimate_h ? Number(form.estimate_h) : null, project_id: form.project_id || null };
    await api(form.id ? `/tasks/${form.id}` : "/tasks", { method: form.id ? "PATCH" : "POST", json: body });
    setForm(null);
  });
  const edit = (x: Task) => setForm({ id: x.id, title: x.title, description: x.description, assignee_id: x.assignee_id || "", status: x.status, priority: x.priority,
    due_at: x.due_at ? x.due_at.slice(0, 16) : "", estimate_h: x.estimate_h ? String(x.estimate_h) : "", project_id: x.project_id || "" });
  if (!d) return <Loading />;
  const open = d.items.filter((x) => x.status !== "done");
  return (
    <div className="col gap-16">
      <div className="row between wrap gap-12"><div><h1>{t("task.title")}</h1><p className="muted" style={{ margin: 0 }}>{t("task.lead")}</p></div>
        <button className="btn primary lg" onClick={() => setForm({ title: "", description: "", assignee_id: "", status: "todo", priority: "normal", due_at: "", estimate_h: "", project_id: "" })}><Plus size={18} /> {t("task.add")}</button></div>
      <div className="grid g4">
        <Kpi icon={<ListTodo size={20} />} value={open.length} label={t("task.k.open")} />
        <Kpi icon={<AlertTriangle size={20} />} value={open.filter((x) => x.overdue).length} label={t("task.k.overdue")} />
        <Kpi icon={<CalendarClock size={20} />} value={open.filter((x) => x.due_at && !x.overdue && new Date(x.due_at) < new Date(Date.now() + 7 * 864e5)).length} label={t("task.k.week")} />
        <Kpi icon={<Users size={20} />} value={w?.unassigned ?? 0} label={t("task.k.unassigned")} />
      </div>
      <div className="row between wrap gap-8">
        <div className="tabs" role="tablist">{(["board", "workload"] as const).map((k) => <button key={k} role="tab" aria-selected={tab === k} className={`tab ${tab === k ? "on" : ""}`} onClick={() => setTab(k)}>{t(`task.tab.${k}`)}</button>)}</div>
        {tab === "board" && <select className="select input" aria-label={t("task.f.assignee")} value={who} onChange={(e) => setWho(e.target.value)}>
          <option value="">{t("task.everyone")}</option><option value="me">{t("task.mine")}</option>{d.members.map((m) => <option key={m.id} value={m.id}>{m.name}</option>)}</select>}
      </div>
      {tab === "board" ? (!d.items.length ? <Empty>{t("task.empty")}</Empty> :
        <div className="kanban four">{COLS.map((s) => <section key={s} className="kcol" aria-label={t(`task.status.${s}`)}>
          <div className="row between"><b className="small">{t(`task.status.${s}`)}</b><Badge>{d.items.filter((x) => x.status === s).length}</Badge></div>
          {d.items.filter((x) => x.status === s).map((x) => <article key={x.id} className="kcard" onClick={() => edit(x)} tabIndex={0} onKeyDown={(e) => e.key === "Enter" && edit(x)}>
            <div className="row between"><b className="small">{x.title}</b>{x.priority !== "normal" && <Badge tone={PRIO[x.priority]}>{t(`task.prio.${x.priority}`)}</Badge>}</div>
            {x.project_title && <Link to={`/app/p/${x.project_id}`} className="tiny" onClick={(e) => e.stopPropagation()}>{x.project_title}</Link>}
            <div className="row between tiny"><span className="muted">{x.assignee_name || t("task.nobody")}</span>{x.due_at && <span className={x.overdue ? "danger-text" : "muted"}><Clock size={11} /> {dt(x.due_at)}</span>}</div>
            <select className="select input" style={{ height: 30, fontSize: 12 }} aria-label={t("common.status")} value={x.status} onClick={(e) => e.stopPropagation()}
              onChange={(e) => run(() => api(`/tasks/${x.id}`, { method: "PATCH", json: { status: e.target.value } }))}>{COLS.map((c) => <option key={c} value={c}>{t(`task.status.${c}`)}</option>)}</select>
          </article>)}
        </section>)}</div>
      ) : !w ? <Loading /> : (
        <div className="card" style={{ overflow: "auto" }}><table className="table compact">
          <thead><tr><th>{t("task.col.member")}</th><th className="right">{t("task.status.todo")}</th><th className="right">{t("task.status.in_progress")}</th><th className="right">{t("task.status.review")}</th>
            <th className="right">{t("task.k.overdue")}</th><th className="right">{t("task.k.week")}</th><th className="right">{t("task.col.hours")}</th><th>{t("task.col.load")}</th><th className="right">{t("task.col.done30")}</th><th className="right">{t("task.col.projects")}</th></tr></thead>
          <tbody>{w.members.map((m) => {
            const openN = m.todo + m.in_progress + m.review;
            const load = Math.min(100, (m.planned_h / 40) * 100);  // share of a 40-hour week
            return <tr key={m.user_id}><td><b className="small">{m.name}</b><div className="tiny muted">{t(`enum.role.${m.role}`)}</div></td>
              <td className="right">{m.todo}</td><td className="right">{m.in_progress}</td><td className="right">{m.review}</td>
              <td className="right">{m.overdue ? <Badge tone="danger">{m.overdue}</Badge> : 0}</td><td className="right">{m.due_week}</td><td className="right mono">{m.planned_h}</td>
              <td style={{ minWidth: 140 }}><div className={`bar ${load > 90 ? "terra" : ""}`} title={t("task.load_hint")}><i style={{ width: `${load}%` }} /></div><span className="tiny muted">{openN ? t("task.n_open", { n: openN }) : t("task.free")}</span></td>
              <td className="right"><CheckCircle2 size={12} /> {m.done_30d}</td><td className="right">{m.projects}</td></tr>;
          })}</tbody></table>
          <p className="tiny muted" style={{ padding: "0 12px 10px" }}>{t("task.load_hint")}</p></div>)}

      <Drawer open={!!form} onClose={() => setForm(null)} title={form?.id ? t("task.edit") : t("task.add")}
        footer={<div className="row gap-6"><button className="btn primary" disabled={!form?.title.trim()} onClick={save}>{t("common.save")}</button>
          {form?.id && <button className="btn danger" onClick={() => confirm(t("task.confirm_delete")) && run(async () => { await api(`/tasks/${form.id}`, { method: "DELETE" }); setForm(null); })}><Trash2 size={14} /> {t("common.delete")}</button>}</div>}>
        {form && <div className="col gap-10">
          <label className="field"><span>{t("task.f.title")} *</span><input className="input" value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} /></label>
          <label className="field"><span>{t("task.f.description")}</span><textarea className="input" rows={3} value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} /></label>
          <div className="grid g2">
            <label className="field"><span>{t("task.f.assignee")}</span><select className="select input" value={form.assignee_id} onChange={(e) => setForm({ ...form, assignee_id: e.target.value })}><option value="">{t("task.nobody")}</option>{d.members.map((m) => <option key={m.id} value={m.id}>{m.name}</option>)}</select></label>
            <label className="field"><span>{t("task.f.project")}</span><select className="select input" value={form.project_id} onChange={(e) => setForm({ ...form, project_id: e.target.value })}><option value="">—</option>{d.projects.map((p) => <option key={p.id} value={p.id}>{p.title}</option>)}</select></label>
            <label className="field"><span>{t("common.status")}</span><select className="select input" value={form.status} onChange={(e) => setForm({ ...form, status: e.target.value })}>{COLS.map((c) => <option key={c} value={c}>{t(`task.status.${c}`)}</option>)}</select></label>
            <label className="field"><span>{t("task.f.priority")}</span><select className="select input" value={form.priority} onChange={(e) => setForm({ ...form, priority: e.target.value })}>{["low", "normal", "high"].map((c) => <option key={c} value={c}>{t(`task.prio.${c}`)}</option>)}</select></label>
            <label className="field"><span>{t("task.f.due")}</span><input className="input" type="datetime-local" value={form.due_at} onChange={(e) => setForm({ ...form, due_at: e.target.value })} /></label>
            <label className="field"><span>{t("task.f.hours")}</span><input className="input" inputMode="decimal" value={form.estimate_h} onChange={(e) => setForm({ ...form, estimate_h: e.target.value })} /></label>
          </div>
        </div>}
      </Drawer>
    </div>
  );
}
