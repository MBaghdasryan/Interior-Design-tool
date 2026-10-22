// i18n audit: hardcoded UI strings, missing keys, orphan keys.
// Usage: node scripts/i18n-check.mjs [--json]
import { readFileSync, readdirSync, statSync } from "node:fs";
import { join } from "node:path";

const SRC = new URL("../src/", import.meta.url).pathname;
const files = [];
(function walk(d) { for (const f of readdirSync(d)) { const p = join(d, f); if (statSync(p).isDirectory()) walk(p); else if (/\.(tsx?|ts)$/.test(f)) files.push(p); } })(SRC);
const dictFiles = files.filter((f) => f.includes("/i18n/dict/"));
const codeFiles = files.filter((f) => !f.includes("/i18n/"));

// --- dictionary keys and per-language completeness
const keys = new Set();
const incomplete = [];
for (const f of dictFiles) {
  const s = readFileSync(f, "utf8");
  for (const m of s.matchAll(/"([a-z0-9_]+(?:\.[^"\s]+)+)":\s*(?:e\(|\{)/g)) keys.add(m[1]);
  for (const m of s.matchAll(/\{\s*hy:\s*"([^"]*)",\s*ru:\s*"([^"]*)",\s*en:\s*"([^"]*)"\s*\}/g)) if (!m[1] || !m[2] || !m[3]) incomplete.push(m[0].slice(0, 60));
}
// enum/unit families are generated programmatically in enums.ts / workspace.ts
const generated = ["enum.cat.", "enum.group.", "enum.style.", "enum.style_sub.", "enum.tier.", "enum.room.", "enum.role.", "unit."];

// --- hardcoded user-visible strings: Cyrillic/Armenian text in code files
const CYR = /[Ѐ-ӿ԰-֏]/;
const hard = [];
for (const f of codeFiles) {
  const lines = readFileSync(f, "utf8").split("\n");
  lines.forEach((l, i) => {
    const t = l.trim();
    if (t.startsWith("//") || t.startsWith("*") || t.startsWith("/*")) return;
    if (CYR.test(l)) hard.push(`${f.replace(SRC, "src/")}:${i + 1}: ${t.slice(0, 110)}`);
  });
}

// --- static keys used in code
const used = new Set();
const dynamicPrefixes = new Set(generated);
for (const f of files.filter((f) => !f.includes("/i18n/dict/"))) {
  const s = readFileSync(f, "utf8");
  for (const m of s.matchAll(/\bt(?:ranslate|Or)?\(\s*"([a-z0-9_]+(?:\.[a-z0-9_?]+)+)"/g)) used.add(m[1]);
  for (const m of s.matchAll(/`([a-z0-9_]+(?:\.[a-z0-9_]+)*\.)\$\{/g)) dynamicPrefixes.add(m[1]);
}
const isGenerated = (k) => generated.some((p) => k.startsWith(p));
// any string literal equal to a dictionary key counts as a use (keys kept in arrays/ternaries)
for (const f of codeFiles) for (const m of readFileSync(f, "utf8").matchAll(/"([a-z0-9_]+(?:\.[a-z0-9_?]+)+)"/g)) if (keys.has(m[1])) used.add(m[1]);
// keys rendered by the server (album, pilot report) through apps/api/app/i18n_shared.json also count as used
const apiDir = new URL("../../api/app/", import.meta.url).pathname;
const walkPy = (d) => { try { return readdirSync(d, { withFileTypes: true }).flatMap((e) => e.isDirectory() ? walkPy(join(d, e.name)) : e.name.endsWith(".py") ? [join(d, e.name)] : []); } catch { return []; } };
for (const f of walkPy(apiDir)) for (const m of readFileSync(f, "utf8").matchAll(/["']([a-z0-9_]+(?:\.[a-z0-9_]+)+)["']/g)) if (keys.has(m[1])) used.add(m[1]);
const missing = [...used].filter((k) => !keys.has(k) && !isGenerated(k));
const orphans = [...keys].filter((k) => !used.has(k) && ![...dynamicPrefixes].some((p) => k.startsWith(p)));

const report = { dictionary_keys: keys.size, languages: ["hy", "ru", "en"], incomplete_entries: incomplete.length, static_keys_used: used.size,
  dynamic_prefixes: [...dynamicPrefixes].sort(), missing_keys: missing, orphan_keys: orphans, hardcoded_strings: hard };
if (process.argv.includes("--json")) console.log(JSON.stringify(report, null, 2));
else {
  console.log(`keys=${keys.size} used(static)=${used.size} incomplete=${incomplete.length} missing=${missing.length} orphans=${orphans.length} hardcoded=${hard.length}`);
  for (const k of missing) console.log("MISSING", k);
  for (const h of hard) console.log("HARDCODED", h);
  if (orphans.length) console.log("ORPHANS", orphans.join(", "));
}
process.exit(missing.length || incomplete.length || hard.length ? 1 : 0);
