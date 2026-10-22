// Thin typed client for the Renovara API. The session lives in an HttpOnly cookie set by
// the server (JS never sees it); unsafe requests echo the readable CSRF cookie in X-CSRF-Token.

export type Pt = [number, number];
export interface Wall { id: string; a: Pt; b: Pt; thickness: number; kind: string; status: "existing" | "demolish" | "new"; material: string; load_bearing: boolean; confidence: number; source: string }
export interface Opening { id: string; wall_id: string; type: string; offset: number; width: number; height: number; sill: number; hinge: "start" | "end"; swing: "left" | "right"; confidence: number; product_variant_id?: string | null }
export interface Room { id: string; number: number; type: string; name: string; polygon: Pt[]; ceiling_height: number; zone?: string | null; confidence: number; source: string }
export interface SceneObject { id: string; code: string; room_id: string; category: string; name: string; product_variant_id?: string | null; custom_product?: Record<string, unknown> | null; x: number; y: number; w: number; d: number; h: number; rotation: number; elevation: number; locked: boolean; color_hex: string; mode: string; confidence: number; source: string }
export interface Fixture { id: string; type: string; position: Pt; room_id?: string; size?: [number, number] | null; rotation: number }
export interface Electrical { id: string; code: string; type: string; position: Pt; height: number; room_id?: string; note: string }
export interface Light { id: string; code: string; type: string; position: Pt; end?: Pt | null; room_id?: string; scenario: string; switch_group: string; power_w: number }
export interface Finish { room_id: string; surface: string; product_variant_id?: string | null; material_code: string; name: string; color_hex: string; pattern: string }
export interface Assumption { key: string; text: string; severity: "info" | "warning" | "critical"; element_id?: string | null }
export interface Scene {
  name: string; ceiling_height: number; walls: Wall[]; openings: Opening[]; rooms: Room[]; fixtures: Fixture[]; objects: SceneObject[];
  electrical: Electrical[]; lights: Light[]; finishes: Finish[]; ceilings: { room_id: string; type: string; height: number }[];
  cameras: { id: string; room_id: string; position: Pt; target: Pt }[]; control_dimensions: { wall_id: string; measured_mm: number }[]; assumptions: Assumption[];
}
export interface EstimateLine { id: string; group: string; category: string; name: string; qty: number; unit: string; unit_price: number | null; total: number | null; price_status: string; ref?: string; sku?: string; supplier?: string; supplier_key?: string; url?: string; checked_at?: string | null; lead_days?: number | null; stock?: string; rooms?: string[]; note?: string; is_demo?: boolean; color_hex?: string; warnings?: string[]; area_m2?: number }
export interface Estimate { generated_at: string; currency: string; lines: EstimateLine[]; sections: { group: string; label: string; total: number; lines: number; quote_required: number; share: number }[]; totals: { known: number; confirmed: number; estimated: number; demo: number; quote_required_lines: number; range_low: number; range_high: number }; budget?: { target: number; delta: number; within: boolean } | null; disclaimers: string[]; areas: Record<string, number> }
export interface Issue { rule: string; severity: "pass" | "warning" | "block"; message: string; element_ids: string[]; room_id?: string | null }
export interface Version { id: string; number: number; parent_id?: string | null; source: string; frozen: boolean; created_at: string; note?: string; diff?: Diff; total?: number; scene: Scene; estimate: Estimate; issues: Issue[]; selection: Record<string, Record<string, string[]>> }
export interface Diff { added: { room_id: string; category: string; name: string }[]; removed: { room_id: string; category: string; name: string }[]; changed: { room_id: string; category: string; from: string; to: string }[]; moved: { room_id: string; category: string; name: string }[]; rooms_affected: string[]; total_before: number; total_after: number; total_delta: number }
export interface Variant { id: string; key: string; title: string; subtitle: string; description: string; style: string; tier: string; mode: string; status: string; palette: string[]; metrics: Metrics; current_version_id: string; version?: Version }
export interface Metrics { total: number; range_low: number; range_high: number; quote_required: number; confidence: number; feasibility: number; lead_days_max: number; availability_share: number; items: number; issues: { block: number; warning: number; pass: number; rules: number }; sourcing?: { external: number; internal: number; demo_fallback: number; concept: number; missing: string[] }; unplaced?: { room_id: string; category: string; reason: string }[]; budget?: { target: number; delta: number; within: boolean } | null }
export interface Job { id: string; kind: string; status: string; progress: number; error?: string | null; counters: Record<string, number>; result: Record<string, unknown>; steps: { key: string; title: string; phase: string; status: string; detail: string }[] }
export interface Project { id: string; title: string; address: string; city: string; area_m2: number | null; accuracy_level: string; confidence: number; status: string; preferences: Record<string, any>; brief: Record<string, any>; product_source: string; external_settings: Record<string, any>; client_name: string; designer_name: string; doc_lang: string; share_token: string; created_at: string; updated_at: string; variants?: any; total?: number | null; assets?: Asset[]; base_scene?: { version: number; confirmed: boolean } | null; last_pipeline_job?: Job | null }
export interface Asset { id: string; kind: string; filename: string; size: number; url: string; quality: { warnings?: string[] }; aps: { status?: string; urn?: string; rooms?: unknown[] } }
export interface Doc { id: string; kind: string; filename: string; size: number; lang: string; status: string; url: string; created_at: string; meta: { sheets?: { code: string; title: string; section: number }[]; aps?: { urn?: string } } }
export interface Me { id: string; email: string; name: string; locale?: string; email_verified: boolean; onboarded: boolean; roles: string[]; memberships: { org_id: string; org_name: string; org_kind: string; role: string }[] }

/** Session state known to the UI. The token itself is HttpOnly and never readable from JS. */
export const auth = { signedIn: false };

function cookie(name: string): string {
  const m = document.cookie.match(new RegExp(`(?:^|; )${name}=([^;]*)`));
  return m ? decodeURIComponent(m[1]) : "";
}

const PUBLIC_PATHS = ["/login", "/register", "/verify-email", "/forgot-password", "/reset-password", "/client"];

import { onLangChange, translate, tOr } from "../i18n";

/** Errors carry the stable server code; `message` is already translated to the UI language. */
export class ApiError extends Error {
  constructor(public status: number, public code: string, public params: Record<string, unknown> = {}, fallback = "") {
    super(tOr(`errors.${code}`, fallback || translate("errors.unknown"), params));
  }
}

export async function api<T = any>(path: string, opts: RequestInit & { json?: unknown } = {}): Promise<T> {
  const headers: Record<string, string> = { ...(opts.headers as Record<string, string>) };
  const method = (opts.method || "GET").toUpperCase();
  if (!["GET", "HEAD", "OPTIONS"].includes(method)) { const c = cookie("forma_csrf"); if (c) headers["X-CSRF-Token"] = c; }
  let body = opts.body;
  if (opts.json !== undefined) { headers["Content-Type"] = "application/json"; body = JSON.stringify(opts.json); }
  let r: Response;
  try { r = await fetch(path.startsWith("/api") ? path : `/api/v1${path}`, { credentials: "same-origin", ...opts, headers, body }); }
  catch { throw new ApiError(0, "network"); }
  if (r.status === 401 && !path.startsWith("/auth/")) {
    auth.signedIn = false;
    const here = location.pathname;
    if (here !== "/" && !PUBLIC_PATHS.some((p) => here.startsWith(p))) location.href = `/login?next=${encodeURIComponent(here)}`;
  }
  if (!r.ok) {
    let code = `http.${r.status}`, params: Record<string, unknown> = {}, fallback = r.statusText;
    try { const j = await r.json(); code = j.code || code; params = j.params || {}; fallback = typeof j.detail === "string" ? j.detail : fallback; } catch { /* not json */ }
    throw new ApiError(r.status, code, params, fallback);
  }
  const ct = r.headers.get("content-type") || "";
  return (ct.includes("json") ? r.json() : r.text()) as Promise<T>;
}

/** Signed file URLs are absolute to the API base; rewrite to the current origin (dev proxy). */
export function fileUrl(u?: string | null): string {
  if (!u) return "#";
  const i = u.indexOf("/api/v1/files/");
  return i >= 0 ? u.slice(i) : u;
}

export function streamJob(pid: string, jid: string, onJob: (j: Job) => void): () => void {
  const es = new EventSource(`/api/v1/projects/${pid}/jobs/${jid}/events`, { withCredentials: true });
  es.addEventListener("progress", (e) => { try { onJob(JSON.parse((e as MessageEvent).data)); } catch { /* ignore */ } });
  es.addEventListener("end", () => es.close());
  es.onerror = () => {
    es.close();
    // fallback: poll
    const t = setInterval(async () => {
      try { const j = await api<Job>(`/projects/${pid}/jobs/${jid}`); onJob(j); if (["succeeded", "failed"].includes(j.status)) clearInterval(t); } catch { clearInterval(t); }
    }, 1500);
  };
  return () => es.close();
}

// Persist the interface language in the user profile whenever it changes.
onLangChange((l) => { if (auth.signedIn) api("/auth/me", { method: "PATCH", json: { locale: l } }).catch(() => {}); });
