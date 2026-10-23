import { useEffect, useRef, useState } from "react";
import { Globe2, Palette, Trash2, Upload } from "lucide-react";
import { api } from "../lib/api";
import { DICT } from "../i18n/dict";
import { useT } from "../i18n";
import { Badge, Loading, useToast } from "../components/ui";

interface B { display_name: string; accent_hex: string; logo_url: string | null; domain: string; domain_status: string; doc_lang: string; allowed: boolean }

/** Organisation settings (mockup 33): brand on client links and albums (white label), languages. */
export default function OrgSettings() {
  const { t } = useT();
  const toast = useToast();
  const [tab, setTab] = useState<"brand" | "languages">("brand");
  const [b, setB] = useState<B | null>(null);
  const file = useRef<HTMLInputElement>(null);
  useEffect(() => { api<B>("/bureau/branding").then(setB).catch((e) => toast((e as Error).message, true)); }, [toast]);
  if (!b) return <Loading />;
  const save = async () => { try { setB(await api<B>("/bureau/branding", { method: "PUT", json: { display_name: b.display_name, accent_hex: b.accent_hex, domain: b.domain, doc_lang: b.doc_lang } })); toast(t("mg.saved")); } catch (x) { toast((x as Error).message, true); } };
  const upload = async (f: File) => { const fd = new FormData(); fd.append("file", f); try { setB(await api<B>("/bureau/branding/logo", { method: "POST", body: fd })); } catch (x) { toast((x as Error).message, true); } };
  const keys = Object.keys(DICT);
  const cover = (l: "hy" | "ru" | "en") => Math.round((keys.filter((k) => (DICT[k] as Record<string, string>)[l]?.trim()).length / keys.length) * 1000) / 10;
  const accent = b.accent_hex || "#93492f";
  return (
    <div className="col gap-16">
      <div className="row between wrap gap-12"><div><h1>{t("os.title")}</h1><p className="muted" style={{ margin: 0 }}>{t("os.lead")}</p></div>
        <button className="btn primary lg" onClick={save} disabled={!b.allowed}>{t("common.save")}</button></div>
      <div className="tabs" role="tablist">{(["brand", "languages"] as const).map((k) => <button key={k} role="tab" aria-selected={tab === k} className={`tab ${tab === k ? "on" : ""}`} onClick={() => setTab(k)}>{t(`os.tab.${k}`)}</button>)}</div>
      {!b.allowed && <div className="alert warn small">{t("errors.plan.feature_unavailable")}</div>}
      {tab === "brand" ? <div className="grid g2" style={{ alignItems: "start" }}>
        <section className="card pad col gap-12">
          <h3 className="row gap-6"><Palette size={18} /> {t("os.brand")}</h3>
          <div className="row gap-12 wrap" style={{ alignItems: "center" }}>
            <div className="logo-box">{b.logo_url ? <img src={b.logo_url} alt={t("os.logo")} /> : <span className="tiny muted">{t("os.no_logo")}</span>}</div>
            <div className="col gap-6">
              <input ref={file} type="file" hidden accept="image/png,image/jpeg,image/webp" aria-label={t("os.logo")} onChange={(e) => e.target.files?.[0] && upload(e.target.files[0])} />
              <button className="btn sm" disabled={!b.allowed} onClick={() => file.current?.click()}><Upload size={14} /> {t("os.change_logo")}</button>
              {b.logo_url && <button className="btn sm danger" onClick={async () => setB(await api<B>("/bureau/branding/logo", { method: "DELETE" }))}><Trash2 size={14} /> {t("common.delete")}</button>}
              <span className="tiny muted">{t("os.logo_hint")}</span>
            </div>
          </div>
          <label className="field"><span>{t("os.display_name")}</span><input className="input" value={b.display_name} onChange={(e) => setB({ ...b, display_name: e.target.value })} /></label>
          <label className="field"><span>{t("os.accent")}</span><div className="row gap-6"><input type="color" value={accent} onChange={(e) => setB({ ...b, accent_hex: e.target.value })} aria-label={t("os.accent")} style={{ width: 44, height: 36, border: 0, background: "none" }} />
            <input className="input mono" style={{ width: 120 }} value={b.accent_hex} placeholder="#93492f" onChange={(e) => setB({ ...b, accent_hex: e.target.value })} />
            {b.accent_hex && <button className="btn sm ghost" onClick={() => setB({ ...b, accent_hex: "" })}>{t("os.reset")}</button>}</div></label>
          <label className="field"><span className="row gap-6"><Globe2 size={14} /> {t("os.domain")}</span><input className="input mono" placeholder="design.yourstudio.am" value={b.domain} onChange={(e) => setB({ ...b, domain: e.target.value.trim().toLowerCase() })} /></label>
          {b.domain && <div className="row gap-6 small"><Badge tone="warn">{t(`os.domain_status.${b.domain_status || "pending"}`)}</Badge><span className="tiny muted">{t("os.domain_hint")}</span></div>}
        </section>
        <section className="card pad col gap-10">
          <h3>{t("os.preview")}</h3>
          <div className="wl-preview" style={{ ["--wl" as string]: accent }}>
            <div className="wl-head">{b.logo_url ? <img src={b.logo_url} alt="" /> : <b>{b.display_name || "—"}</b>}<span className="tiny muted">{t("os.preview_portal")}</span></div>
            <div className="wl-body"><b>{t("os.preview_project")}</b><div className="row gap-6 mt-8"><span className="wl-btn">{t("cv.approve")}</span><span className="wl-btn ghost">{t("cv.changes")}</span></div></div>
          </div>
          <p className="tiny muted" style={{ margin: 0 }}>{t("os.where")}</p>
        </section>
      </div> : <section className="card pad col gap-10">
        <h3>{t("os.languages")}</h3>
        {(["hy", "ru", "en"] as const).map((l) => <div key={l} className="row gap-12"><b style={{ width: 120 }}>{t(`os.lang.${l}`)}</b><div className="bar grow"><i style={{ width: `${cover(l)}%` }} /></div><span className="mono small">{cover(l)}%</span></div>)}
        <p className="tiny muted" style={{ margin: 0 }}>{t("os.coverage_hint", { n: keys.length })}</p>
        <label className="field" style={{ maxWidth: 320 }}><span>{t("os.doc_lang")}</span><select className="select input" value={b.doc_lang} onChange={(e) => setB({ ...b, doc_lang: e.target.value })}>
          {(["hy", "ru", "en"] as const).map((l) => <option key={l} value={l}>{t(`os.lang.${l}`)}</option>)}</select></label>
      </section>}
    </div>
  );
}
