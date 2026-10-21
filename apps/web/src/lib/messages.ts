// Localisation of server-generated messages that carry stable codes + params.
import type { Issue, Job } from "./api";
import { catName, roomType } from "./format";
import { getLang, has, tOr, translate } from "../i18n";

export function ruleMessage(i: Issue & { code?: string; params?: Record<string, unknown> }): string {
  if (!i.code) return getLang() === "ru" ? i.message : translate("errors.unknown");
  const p: Record<string, unknown> = { ...(i.params || {}) };
  for (const k of ["object", "other", "a", "b"]) if (typeof p[k] === "string") p[k] = catName(p[k] as string);
  if (typeof p.room === "string") p.room = roomType(p.room as string);
  // codes default to the object category when the drawing tag is missing
  for (const [code, cat] of [["code", "object"], ["other_code", "other"], ["a_code", "a"], ["b_code", "b"]]) if (!p[code]) p[code] = p[cat];
  return tOr(`rules.${i.code}`, i.message, p);
}

export function stepTitle(s: Job["steps"][number]): string {
  return tOr(`steps.${s.key}.title`, s.title);
}

export function stepDetail(s: Job["steps"][number] & { params?: Record<string, unknown> }): string {
  const key = `steps.${s.key}.detail`;
  if (s.params && Object.keys(s.params).length && has(key)) {
    const p: Record<string, unknown> = { ...s.params };
    if (Array.isArray(p.variants)) p.n = (p.variants as unknown[]).length;
    if (typeof p.provider === "string") p.provider = p.provider === "stub" ? translate("cmd.deterministic") : p.provider;
    return translate(key, p);
  }
  // free-text details are produced in Russian by the server; hide them in other languages
  return getLang() === "ru" ? s.detail : "";
}
