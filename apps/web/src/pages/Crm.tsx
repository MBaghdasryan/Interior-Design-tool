import { useCallback, useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { CalendarClock, FolderPlus, LayoutGrid, List, Phone, Plus, Search, Target, Trash2, Users, Wallet } from "lucide-react";
import { api } from "../lib/api";
import { amd, dt } from "../lib/format";
import { useT } from "../i18n";
import { Badge, Drawer, Empty, Kpi, Loading, useToast } from "../components/ui";

interface Client { id: string; name: string; phone: string; email: string; source: string; stage: string; budget_amd: number | null; area_m2: number | null; address: string; notes: string;
  owner_id: string | null; owner_name: string; next_action: string; next_action_at: string | null; lost_reason: string; created_at: string; updated_at: string; projects: number; open_tasks: number }
interface Detail extends Client { activities: { id: string; kind: string; body: string; user: string; at: string }[]; project_list: { id: string; title: string; status: string }[];
  tasks: { id: string; title: string; status: string; due_at: string | null; overdue: boolean; assignee_name: string }[] }
interface List_ { items: Client[]; counts: Record<string, number>; pipeline_amd: number; conversion: number | null; stages: string[]; sources: string[]; members: { id: string; name: string }[] }
const FUNNEL = ["lead", "contacted", "brief", "proposal", "contract", "in_work"];
const BLANK = { name: "", phone: "", email: "", source: "other", stage: "lead", budget_amd: "", area_m2: "", address: "", notes: "", next_action: "", next_action_at: "" };

/** CRM: clients of the bureau and the deal funnel (mockups 05 and 14). */
export default function Crm() {
  const { t } = useT();
  const toast = useToast();
  const nav = useNavigate();
  const [d, setD] = useState<List_ | null>(null);
  const [view, setView] = useState<"board" | "list">("board");
  const [q, setQ] = useState("");
  const [mine, setMine] = useState(false);
  const [open, setOpen] = useState<Detail | null>(null);
  const [form, setForm] = useState<typeof BLANK | null>(null);
  const [note, setNote] = useState({ kind: "note", body: "" });
  const load = useCallback(() => api<List_>(`/crm/clients?${new URLSearchParams({ q, ...(mine ? { owner: "me" } : {}) })}`).then(setD).catch((e) => toast((e as Error).message, true)), [q, mine, toast]);
  useEffect(() => { const tm = setTimeout(load, 200); return () => clearTimeout(tm); }, [load]);
  const run = async (fn: () => Promise<unknown>) => { try { await fn(); load(); } catch (x) { toast((x as Error).message, true); } };
  const show = async (id: string) => setOpen(await api<Detail>(`/crm/clients/${id}`));
  const move = (c: Client, stage: string) => run(async () => { await api(`/crm/clients/${c.id}`, { method: "PATCH", json: { stage } }); if (open?.id === c.id) await show(c.id); });
  const create = () => form && run(async () => {
    await api("/crm/clients", { method: "POST", json: { ...form, budget_amd: form.budget_amd ? Number(form.budget_amd) : null, area_m2: form.area_m2 ? Number(form.area_m2) : null,
      next_action_at: form.next_action_at ? new Date(form.next_action_at).toISOString() : null } });
    setForm(null); toast(t("crm.saved"));
  });
  if (!d) return <Loading />;
  const byStage = (s: string) => d.items.filter((c) => c.stage === s);
  const leads = FUNNEL.reduce((n, s) => n + (d.counts[s] || 0), 0);
  return (
    <div className="col gap-16">
      <div className="row between wrap gap-12"><div><h1>{t("crm.title")}</h1><p className="muted" style={{ margin: 0 }}>{t("crm.lead")}</p></div>
        <button className="btn primary lg" onClick={() => setForm({ ...BLANK })}><Plus size={18} /> {t("crm.add")}</button></div>
      <div className="grid g4">
        <Kpi icon={<Users size={20} />} value={leads} label={t("crm.k.open")} />
        <Kpi icon={<Wallet size={20} />} value={amd(d.pipeline_amd)} label={t("crm.k.pipeline")} />
        <Kpi icon={<Target size={20} />} value={d.conversion == null ? "—" : `${Math.round(d.conversion * 100)}%`} label={t("crm.k.conversion")} />
        <Kpi icon={<CalendarClock size={20} />} value={d.items.filter((c) => c.next_action_at && new Date(c.next_action_at) < new Date(Date.now() + 864e5)).length} label={t("crm.k.today")} />
      </div>
      <div className="row between wrap gap-8">
        <div className="row gap-6">
          <label className="row gap-4 input" style={{ height: 38, minWidth: 260 }}><Search size={15} /><input aria-label={t("common.search")} placeholder={t("crm.search")} value={q} onChange={(e) => setQ(e.target.value)} style={{ border: 0, outline: 0, background: "transparent", width: "100%" }} /></label>
          <button className={`chip ${mine ? "on" : ""}`} aria-pressed={mine} onClick={() => setMine(!mine)}>{t("crm.mine")}</button>
        </div>
        <div className="seg" role="group"><button className={view === "board" ? "on" : ""} onClick={() => setView("board")}><LayoutGrid size={14} /> {t("crm.board")}</button><button className={view === "list" ? "on" : ""} onClick={() => setView("list")}><List size={14} /> {t("crm.list")}</button></div>
      </div>
      {!d.items.length && !q ? <Empty>{t("crm.empty")}</Empty> : view === "board" ? (
        <div className="kanban">
          {[...FUNNEL, "done", "lost"].map((s) => <section key={s} className="kcol" aria-label={t(`crm.stage.${s}`)}>
            <div className="row between"><b className="small">{t(`crm.stage.${s}`)}</b><Badge>{d.counts[s] || 0}</Badge></div>
            <div className="tiny muted">{amd(byStage(s).reduce((n, c) => n + (c.budget_amd || 0), 0))}</div>
            {byStage(s).map((c) => <article key={c.id} className="kcard" onClick={() => show(c.id)} tabIndex={0} onKeyDown={(e) => e.key === "Enter" && show(c.id)}>
              <b className="small">{c.name}</b>
              <div className="tiny muted">{[c.budget_amd ? amd(c.budget_amd) : "", c.area_m2 ? `${c.area_m2} ${t("common.m2")}` : "", t(`crm.src.${c.source}`)].filter(Boolean).join(" · ")}</div>
              {c.next_action && <div className={`tiny ${c.next_action_at && new Date(c.next_action_at) < new Date() ? "danger-text" : ""}`}><CalendarClock size={12} /> {c.next_action}{c.next_action_at ? ` · ${dt(c.next_action_at)}` : ""}</div>}
              <div className="row between tiny muted"><span>{c.owner_name}</span><span>{c.projects ? t("crm.n_projects", { n: c.projects }) : ""}</span></div>
              <select className="select input" style={{ height: 30, fontSize: 12 }} aria-label={t("crm.move")} value={c.stage} onClick={(e) => e.stopPropagation()} onChange={(e) => move(c, e.target.value)}>
                {d.stages.map((x) => <option key={x} value={x}>{t(`crm.stage.${x}`)}</option>)}</select>
            </article>)}
          </section>)}
        </div>) : (
        <div className="card" style={{ overflow: "auto" }}><table className="table compact"><thead><tr><th>{t("crm.col.client")}</th><th>{t("crm.col.stage")}</th><th className="right">{t("crm.col.budget")}</th><th>{t("crm.col.next")}</th><th>{t("crm.col.owner")}</th><th>{t("crm.col.updated")}</th></tr></thead>
          <tbody>{d.items.map((c) => <tr key={c.id} onClick={() => show(c.id)} style={{ cursor: "pointer" }}><td><b className="small">{c.name}</b><div className="tiny muted">{c.phone} {c.email}</div></td>
            <td><Badge tone={c.stage === "lost" ? "danger" : c.stage === "done" ? "sage" : "info"}>{t(`crm.stage.${c.stage}`)}</Badge></td><td className="right mono small">{c.budget_amd ? amd(c.budget_amd) : "—"}</td>
            <td className="small">{c.next_action}{c.next_action_at ? <div className="tiny muted">{dt(c.next_action_at)}</div> : null}</td><td className="small">{c.owner_name}</td><td className="tiny muted">{dt(c.updated_at)}</td></tr>)}</tbody></table></div>)}

      <Drawer open={!!open} onClose={() => setOpen(null)} title={open?.name || ""}>
        {open && <div className="col gap-12">
          <div className="small"><Phone size={13} /> {open.phone || "—"} · {open.email || "—"}</div>
          <div className="grid g2">
            <label className="field"><span>{t("crm.col.stage")}</span><select className="select input" value={open.stage} onChange={(e) => move(open, e.target.value)}>{d.stages.map((x) => <option key={x} value={x}>{t(`crm.stage.${x}`)}</option>)}</select></label>
            <label className="field"><span>{t("crm.col.owner")}</span><select className="select input" value={open.owner_id || ""} onChange={(e) => run(async () => { await api(`/crm/clients/${open.id}`, { method: "PATCH", json: { owner_id: e.target.value || null } }); await show(open.id); })}>
              {d.members.map((mb) => <option key={mb.id} value={mb.id}>{mb.name}</option>)}</select></label>
          </div>
          <div className="small muted">{[open.budget_amd ? amd(open.budget_amd) : "", open.area_m2 ? `${open.area_m2} ${t("common.m2")}` : "", open.address].filter(Boolean).join(" · ")}</div>
          {open.notes && <p className="small" style={{ margin: 0 }}>{open.notes}</p>}
          <label className="field"><span>{t("crm.col.next")}</span><input className="input" defaultValue={open.next_action} onBlur={(e) => e.target.value !== open.next_action && run(() => api(`/crm/clients/${open.id}`, { method: "PATCH", json: { next_action: e.target.value } }))} /></label>
          <div className="divider" />
          <div className="row between"><b>{t("crm.projects")}</b><button className="btn sm" onClick={() => run(async () => { const r = await api<{ project_id: string }>(`/crm/clients/${open.id}/projects`, { method: "POST", json: { title: "" } }); nav(`/app/p/${r.project_id}/upload`); })}><FolderPlus size={14} /> {t("crm.new_project")}</button></div>
          {open.project_list.map((p) => <Link key={p.id} to={`/app/p/${p.id}`} className="row between small"><span>{p.title}</span><Badge>{t(`enum.project_status.${p.status}`)}</Badge></Link>)}
          {open.tasks.length > 0 && <><b>{t("nav.tasks")}</b>{open.tasks.map((x) => <div key={x.id} className="row between small"><span>{x.title}</span><Badge tone={x.overdue ? "danger" : ""}>{t(`task.status.${x.status}`)}</Badge></div>)}</>}
          <div className="divider" />
          <b>{t("crm.history")}</b>
          <div className="row gap-6"><select className="select input" style={{ width: 130 }} aria-label={t("crm.kind")} value={note.kind} onChange={(e) => setNote({ ...note, kind: e.target.value })}>{["note", "call", "meeting"].map((k) => <option key={k} value={k}>{t(`crm.act.${k}`)}</option>)}</select>
            <input className="input grow" aria-label={t("crm.add_note")} placeholder={t("crm.add_note")} value={note.body} onChange={(e) => setNote({ ...note, body: e.target.value })} />
            <button className="btn sm primary" disabled={!note.body.trim()} onClick={() => run(async () => { setOpen(await api<Detail>(`/crm/clients/${open.id}/activities`, { method: "POST", json: note })); setNote({ kind: "note", body: "" }); })}>{t("common.save")}</button></div>
          {open.activities.map((a) => <div key={a.id} className="small"><Badge>{t(`crm.act.${a.kind}`)}</Badge> {a.kind === "stage" ? a.body.split("→").map((x) => t(`crm.stage.${x}`)).join(" → ") : a.body} <span className="tiny muted">· {a.user} · {dt(a.at)}</span></div>)}
          <div className="divider" />
          <button className="btn sm danger" onClick={() => confirm(t("crm.confirm_delete", { name: open.name })) && run(async () => { await api(`/crm/clients/${open.id}`, { method: "DELETE" }); setOpen(null); })}><Trash2 size={14} /> {t("crm.delete")}</button>
        </div>}
      </Drawer>

      <Drawer open={!!form} onClose={() => setForm(null)} title={t("crm.add")} footer={<div className="row gap-6"><button className="btn primary" disabled={!form?.name.trim()} onClick={create}>{t("common.save")}</button><button className="btn ghost" onClick={() => setForm(null)}>{t("common.cancel")}</button></div>}>
        {form && <div className="col gap-10">
          {(["name", "phone", "email", "address"] as const).map((k) => <label key={k} className="field"><span>{t(`crm.f.${k}`)}{k === "name" ? " *" : ""}</span><input className="input" value={form[k]} onChange={(e) => setForm({ ...form, [k]: e.target.value })} /></label>)}
          <div className="grid g2">
            <label className="field"><span>{t("crm.f.source")}</span><select className="select input" value={form.source} onChange={(e) => setForm({ ...form, source: e.target.value })}>{d.sources.map((s) => <option key={s} value={s}>{t(`crm.src.${s}`)}</option>)}</select></label>
            <label className="field"><span>{t("crm.col.stage")}</span><select className="select input" value={form.stage} onChange={(e) => setForm({ ...form, stage: e.target.value })}>{d.stages.map((s) => <option key={s} value={s}>{t(`crm.stage.${s}`)}</option>)}</select></label>
            <label className="field"><span>{t("crm.f.budget")}</span><input className="input" inputMode="numeric" value={form.budget_amd} onChange={(e) => setForm({ ...form, budget_amd: e.target.value.replace(/\D/g, "") })} /></label>
            <label className="field"><span>{t("crm.f.area")}</span><input className="input" inputMode="decimal" value={form.area_m2} onChange={(e) => setForm({ ...form, area_m2: e.target.value })} /></label>
          </div>
          <label className="field"><span>{t("crm.col.next")}</span><input className="input" value={form.next_action} onChange={(e) => setForm({ ...form, next_action: e.target.value })} /></label>
          <label className="field"><span>{t("crm.f.next_at")}</span><input className="input" type="datetime-local" value={form.next_action_at} onChange={(e) => setForm({ ...form, next_action_at: e.target.value })} /></label>
          <label className="field"><span>{t("crm.f.notes")}</span><textarea className="input" rows={3} value={form.notes} onChange={(e) => setForm({ ...form, notes: e.target.value })} /></label>
        </div>}
      </Drawer>
    </div>
  );
}
