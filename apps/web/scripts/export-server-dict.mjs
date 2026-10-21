// Exports the parts of the UI dictionary that the API also renders (album PDF, XLSX) to
// apps/api/app/i18n_shared.json, so server documents and the UI share one source of truth.
// Run: node --experimental-strip-types scripts/export-server-dict.mjs   (CI: add --check)
import { mkdtempSync, readdirSync, readFileSync, writeFileSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { pathToFileURL } from "node:url";

const PREFIXES = ["works.", "notice.", "rules.", "enum.group.", "enum.price.", "enum.style.", "enum.tier.", "enum.room.", "unit.", "estimate.line_"];
const src = new URL("../src/i18n/dict/", import.meta.url).pathname;
const tmp = mkdtempSync(join(tmpdir(), "dict-"));
for (const f of readdirSync(src).filter((x) => x.endsWith(".ts"))) {
  const code = readFileSync(join(src, f), "utf8")
    .replace(/^import type .*$/gm, "")
    .replace(/from "\.\/(\w+)"/g, 'from "./$1.ts"')
    .replace(/: (Dict|Record<string, Entry>|Entry)\b/g, "");
  writeFileSync(join(tmp, f), code);
}
const { DICT } = await import(pathToFileURL(join(tmp, "index.ts")).href);
rmSync(tmp, { recursive: true });
const out = Object.fromEntries(Object.entries(DICT).filter(([k]) => PREFIXES.some((p) => k.startsWith(p))).sort(([a], [b]) => a.localeCompare(b)));
const json = JSON.stringify(out, null, 1) + "\n";
const target = new URL("../../api/app/i18n_shared.json", import.meta.url).pathname;
if (process.argv.includes("--check")) {
  let cur = "";
  try { cur = readFileSync(target, "utf8"); } catch { /* missing */ }
  if (cur !== json) { console.error("i18n_shared.json is stale — run scripts/export-server-dict.mjs"); process.exit(1); }
  console.log(`i18n_shared.json up to date (${Object.keys(out).length} keys)`);
} else {
  writeFileSync(target, json);
  console.log(`wrote ${Object.keys(out).length} keys to ${target}`);
}
