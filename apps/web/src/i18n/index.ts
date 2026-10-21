// Single i18n engine for the whole web client.
// Dictionaries live in ./dict/<domain>.ts as { key: { hy, ru, en } } — the type makes every
// language mandatory, so a missing translation is a compile error, not a runtime raw key.
import { useSyncExternalStore } from "react";
import { DICT } from "./dict";

export type Lang = "hy" | "ru" | "en";
export type Entry = Record<Lang, string>;
export type Dict = Record<string, Entry>;
// Endonyms are intentionally not translated (each language is shown in its own script).
export const LANGS: { code: Lang; label: string; name: string; locale: string }[] = [
  { code: "hy", label: "Հայ", name: "Հայերեն", locale: "hy-AM" },
  { code: "ru", label: "Рус", name: "Русский", locale: "ru-RU" },
  { code: "en", label: "Eng", name: "English", locale: "en-US" },
];

const STORAGE_KEY = "forma.lang";
function detect(): Lang {
  try {
    const saved = localStorage.getItem(STORAGE_KEY) as Lang | null;
    if (saved && ["hy", "ru", "en"].includes(saved)) return saved;
  } catch { /* storage unavailable */ }
  const nav = (navigator.languages || [navigator.language]).map((l) => l.slice(0, 2));
  return (nav.find((l) => ["hy", "ru", "en"].includes(l)) as Lang) || "hy";
}

let current: Lang = detect();
const subs = new Set<() => void>();
const onChange: ((l: Lang) => void)[] = [];
document.documentElement.lang = current;

export function getLang(): Lang { return current; }
export function setLang(l: Lang, opts: { persistRemote?: boolean } = { persistRemote: true }) {
  if (l === current) return;
  current = l;
  document.documentElement.lang = l;
  try { localStorage.setItem(STORAGE_KEY, l); } catch { /* ignore */ }
  subs.forEach((f) => f());
  if (opts.persistRemote !== false) onChange.forEach((f) => f(l));
}
/** Registers a listener (used by the API layer to save the language in the user profile). */
export function onLangChange(f: (l: Lang) => void) { onChange.push(f); }

const missing = new Set<string>();
export function translate(key: string, params?: Record<string, unknown>, lang: Lang = current): string {
  const e = DICT[key];
  let s = e ? (e[lang] || e.en || e.ru) : undefined;
  if (s === undefined) {
    if (import.meta.env.DEV && !missing.has(key)) { missing.add(key); console.warn(`[i18n] missing key: ${key}`); }
    // never show a raw key: humanise its last segment
    s = key.split(".").pop()!.replace(/_/g, " ");
  }
  if (params) s = s.replace(/\{(\w+)\}/g, (_, k) => (params[k] === undefined || params[k] === null ? "" : String(params[k])));
  return s;
}
export function has(key: string) { return key in DICT; }

export function useLang(): Lang {
  return useSyncExternalStore((cb) => { subs.add(cb); return () => subs.delete(cb); }, () => current);
}
/** Hook: components re-render on language switch. */
export function useT() {
  const lang = useLang();
  const t = (key: string, params?: Record<string, unknown>) => translate(key, params, lang);
  return { t, lang, locale: LANGS.find((l) => l.code === lang)!.locale };
}
/** Translate a key if it exists, otherwise return the fallback text (for server-provided text). */
export function tOr(key: string, fallback: string, params?: Record<string, unknown>, lang: Lang = current) {
  return has(key) ? translate(key, params, lang) : fallback;
}
