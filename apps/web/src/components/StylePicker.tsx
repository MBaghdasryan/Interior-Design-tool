import { useEffect, useMemo, useState } from "react";
import { Check, Plus, Search, X } from "lucide-react";
import { api } from "../lib/api";
import { useT } from "../i18n";

export interface StyleDef { key: string; group: string; palette: string[] }
const GROUPS = ["modern", "classic", "ethnic", "mixed"];
export const MAX_STYLES = 3;  // the generator builds three variants

let cache: StyleDef[] | null = null;
export function useStyles(): StyleDef[] {
  const [s, setS] = useState<StyleDef[]>(cache || []);
  useEffect(() => {
    if (cache) return;
    api<{ styles: StyleDef[] }>("/catalog/taxonomy").then((x) => { cache = x.styles; setS(x.styles); }).catch(() => {});
  }, []);
  return s;
}

/** All interior styles grouped as in the brief (modern, classic & historic, ethnic, mixed); up to three at once. */
export function StylePicker({ value, onChange }: { value: string[]; onChange: (v: string[]) => void }) {
  const { t } = useT();
  const styles = useStyles();
  const [group, setGroup] = useState("modern");
  const [q, setQ] = useState("");
  const shown = useMemo(() => {
    const needle = q.trim().toLowerCase();
    return styles.filter((s) => (needle ? `${t(`enum.style.${s.key}`)} ${t(`enum.style_sub.${s.key}`)}`.toLowerCase().includes(needle) : s.group === group));
  }, [styles, group, q, t]);
  const toggle = (k: string) => onChange(value.includes(k) ? value.filter((x) => x !== k) : value.length >= MAX_STYLES ? [...value.slice(1), k] : [...value, k]);
  return (
    <div className="col gap-8">
      <label className="row gap-4 input" style={{ height: 36 }}><Search size={15} /><input aria-label={t("sty.search")} placeholder={t("sty.search")} value={q} onChange={(e) => setQ(e.target.value)} style={{ border: 0, outline: 0, background: "transparent", width: "100%" }} /></label>
      {!q && <div className="row gap-4 wrap">{GROUPS.map((g) => <button key={g} type="button" className={`chip ${group === g ? "on" : ""}`} aria-pressed={group === g} onClick={() => setGroup(g)}>{t(`enum.style_group.${g}`)}</button>)}</div>}
      <div className="style-grid">
        {shown.map((s) => {
          const on = value.includes(s.key);
          return (
            <button key={s.key} type="button" className={`style-tile ${on ? "on" : ""}`} aria-pressed={on} title={t(`enum.style_sub.${s.key}`)} onClick={() => toggle(s.key)}>
              <div className="img sw">{s.palette.slice(0, 5).map((c) => <i key={c} style={{ background: c }} />)}{on && <span className="tick"><Check size={12} /></span>}</div>
              <div className="tiny" style={{ padding: "4px 2px", fontWeight: 600 }}>{t(`enum.style.${s.key}`)}</div>
              <div className="tiny muted" style={{ padding: "0 2px 4px" }}>{t(`enum.style_sub.${s.key}`)}</div>
            </button>);
        })}
      </div>
      <div className="tiny muted">{value.length ? t("sty.chosen", { n: value.length, max: MAX_STYLES }) + ": " + value.map((k) => t(`enum.style.${k}`)).join(", ") : t("sty.none")}</div>
    </div>
  );
}

// a broad palette by colour family; any other colour is added with the picker — the choice is not limited
const SWATCHES = [
  "#ffffff", "#f6f1e7", "#efe6da", "#e8dccb", "#d9c9b7", "#c8b08f", "#b98f6a", "#8a5a3c", "#5b3a23", "#2e2e2e", "#1c1c1c",
  "#f1efea", "#e3e1dc", "#c9c6c1", "#9c9a95", "#6f6c67", "#3f3d3a",
  "#f2d7dd", "#e8a0a8", "#c96f7a", "#a3201c", "#7a1f2b", "#f3c9b6", "#e09a7a", "#c97f63", "#a65e45", "#c96a3a",
  "#fbf0c9", "#f9c80e", "#e0a32e", "#d9a441", "#c9a14a", "#b08d57",
  "#e7ecdf", "#cdd6c1", "#a9b892", "#8f9f7e", "#6b7a4f", "#4b5d47", "#3f4a32", "#0f4c4a", "#3dbfa4",
  "#e1ebf4", "#cfe3ef", "#9fc3dd", "#5f8fb5", "#2f6fa8", "#1f3a5f", "#2b2d42", "#00a8e8",
  "#ece4f2", "#c9b8d6", "#9b84b8", "#5e4b7a",
];

/** Unlimited colour choice: a wide palette, any custom colour, or the palette of the chosen styles. */
export function ColorPicker({ value, onChange, styles = [] }: { value: string[]; onChange: (v: string[]) => void; styles?: string[] }) {
  const { t } = useT();
  const all = useStyles();
  const [custom, setCustom] = useState("#c97f63");
  const toggle = (c: string) => onChange(value.includes(c) ? value.filter((x) => x !== c) : [...value, c]);
  const fromStyles = all.filter((s) => styles.includes(s.key)).flatMap((s) => s.palette);
  return (
    <div className="col gap-8">
      <div className="swatch-grid">{SWATCHES.map((c) => <button key={c} type="button" className={`swatch ${value.includes(c) ? "on" : ""}`} style={{ background: c }} onClick={() => toggle(c)} aria-label={c} aria-pressed={value.includes(c)} />)}</div>
      <div className="row gap-6 wrap">
        <label className="row gap-6 small"><input type="color" value={custom} onChange={(e) => setCustom(e.target.value)} aria-label={t("sty.custom")} style={{ width: 40, height: 32, border: 0, background: "none", padding: 0 }} />
          <button type="button" className="btn sm" onClick={() => !value.includes(custom) && onChange([...value, custom])}><Plus size={14} /> {t("sty.add_color")}</button></label>
        {fromStyles.length > 0 && <button type="button" className="btn sm ghost" onClick={() => onChange([...new Set([...value, ...fromStyles])])}>{t("sty.from_styles")}</button>}
        {value.length > 0 && <button type="button" className="btn sm ghost" onClick={() => onChange([])}>{t("sty.clear")}</button>}
      </div>
      {value.length > 0 && <div className="row gap-4 wrap">{value.map((c) => <span key={c} className="color-chip"><i style={{ background: c }} />{c}<button type="button" aria-label={`${t("common.delete")} ${c}`} onClick={() => toggle(c)}><X size={12} /></button></span>)}</div>}
      <div className="tiny muted">{t("sty.colors_hint")}</div>
    </div>
  );
}
