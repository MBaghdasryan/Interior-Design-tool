// Locale-aware formatting. Amounts are numbers end-to-end; only the view formats them.
import { getLang, LANGS, translate, type Lang } from "../i18n";

const loc = (l: Lang = getLang()) => LANGS.find((x) => x.code === l)!.locale;
const num = (v: number, digits = 0) => new Intl.NumberFormat(loc(), { maximumFractionDigits: digits, minimumFractionDigits: digits }).format(v);

export const amd = (v: number | null | undefined, unit: string | null = null) =>
  v === null || v === undefined ? "—" : `${num(Math.round(v))}${unit === null ? ` ${translate("common.amd")}` : unit}`;
export const pct = (v: number | null | undefined) => (v === null || v === undefined ? "—" : new Intl.NumberFormat(loc(), { style: "percent", maximumFractionDigits: 0 }).format(v));
export const m2 = (v: number | null | undefined) => (v === null || v === undefined ? "—" : `${num(v, 1)} ${translate("common.m2")}`);
export const mm = (v: number) => `${num(Math.round(v))} ${translate("common.mm")}`;
export const n1 = (v: number) => num(v, 1);
export const kb = (b: number) => (b > 1024 * 1024 ? `${num(b / 1024 / 1024, 1)} ${translate("common.mb")}` : `${num(Math.max(1, Math.round(b / 1024)))} ${translate("common.kb")}`);
export const dt = (s?: string | null) => (s ? new Date(s).toLocaleString(loc(), { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" }) : "—");

// Enumerations → dictionary keys (see i18n/dict/enums.ts)
export const styleName = (k: string) => translate(`enum.style.${k}`);
export const styleSubtitle = (k: string) => translate(`enum.style_sub.${k}`);
export const tierName = (k: string) => translate(`enum.tier.${k}`);
export const catName = (k: string) => translate(`enum.cat.${k}`);
export const roomType = (k: string) => translate(`enum.room.${k}`);
export const roleName = (k: string) => translate(`enum.role.${k}`);

export const ACCURACY_TONE: Record<string, string> = { concept: "warn", verified: "info", production: "sage" };
export const PRICE_TONE: Record<string, string> = { confirmed: "sage", estimated: "info", quote_required: "warn", demo: "danger", concept: "" };
export const GROUP_COLORS: Record<string, string> = {
  furniture: "#b8694c", custom: "#d9a27f", lighting: "#e2b04a", plumbing: "#4f7da3", finishing: "#2e2e2e", doors: "#8f9f7e", appliances: "#6e5a4b",
  decor: "#c8b5a0", works: "#a39a8f", delivery: "#cfc6bb", installation: "#7a8d6a", contingency: "#e6ddd2",
};

/** Localised estimate line name: works/delivery/installation/contingency are system lines. */
export function lineName(l: { group: string; category: string; name: string; supplier?: string }) {
  if (l.group === "works") return translate(`works.${l.category}`);
  if (l.group === "delivery") return translate("estimate.line_delivery", { supplier: l.supplier || "" });
  if (l.group === "installation") return translate("estimate.line_installation", { supplier: l.supplier || "" });
  if (l.group === "contingency") return translate("estimate.line_contingency");
  return l.name;
}

/** Variant titles are built from stable keys (style + tier), never from server text. */
export function variantTitle(v: { key: string; style: string }) {
  const tier = ["economy", "optimal", "premium"].includes(v.key) ? ` · ${translate(`enum.tier.${v.key}`)}` : "";
  return `${styleName(v.style)}${tier}`;
}
export function variantSubtitle(v: { key: string; style: string }) {
  return translate(`enum.style_sub.${v.key === "economy" || v.key === "premium" ? v.key : v.style}`);
}
