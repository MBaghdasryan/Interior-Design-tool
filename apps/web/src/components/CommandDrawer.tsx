import { useState } from "react";
import { Check, Mic, MicOff, Sparkles, X } from "lucide-react";
import { api, type Diff } from "../lib/api";
import { amd, catName, roomType } from "../lib/format";
import { useT } from "../i18n";
import { Badge, Drawer, useToast } from "./ui";

interface Preview { plan: { operations: { op: string; room_type?: string; category?: string; params: Record<string, unknown>; explanation: string }[]; summary: string; unsupported: string[] };
  provider: string; applied: { op: string; room_id?: string; category?: string; to?: string; saving?: number }[]; skipped: { op: string; reason: string }[]; diff: Diff; total_after: number; issues_after: { block: number; warning: number } }

const SUGGEST = ["lighter_kitchen", "compact_sofa", "closed_wardrobe_hall", "cut_budget", "premium_tile", "remove_rug"];
const SPEECH: Record<string, string> = { hy: "hy-AM", ru: "ru-RU", en: "en-US" };

export default function CommandDrawer({ open, onClose, pid, vid, onApplied }: { open: boolean; onClose: () => void; pid: string; vid: string; onApplied: () => void }) {
  const { t, lang } = useT();
  const [cmd, setCmd] = useState("");
  const [busy, setBusy] = useState(false);
  const [pv, setPv] = useState<Preview | null>(null);
  const [listening, setListening] = useState(false);
  const toast = useToast();
  const preview = async () => {
    setBusy(true); setPv(null);
    try { setPv(await api<Preview>(`/projects/${pid}/variants/${vid}/command`, { method: "POST", json: { command: cmd } })); } catch (x) { toast((x as Error).message, true); }
    setBusy(false);
  };
  const apply = async () => {
    setBusy(true);
    try { await api(`/projects/${pid}/variants/${vid}/command`, { method: "POST", json: { command: cmd, apply: true, plan: pv?.plan } }); toast(t("cmd.version_created")); setPv(null); setCmd(""); onApplied(); onClose(); }
    catch (x) { toast((x as Error).message, true); }
    setBusy(false);
  };
  const voice = () => {
    const SR = (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition;
    if (!SR) { toast(t("cmd.voice_unsupported"), true); return; }
    const r = new SR();
    r.lang = SPEECH[lang]; r.interimResults = false;
    r.onresult = (e: any) => setCmd((c) => (c ? c + ", " : "") + e.results[0][0].transcript);
    r.onend = () => setListening(false);
    setListening(true); r.start();
  };
  return (
    <Drawer open={open} onClose={onClose} title={<span className="row"><Sparkles size={18} color="var(--terra-ink)" /> {t("cta.ai_change")}</span>}
      footer={pv ? <><button className="btn" onClick={() => setPv(null)}>{t("common.cancel")}</button><button className="btn primary" disabled={busy || !pv.applied.length} onClick={apply}><Check size={16} /> {t("cmd.apply")}</button></> :
        <button className="btn primary" disabled={busy || cmd.length < 3} onClick={preview}>{busy ? <span className="spinner" /> : <Sparkles size={16} />} {t("cmd.preview")}</button>}>
      <p className="muted small">{t("cmd.intro")}</p>
      <div className="row top mt-16">
        <textarea className="input grow" rows={4} value={cmd} onChange={(e) => setCmd(e.target.value)} placeholder={t("cmd.placeholder")} />
        <button className="icon-btn" onClick={voice} aria-label={t("cmd.voice")} title={t("cmd.voice")}>{listening ? <MicOff size={18} /> : <Mic size={18} />}</button>
      </div>
      <div className="row wrap mt-8">{SUGGEST.map((s) => <button key={s} className="chip" onClick={() => setCmd((c) => (c ? `${c}, ${t(`cmd.s.${s}`).toLowerCase()}` : t(`cmd.s.${s}`)))}>{t(`cmd.s.${s}`)}</button>)}</div>
      {lang !== "ru" && <p className="tiny muted mt-8">{t("cmd.lang_note")}</p>}
      {pv && (
        <div className="col gap-10 mt-24">
          <div className="row between"><h3>{t("cmd.plan")}</h3><Badge tone={pv.provider === "stub" ? "warn" : "info"}>{pv.provider === "stub" ? t("cmd.deterministic") : pv.provider}</Badge></div>
          {pv.plan.operations.map((o, i) => <div key={i} className="row small wrap"><Badge tone="terra">{t(`cmd.op.${o.op}`)}</Badge>{o.room_type && <Badge>{roomType(o.room_type)}</Badge>}{o.category && <Badge>{catName(o.category)}</Badge>}
            {o.params?.delta_amd ? <span className="mono">{amd(Number(o.params.delta_amd))}</span> : null}</div>)}
          <div className="divider" />
          <b>{t("cmd.will_do", { n: pv.applied.length })}</b>
          {pv.applied.map((a, i) => <div key={i} className="small row"><Check size={14} color="var(--sage-ink)" /> {t(`cmd.op.${a.op}`)}: {a.category ? catName(a.category) : ""} → {a.to || ""} {a.saving ? <span className="muted">(−{amd(a.saving)})</span> : null}</div>)}
          {pv.skipped.map((s, i) => <div key={`s${i}`} className="small row" style={{ color: "#8a5d00" }}><X size={14} /> {s.op === "unsupported" ? t("cmd.unsupported", { text: s.reason }) : t("cmd.skipped", { op: t(`cmd.op.${s.op}`) })}</div>)}
          <div className="divider" />
          <div className="grid g3 small">
            <div><div className="muted">{t("cmd.added_removed")}</div><b>{pv.diff.added.length} / {pv.diff.removed.length}</b></div>
            <div><div className="muted">{t("cmd.changed_moved")}</div><b>{pv.diff.changed.length} / {pv.diff.moved.length}</b></div>
            <div><div className="muted">{t("cmd.estimate_delta")}</div><b className="mono" style={{ color: pv.diff.total_delta <= 0 ? "var(--sage-ink)" : "var(--danger)" }}>{pv.diff.total_delta > 0 ? "+" : ""}{amd(pv.diff.total_delta)}</b></div>
          </div>
          <div className="small muted">{t("cmd.after_issues", { rooms: pv.diff.rooms_affected.length, block: pv.issues_after.block, warning: pv.issues_after.warning })}</div>
        </div>
      )}
    </Drawer>
  );
}
