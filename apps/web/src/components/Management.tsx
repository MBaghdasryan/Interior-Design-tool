import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { Archive, Building2, KeyRound, LogOut, Mail, Pencil, Plus, RotateCcw, Search, ShieldOff, Store, Trash2, UserPlus, Users } from "lucide-react";
import { api, ApiError } from "../lib/api";
import { withQs } from "../lib/scope";
import { amd, catName, dt, roleName } from "../lib/format";
import { useT } from "../i18n";
import { Badge, Drawer, Empty, Loading, Modal, PriceStatus, useToast } from "./ui";
import { useMe } from "./AppShell";

export interface Org { id: string; name: string; kind: string; status: string; plan: string | null; users: number; projects: number; supplier_id: string | null; created_at: string | null }
export interface SupplierRow { id: string; name: string; slug: string; kind: string; city: string; website: string; is_demo: boolean; verification: string; commission_pct: number;
  org_id: string | null; org_name: string | null; products: number; contacts: Record<string, string> | null }
interface Membership { id: string; org_id: string; org_name: string; org_kind: string; role: string }
interface AdminUser { id: string; email: string; name: string; locale: string; status: string; email_verified: boolean; mfa: boolean; created_at: string | null; last_seen_at: string | null; memberships: Membership[] }
interface Member { membership_id: string; user_id: string; name: string; email: string; role: string; status: string; email_verified: boolean; mfa: boolean; last_seen_at: string | null }
interface Team { org: { id: string; name: string; kind: string }; roles: string[]; members: Member[] }
interface Variant { id?: string; sku: string; color: string; color_hex: string; material: string; width_mm: number; depth_mm: number; height_mm: number; price: number | null; currency: string;
  price_status?: string; stock_status: string; lead_time_days: number | null; url: string; image_url: string; has_3d?: boolean }
export interface Product { id: string; supplier_id: string; supplier_name: string; category: string; name_ru: string; name_hy: string; name_en: string; brand: string; description: string;
  tier: string; styles: string[]; unit: string; item_type: string; status: string; is_demo: boolean; variants: Variant[]; can_edit?: boolean }
interface Tax { categories: { key: string; group: string }[]; styles: { key: string }[] }

const ROLES: Record<string, string[]> = {
  platform: ["platform_admin", "platform_ops", "linguist", "verifier"],
  bureau: ["bureau_admin", "designer", "verifier", "collaborator", "client"],
  supplier: ["supplier_admin", "supplier_catalog", "manufacturer", "installer"],
};
const STATUS_TONE: Record<string, string> = { active: "sage", suspended: "danger", deletion_pending: "warn", verified: "sage", pending: "warn", rejected: "danger", archived: "" };
const errMsg = (x: unknown) => (x as Error).message;

function useRun() {
  const toast = useToast();
  const { t } = useT();
  return useCallback(async (fn: () => Promise<unknown>, ok?: string) => {
    try { await fn(); toast(ok || t("mg.saved")); return true; } catch (x) { toast(errMsg(x), true); return false; }
  }, [toast, t]);
}

// ------------------------------------------------------------------ pickers (platform staff open any cabinet)
export function OrgPicker({ kind, value, onChange }: { kind: "bureau"; value: string; onChange: (id: string) => void }) {
  const { t } = useT();
  const [orgs, setOrgs] = useState<Org[] | null>(null);
  useEffect(() => { api<Org[]>(`/admin/organizations?kind=${kind}`).then(setOrgs).catch(() => setOrgs([])); }, [kind]);
  if (!orgs?.length) return null;
  return (
    <label className="row gap-6 small"><Building2 size={16} /> {t("mg.open_cabinet")}
      <select className="select input" style={{ minWidth: 240 }} value={value} onChange={(e) => onChange(e.target.value)}>
        <option value="">{t("mg.own_or_pick")}</option>
        {orgs.map((o) => <option key={o.id} value={o.id}>{o.name} · {t("mg.n_projects", { n: o.projects })}</option>)}
      </select></label>
  );
}

export function SupplierPicker({ value, onChange }: { value: string; onChange: (id: string) => void }) {
  const { t } = useT();
  const [rows, setRows] = useState<SupplierRow[] | null>(null);
  useEffect(() => { api<SupplierRow[]>("/admin/suppliers/all").then(setRows).catch(() => setRows([])); }, []);
  if (!rows?.length) return null;
  return (
    <label className="row gap-6 small"><Store size={16} /> {t("mg.open_cabinet")}
      <select className="select input" style={{ minWidth: 240 }} value={value} onChange={(e) => onChange(e.target.value)}>
        <option value="">{t("mg.own_or_pick")}</option>
        {rows.map((s) => <option key={s.id} value={s.id}>{s.name}{s.is_demo ? " · DEMO" : ""} · {t("mg.n_products", { n: s.products })}</option>)}
      </select></label>
  );
}

// ------------------------------------------------------------------ team (bureau head / supplier admin / platform)
export function TeamCard({ orgId = "" }: { orgId?: string }) {
  const { t } = useT();
  const run = useRun();
  const [team, setTeam] = useState<Team | null>(null);
  const [err, setErr] = useState("");
  const [inv, setInv] = useState<{ email: string; name: string; role: string; locale: string } | null>(null);
  const q = orgId ? `org_id=${encodeURIComponent(orgId)}` : "";
  const load = useCallback(() => api<Team>(withQs("/team", q)).then((x) => { setTeam(x); setErr(""); }).catch((e: ApiError) => setErr(e.message)), [q]);
  useEffect(() => { load(); }, [load]);
  if (err) return <div className="alert warn small">{err}</div>;
  if (!team) return <Loading />;
  const invite = async () => { if (inv && await run(() => api(withQs("/team/invite", q), { method: "POST", json: inv }), t("mg.invited", { email: inv.email }))) { setInv(null); load(); } };
  return (
    <section className="card pad col gap-10" aria-labelledby="team-h">
      <div className="row between wrap"><h3 id="team-h" className="row gap-6"><Users size={18} /> {t("mg.team_title")} <Badge>{team.members.length}</Badge></h3>
        <button className="btn sm primary" onClick={() => setInv({ email: "", name: "", role: team.roles.includes("designer") ? "designer" : "supplier_catalog", locale: "hy" })}><UserPlus size={15} /> {t("mg.invite")}</button></div>
      <p className="tiny muted">{t("mg.team_lead")}</p>
      <div style={{ overflow: "auto" }}>
        <table className="table compact"><thead><tr><th>{t("mg.col.person")}</th><th>{t("mg.col.role")}</th><th>{t("common.status")}</th><th>{t("mg.col.last_seen")}</th><th /></tr></thead>
          <tbody>{team.members.map((m) => (
            <tr key={m.membership_id}>
              <td><b className="small">{m.name}</b><div className="tiny muted">{m.email}</div></td>
              <td><select className="select input" style={{ height: 32, minWidth: 190 }} aria-label={t("mg.col.role")} value={m.role}
                onChange={(e) => run(() => api(withQs(`/team/${m.membership_id}`, q), { method: "PATCH", json: { role: e.target.value } })).then(load)}>
                {team.roles.map((r) => <option key={r} value={r}>{roleName(r)}</option>)}</select></td>
              <td><Badge tone={STATUS_TONE[m.status]}>{t(`mg.status.${m.status}`)}</Badge>{m.mfa && <Badge tone="info">MFA</Badge>}</td>
              <td className="tiny muted">{m.last_seen_at ? dt(m.last_seen_at) : t("mg.never")}</td>
              <td><button className="icon-btn" aria-label={t("mg.remove_member")} title={t("mg.remove_member")}
                onClick={() => confirm(t("mg.confirm_remove", { name: m.name })) && run(() => api(withQs(`/team/${m.membership_id}`, q), { method: "DELETE" })).then(load)}><Trash2 size={15} /></button></td>
            </tr>))}</tbody></table>
      </div>
      <Modal open={!!inv} onClose={() => setInv(null)}>
        {inv && <div className="col gap-10" style={{ padding: 20, width: "min(440px, 92vw)" }} role="dialog" aria-label={t("mg.invite")}>
          <h3>{t("mg.invite_to", { org: team.org.name })}</h3>
          <label className="field"><span>{t("mg.f.email")}</span><input className="input" type="email" value={inv.email} onChange={(e) => setInv({ ...inv, email: e.target.value })} /></label>
          <label className="field"><span>{t("mg.f.name")}</span><input className="input" value={inv.name} onChange={(e) => setInv({ ...inv, name: e.target.value })} /></label>
          <div className="row gap-8">
            <label className="field grow"><span>{t("mg.col.role")}</span><select className="select input" value={inv.role} onChange={(e) => setInv({ ...inv, role: e.target.value })}>{team.roles.map((r) => <option key={r} value={r}>{roleName(r)}</option>)}</select></label>
            <LocaleSelect value={inv.locale} onChange={(v) => setInv({ ...inv, locale: v })} />
          </div>
          <p className="tiny muted">{t("mg.invite_hint")}</p>
          <div className="row gap-6"><button className="btn primary" disabled={!inv.email.includes("@") || !inv.name} onClick={invite}><Mail size={15} /> {t("mg.send_invite")}</button><button className="btn ghost" onClick={() => setInv(null)}>{t("common.cancel")}</button></div>
        </div>}
      </Modal>
    </section>
  );
}

function LocaleSelect({ value, onChange }: { value: string; onChange: (v: string) => void }) {
  const { t } = useT();
  return <label className="field"><span>{t("mg.f.locale")}</span><select className="select input" value={value} onChange={(e) => onChange(e.target.value)}>
    {["hy", "ru", "en"].map((l) => <option key={l} value={l}>{l.toUpperCase()}</option>)}</select></label>;
}

// ------------------------------------------------------------------ products: manual create / edit / archive
const EMPTY_VARIANT: Variant = { sku: "", color: "", color_hex: "#cccccc", material: "", width_mm: 0, depth_mm: 0, height_mm: 0, price: null, currency: "AMD", stock_status: "unknown", lead_time_days: null, url: "", image_url: "" };
const VARIANT_FIELDS = ["sku", "color", "color_hex", "material", "width_mm", "depth_mm", "height_mm", "price", "currency", "stock_status", "lead_time_days", "url", "image_url"] as const;
const variantBody = (v: Variant) => Object.fromEntries(VARIANT_FIELDS.map((k) => [k, v[k]]));

export function ProductEditor({ open, supplierId, productId, onClose, onSaved }: { open: boolean; supplierId: string; productId: string | null; onClose: () => void; onSaved: () => void }) {
  const { t } = useT();
  const run = useRun();
  const [tax, setTax] = useState<Tax | null>(null);
  const [p, setP] = useState<Product | null>(null);
  useEffect(() => { api<Tax>("/catalog/taxonomy").then(setTax).catch(() => {}); }, []);
  useEffect(() => {
    if (!open) return;
    if (productId) { setP(null); api<Product>(`/catalog/products/${productId}/detail`).then(setP).catch(() => onClose()); }
    else setP({ id: "", supplier_id: supplierId, supplier_name: "", category: "sofa", name_ru: "", name_hy: "", name_en: "", brand: "", description: "", tier: "comfort", styles: [], unit: "pcs", item_type: "serial", status: "active", is_demo: false, variants: [{ ...EMPTY_VARIANT }] });
  }, [open, productId, supplierId, onClose]);
  if (!open) return null;
  const isNew = !productId;
  const set = (k: keyof Product, v: unknown) => p && setP({ ...p, [k]: v });
  const setV = (i: number, k: keyof Variant, v: unknown) => p && setP({ ...p, variants: p.variants.map((x, j) => (j === i ? { ...x, [k]: v } : x)) });
  const head = p && { category: p.category, name_ru: p.name_ru, name_hy: p.name_hy, name_en: p.name_en, brand: p.brand, description: p.description, tier: p.tier, styles: p.styles, unit: p.unit, item_type: p.item_type };
  const save = async () => {
    if (!p || !head) return;
    const ok = isNew
      ? await run(() => api("/catalog/products", { method: "POST", json: { ...head, supplier_id: supplierId, variants: p.variants.map(variantBody) } }), t("mg.product_created"))
      : await run(async () => {
        await api(`/catalog/products/${p.id}`, { method: "PATCH", json: head });
        for (const v of p.variants) {
          if (v.id) await api(`/catalog/variants/${v.id}`, { method: "PATCH", json: variantBody(v) });
          else await api(`/catalog/products/${p.id}/variants`, { method: "POST", json: variantBody(v) });
        }
      });
    if (ok) { onSaved(); onClose(); }
  };
  const dropVariant = async (i: number) => {
    if (!p) return;
    const v = p.variants[i];
    if (v.id && !(await run(() => api(`/catalog/variants/${v.id}`, { method: "DELETE" })))) return;
    setP({ ...p, variants: p.variants.filter((_, j) => j !== i) });
  };
  const num = (v: string) => (v === "" ? null : Number(v));
  const valid = !!p && p.name_ru.trim() && p.variants.length && p.variants.every((v) => v.sku.trim());
  return (
    <Drawer open onClose={onClose} title={isNew ? t("mg.product_new") : t("mg.product_edit")}
      footer={<div className="row gap-6"><button className="btn primary" disabled={!valid} onClick={save}>{t("common.save")}</button><button className="btn ghost" onClick={onClose}>{t("common.cancel")}</button></div>}>
      {!p || !tax ? <Loading /> : <div className="col gap-10">
        {!isNew && <div className="row gap-6 small"><Badge tone={STATUS_TONE[p.status]}>{t(`mg.pstatus.${p.status}`)}</Badge>{p.is_demo && <Badge tone="danger">DEMO</Badge>}<span className="muted">{p.supplier_name}</span></div>}
        <label className="field"><span>{t("mg.f.name_ru")} *</span><input className="input" value={p.name_ru} onChange={(e) => set("name_ru", e.target.value)} /></label>
        <div className="grid g2">
          <label className="field"><span>{t("mg.f.name_hy")}</span><input className="input" lang="hy" value={p.name_hy} onChange={(e) => set("name_hy", e.target.value)} /></label>
          <label className="field"><span>{t("mg.f.name_en")}</span><input className="input" lang="en" value={p.name_en} onChange={(e) => set("name_en", e.target.value)} /></label>
          <label className="field"><span>{t("common.category")}</span><select className="select input" value={p.category} onChange={(e) => set("category", e.target.value)}>{tax.categories.map((c) => <option key={c.key} value={c.key}>{catName(c.key)}</option>)}</select></label>
          <label className="field"><span>{t("mg.f.brand")}</span><input className="input" value={p.brand} onChange={(e) => set("brand", e.target.value)} /></label>
          <label className="field"><span>{t("mg.f.tier")}</span><select className="select input" value={p.tier} onChange={(e) => set("tier", e.target.value)}>{["economy", "comfort", "business", "premium"].map((k) => <option key={k} value={k}>{t(`enum.tier.${k}`)}</option>)}</select></label>
          <label className="field"><span>{t("mg.f.unit")}</span><select className="select input" value={p.unit} onChange={(e) => set("unit", e.target.value)}>{["pcs", "m2", "pack", "l", "kg", "m"].map((k) => <option key={k} value={k}>{t(`mg.unit.${k}`)}</option>)}</select></label>
          <label className="field"><span>{t("mg.f.item_type")}</span><select className="select input" value={p.item_type} onChange={(e) => set("item_type", e.target.value)}>{["serial", "made_to_order", "parametric", "service", "material", "kit", "custom"].map((k) => <option key={k} value={k}>{t(`mg.itype.${k}`)}</option>)}</select></label>
        </div>
        <fieldset className="col gap-4" style={{ border: 0, padding: 0, margin: 0 }}><legend className="small muted">{t("mg.f.styles")}</legend>
          <div className="row gap-4 wrap">{tax.styles.map((s) => { const on = p.styles.includes(s.key); return <button key={s.key} type="button" className={`chip ${on ? "on" : ""}`} aria-pressed={on} onClick={() => set("styles", on ? p.styles.filter((x) => x !== s.key) : [...p.styles, s.key])}>{t(`enum.style.${s.key}`)}</button>; })}</div></fieldset>
        <label className="field"><span>{t("mg.f.description")}</span><textarea className="input" rows={3} value={p.description} onChange={(e) => set("description", e.target.value)} /></label>
        <div className="row between"><b>{t("mg.variants")}</b><button className="btn sm" onClick={() => setP({ ...p, variants: [...p.variants, { ...EMPTY_VARIANT }] })}><Plus size={14} /> {t("mg.add_variant")}</button></div>
        {p.variants.map((v, i) => (
          <div key={v.id || `new-${i}`} className="card flat pad col gap-6">
            <div className="row between"><span className="row gap-6 small"><b className="mono">{v.sku || t("mg.new_variant")}</b>{v.price_status && <PriceStatus s={v.price_status} />}{v.has_3d && <Badge tone="info">3D</Badge>}</span>
              {p.variants.length > 1 && <button className="icon-btn" aria-label={t("mg.remove_variant")} title={t("mg.remove_variant")} onClick={() => dropVariant(i)}><Trash2 size={14} /></button>}</div>
            <div className="grid g3">
              <label className="field"><span>{t("common.sku")} *</span><input className="input mono" value={v.sku} onChange={(e) => setV(i, "sku", e.target.value)} /></label>
              <label className="field"><span>{t("common.price")}</span><input className="input" inputMode="numeric" placeholder={t("mg.price_on_request")} value={v.price ?? ""} onChange={(e) => setV(i, "price", num(e.target.value))} /></label>
              <label className="field"><span>{t("mg.f.currency")}</span><select className="select input" value={v.currency} onChange={(e) => setV(i, "currency", e.target.value)}>{["AMD", "USD", "EUR", "RUB"].map((c) => <option key={c}>{c}</option>)}</select></label>
              <label className="field"><span>{t("mg.f.width")}</span><input className="input" inputMode="numeric" value={v.width_mm || ""} onChange={(e) => setV(i, "width_mm", Number(e.target.value) || 0)} /></label>
              <label className="field"><span>{t("mg.f.depth")}</span><input className="input" inputMode="numeric" value={v.depth_mm || ""} onChange={(e) => setV(i, "depth_mm", Number(e.target.value) || 0)} /></label>
              <label className="field"><span>{t("mg.f.height")}</span><input className="input" inputMode="numeric" value={v.height_mm || ""} onChange={(e) => setV(i, "height_mm", Number(e.target.value) || 0)} /></label>
              <label className="field"><span>{t("mg.f.color")}</span><div className="row gap-4"><input type="color" aria-label={t("mg.f.color")} value={v.color_hex} onChange={(e) => setV(i, "color_hex", e.target.value)} style={{ width: 38, height: 38, border: 0, background: "none" }} /><input className="input grow" value={v.color} onChange={(e) => setV(i, "color", e.target.value)} /></div></label>
              <label className="field"><span>{t("mg.f.material")}</span><input className="input" value={v.material} onChange={(e) => setV(i, "material", e.target.value)} /></label>
              <label className="field"><span>{t("common.in_stock")}</span><select className="select input" value={v.stock_status} onChange={(e) => setV(i, "stock_status", e.target.value)}>{["in_stock", "to_order", "out_of_stock", "unknown"].map((k) => <option key={k} value={k}>{t(`mg.stock.${k}`)}</option>)}</select></label>
              <label className="field"><span>{t("mg.f.lead")}</span><input className="input" inputMode="numeric" value={v.lead_time_days ?? ""} onChange={(e) => setV(i, "lead_time_days", num(e.target.value))} /></label>
              <label className="field"><span>{t("mg.f.url")}</span><input className="input" type="url" value={v.url} onChange={(e) => setV(i, "url", e.target.value)} /></label>
              <label className="field"><span>{t("mg.f.image")}</span><input className="input" type="url" value={v.image_url} onChange={(e) => setV(i, "image_url", e.target.value)} /></label>
            </div>
          </div>))}
        <p className="tiny muted">{t("mg.price_history_hint")}</p>
      </div>}
    </Drawer>
  );
}

interface SP { id: string; product_id: string; sku: string; name: string; category: string; price: number | null; price_status: string; stock: string; dims: number[]; has_3d: boolean; color_hex: string }

/** Supplier's catalogue with manual add / edit / archive (next to file import and feeds). */
export function SupplierProducts({ supplierId, supplierName, items, onChange }: { supplierId: string; supplierName: string; items: SP[]; onChange: () => void }) {
  const { t } = useT();
  const run = useRun();
  const [edit, setEdit] = useState<{ id: string | null } | null>(null);
  const [q, setQ] = useState("");
  const close = useCallback(() => setEdit(null), []);
  const rows = items.filter((p) => !q || `${p.sku} ${p.name}`.toLowerCase().includes(q.toLowerCase()));
  return (
    <section className="card col" aria-labelledby="sprod-h">
      <div className="row between wrap gap-8" style={{ padding: 16 }}>
        <h3 id="sprod-h">{t("mg.products_title")} <Badge>{items.length}</Badge></h3>
        <div className="row gap-6 wrap">
          <label className="row gap-4 input" style={{ height: 36 }}><Search size={15} /><input aria-label={t("common.search")} placeholder={t("common.search")} value={q} onChange={(e) => setQ(e.target.value)} style={{ border: 0, outline: 0, background: "transparent" }} /></label>
          <Link className="btn sm" to={`/app/pim?${new URLSearchParams({ supplier_name: supplierName, supplier_id: supplierId })}`}>{t("supc.upload")}</Link>
          <button className="btn sm primary" onClick={() => setEdit({ id: null })}><Plus size={15} /> {t("mg.product_new")}</button>
        </div>
      </div>
      {!items.length ? <Empty>{t("mg.no_products")}</Empty> : (
        <div style={{ overflow: "auto", maxHeight: 560 }}>
          <table className="table compact"><thead><tr><th /><th>{t("common.sku")}</th><th>{t("supc.col.name")}</th><th>{t("common.category")}</th><th className="right">{t("common.price")}</th><th>{t("common.status")}</th><th>{t("common.in_stock")}</th><th>{t("common.dims")}</th><th>{t("supc.col.3d")}</th><th /></tr></thead>
            <tbody>{rows.map((p) => <tr key={p.id}>
              <td><span className="dot" style={{ background: p.color_hex, width: 14, height: 14 }} /></td><td className="small mono">{p.sku}</td><td className="small">{p.name}</td><td className="small">{catName(p.category)}</td>
              <td className="right mono small">{amd(p.price, "")}</td><td><PriceStatus s={p.price_status} /></td><td className="small">{t(`mg.stock.${p.stock}`)}</td><td className="small">{p.dims.join("×")}</td><td>{p.has_3d ? "✓" : "—"}</td>
              <td><div className="row gap-4 wrap"><button className="icon-btn" aria-label={t("mg.product_edit")} title={t("mg.product_edit")} onClick={() => setEdit({ id: p.product_id })}><Pencil size={15} /></button>
                <button className="icon-btn" aria-label={t("mg.archive")} title={t("mg.archive")} onClick={() => confirm(t("mg.confirm_archive", { name: p.name })) && run(() => api(`/catalog/products/${p.product_id}`, { method: "DELETE" }), t("mg.archived")).then(onChange)}><Archive size={15} /></button></div></td>
            </tr>)}</tbody></table>
        </div>)}
      <ProductEditor open={!!edit} supplierId={supplierId} productId={edit?.id || null} onClose={close} onSaved={onChange} />
    </section>
  );
}

// ------------------------------------------------------------------ platform: users
export function UsersAdmin() {
  const { t } = useT();
  const run = useRun();
  const { me } = useMe();
  const [q, setQ] = useState("");
  const [status, setStatus] = useState("");
  const [data, setData] = useState<{ items: AdminUser[]; counts: Record<string, number> } | null>(null);
  const [orgs, setOrgs] = useState<Org[]>([]);
  const [sel, setSel] = useState<AdminUser | null>(null);
  const [add, setAdd] = useState<{ email: string; name: string; org_id: string; role: string; locale: string } | null>(null);
  const [grant, setGrant] = useState({ org_id: "", role: "" });
  const load = useCallback(() => api<{ items: AdminUser[]; counts: Record<string, number> }>(`/admin/users?${new URLSearchParams({ q, status })}`).then(setData).catch(() => {}), [q, status]);
  useEffect(() => { const tm = setTimeout(load, 250); return () => clearTimeout(tm); }, [load]);
  useEffect(() => { api<Org[]>("/admin/organizations").then(setOrgs).catch(() => {}); }, []);
  const act = async (fn: () => Promise<AdminUser>, ok?: string) => { let u: AdminUser | null = null; if (await run(async () => { u = await fn(); }, ok)) { setSel(u); load(); } };
  const rolesFor = (orgId: string) => ROLES[orgs.find((o) => o.id === orgId)?.kind || ""] || [];
  if (!data) return <Loading />;
  return (
    <div className="col gap-10">
      <div className="row between wrap gap-8">
        <div className="row gap-6 wrap">
          <label className="row gap-4 input" style={{ height: 38, minWidth: 260 }}><Search size={15} /><input aria-label={t("common.search")} placeholder={t("mg.search_users")} value={q} onChange={(e) => setQ(e.target.value)} style={{ border: 0, outline: 0, background: "transparent", width: "100%" }} /></label>
          {["", "active", "suspended", "deletion_pending"].map((s) => <button key={s} className={`chip ${status === s ? "on" : ""}`} aria-pressed={status === s} onClick={() => setStatus(s)}>{s ? t(`mg.status.${s}`) : t("mg.all")} {s ? data.counts[s] || 0 : ""}</button>)}
        </div>
        <button className="btn primary" onClick={() => setAdd({ email: "", name: "", org_id: orgs[0]?.id || "", role: rolesFor(orgs[0]?.id || "")[0] || "", locale: "hy" })}><UserPlus size={16} /> {t("mg.add_user")}</button>
      </div>
      <div className="card" style={{ overflow: "auto" }}>
        {!data.items.length ? <Empty>{t("mg.no_users")}</Empty> :
          <table className="table compact"><thead><tr><th>{t("mg.col.person")}</th><th>{t("mg.col.orgs_roles")}</th><th>{t("common.status")}</th><th>{t("mg.col.security")}</th><th>{t("mg.col.last_seen")}</th></tr></thead>
            <tbody>{data.items.map((u) => <tr key={u.id} onClick={() => { setSel(u); setGrant({ org_id: "", role: "" }); }} style={{ cursor: "pointer" }} tabIndex={0} onKeyDown={(e) => e.key === "Enter" && setSel(u)}>
              <td><b className="small">{u.name}</b><div className="tiny muted">{u.email}</div></td>
              <td className="small">{u.memberships.map((ms) => <div key={ms.id}>{ms.org_name} · <span className="muted">{roleName(ms.role)}</span></div>)}</td>
              <td><Badge tone={STATUS_TONE[u.status]}>{t(`mg.status.${u.status}`)}</Badge></td>
              <td><div className="row gap-4 wrap">{u.email_verified ? <Badge tone="sage">{t("mg.email_ok")}</Badge> : <Badge tone="warn">{t("mg.email_unverified")}</Badge>}{u.mfa && <Badge tone="info">MFA</Badge>}</div></td>
              <td className="tiny muted">{u.last_seen_at ? dt(u.last_seen_at) : t("mg.never")}</td>
            </tr>)}</tbody></table>}
      </div>
      <Drawer open={!!sel} onClose={() => setSel(null)} title={sel?.name || ""}>
        {sel && <div className="col gap-12">
          <div className="small"><div className="muted">{sel.email}</div><div className="row gap-4 mt-8"><Badge tone={STATUS_TONE[sel.status]}>{t(`mg.status.${sel.status}`)}</Badge>{sel.mfa && <Badge tone="info">MFA</Badge>}<Badge>{sel.locale.toUpperCase()}</Badge></div>
            <div className="tiny muted mt-8">{t("mg.created", { at: sel.created_at ? dt(sel.created_at) : "—" })} · {t("mg.last_seen", { at: sel.last_seen_at ? dt(sel.last_seen_at) : t("mg.never") })}</div></div>
          <b>{t("mg.col.orgs_roles")}</b>
          {sel.memberships.map((ms) => <div key={ms.id} className="row between small"><span>{ms.org_name} · {roleName(ms.role)}</span>
            <button className="icon-btn" aria-label={t("mg.revoke_role")} title={t("mg.revoke_role")} onClick={() => act(() => api(`/admin/users/${sel.id}/memberships/${ms.id}`, { method: "DELETE" }))}><Trash2 size={14} /></button></div>)}
          <div className="row gap-4 wrap">
            <select className="select input" aria-label={t("mg.col.org")} value={grant.org_id} onChange={(e) => setGrant({ org_id: e.target.value, role: rolesFor(e.target.value)[0] || "" })}><option value="">{t("mg.pick_org")}</option>{orgs.map((o) => <option key={o.id} value={o.id}>{o.name}</option>)}</select>
            <select className="select input" aria-label={t("mg.col.role")} value={grant.role} disabled={!grant.org_id} onChange={(e) => setGrant({ ...grant, role: e.target.value })}>{rolesFor(grant.org_id).map((r) => <option key={r} value={r}>{roleName(r)}</option>)}</select>
            <button className="btn sm" disabled={!grant.org_id || !grant.role} onClick={() => act(() => api(`/admin/users/${sel.id}/memberships`, { method: "POST", json: grant }))}><Plus size={14} /> {t("mg.grant_role")}</button>
          </div>
          <div className="divider" />
          <b>{t("mg.actions")}</b>
          <div className="col gap-6">
            <button className="btn sm" onClick={() => act(() => api(`/admin/users/${sel.id}/reset-password`, { method: "POST" }).then(() => sel), t("mg.reset_sent"))}><KeyRound size={14} /> {t("mg.reset_password")}</button>
            <button className="btn sm" onClick={() => act(() => api(`/admin/users/${sel.id}/revoke-sessions`, { method: "POST" }).then(() => sel), t("mg.sessions_revoked"))}><LogOut size={14} /> {t("mg.revoke_sessions")}</button>
            {sel.mfa && <button className="btn sm" onClick={() => confirm(t("mg.confirm_mfa")) && act(() => api(`/admin/users/${sel.id}/reset-mfa`, { method: "POST" }))}><ShieldOff size={14} /> {t("mg.reset_mfa")}</button>}
            {sel.id !== me?.id && (sel.status === "suspended"
              ? <button className="btn sm" onClick={() => act(() => api(`/admin/users/${sel.id}`, { method: "PATCH", json: { status: "active" } }))}><RotateCcw size={14} /> {t("mg.activate")}</button>
              : sel.status === "active" && <button className="btn sm danger" onClick={() => confirm(t("mg.confirm_suspend", { name: sel.name })) && act(() => api(`/admin/users/${sel.id}`, { method: "PATCH", json: { status: "suspended" } }))}><ShieldOff size={14} /> {t("mg.suspend")}</button>)}
            {sel.id !== me?.id && sel.status !== "deletion_pending" && <button className="btn sm danger" onClick={() => confirm(t("mg.confirm_delete", { name: sel.name })) && act(() => api(`/admin/users/${sel.id}`, { method: "DELETE" }))}><Trash2 size={14} /> {t("mg.delete_user")}</button>}
          </div>
          <p className="tiny muted">{t("mg.delete_hint")}</p>
        </div>}
      </Drawer>
      <Modal open={!!add} onClose={() => setAdd(null)}>
        {add && <div className="col gap-10" style={{ padding: 20, width: "min(460px, 92vw)" }} role="dialog" aria-label={t("mg.add_user")}>
          <h3>{t("mg.add_user")}</h3>
          <label className="field"><span>{t("mg.f.email")}</span><input className="input" type="email" value={add.email} onChange={(e) => setAdd({ ...add, email: e.target.value })} /></label>
          <label className="field"><span>{t("mg.f.name")}</span><input className="input" value={add.name} onChange={(e) => setAdd({ ...add, name: e.target.value })} /></label>
          <label className="field"><span>{t("mg.col.org")}</span><select className="select input" value={add.org_id} onChange={(e) => setAdd({ ...add, org_id: e.target.value, role: rolesFor(e.target.value)[0] || "" })}>{orgs.map((o) => <option key={o.id} value={o.id}>{o.name} · {t(`mg.kind.${o.kind}`)}</option>)}</select></label>
          <div className="row gap-8">
            <label className="field grow"><span>{t("mg.col.role")}</span><select className="select input" value={add.role} onChange={(e) => setAdd({ ...add, role: e.target.value })}>{rolesFor(add.org_id).map((r) => <option key={r} value={r}>{roleName(r)}</option>)}</select></label>
            <LocaleSelect value={add.locale} onChange={(v) => setAdd({ ...add, locale: v })} />
          </div>
          <p className="tiny muted">{t("mg.invite_hint")}</p>
          <div className="row gap-6"><button className="btn primary" disabled={!add.email.includes("@") || !add.name || !add.role} onClick={async () => { if (await run(() => api("/admin/users", { method: "POST", json: add }), t("mg.invited", { email: add.email }))) { setAdd(null); load(); } }}><Mail size={15} /> {t("mg.send_invite")}</button>
            <button className="btn ghost" onClick={() => setAdd(null)}>{t("common.cancel")}</button></div>
        </div>}
      </Modal>
    </div>
  );
}

// ------------------------------------------------------------------ platform: organisations
export function OrgsAdmin() {
  const { t } = useT();
  const run = useRun();
  const [kind, setKind] = useState("");
  const [rows, setRows] = useState<Org[] | null>(null);
  const [add, setAdd] = useState<{ name: string; kind: string } | null>(null);
  const [team, setTeam] = useState<Org | null>(null);
  const load = useCallback(() => api<Org[]>(withQs("/admin/organizations", kind ? `kind=${kind}` : "")).then(setRows).catch(() => setRows([])), [kind]);
  useEffect(() => { load(); }, [load]);
  if (!rows) return <Loading />;
  const rename = (o: Org) => { const name = prompt(t("mg.f.org_name"), o.name); if (name && name !== o.name) run(() => api(`/admin/organizations/${o.id}`, { method: "PATCH", json: { name } })).then(load); };
  return (
    <div className="col gap-10">
      <div className="row between wrap gap-8">
        <div className="row gap-4">{["", "bureau", "supplier", "platform"].map((k) => <button key={k} className={`chip ${kind === k ? "on" : ""}`} aria-pressed={kind === k} onClick={() => setKind(k)}>{k ? t(`mg.kind.${k}`) : t("mg.all")}</button>)}</div>
        <button className="btn primary" onClick={() => setAdd({ name: "", kind: "bureau" })}><Plus size={16} /> {t("mg.add_org")}</button>
      </div>
      <div className="card" style={{ overflow: "auto" }}>
        <table className="table compact"><thead><tr><th>{t("mg.col.org")}</th><th>{t("mg.col.kind")}</th><th className="right">{t("mg.col.users")}</th><th className="right">{t("mg.col.projects")}</th><th>{t("common.status")}</th><th /></tr></thead>
          <tbody>{rows.map((o) => <tr key={o.id}>
            <td><b className="small">{o.name}</b><div className="tiny muted">{o.created_at ? dt(o.created_at) : ""}</div></td>
            <td><Badge>{t(`mg.kind.${o.kind}`)}</Badge></td><td className="right">{o.users}</td><td className="right">{o.projects}</td>
            <td><Badge tone={STATUS_TONE[o.status]}>{t(`mg.status.${o.status}`)}</Badge></td>
            <td><div className="row gap-4 wrap">
              {o.kind === "bureau" && <Link className="btn sm" to={`/app/bureau?org=${o.id}`}>{t("mg.open_cabinet_btn")}</Link>}
              {o.kind === "supplier" && o.supplier_id && <Link className="btn sm" to={`/app/supplier?supplier=${o.supplier_id}`}>{t("mg.open_cabinet_btn")}</Link>}
              {o.kind !== "platform" && <button className="btn sm ghost" onClick={() => setTeam(o)}><Users size={14} /> {t("mg.team_title")}</button>}
              {o.kind !== "platform" && <button className="icon-btn" aria-label={t("mg.rename")} title={t("mg.rename")} onClick={() => rename(o)}><Pencil size={14} /></button>}
              {o.kind !== "platform" && (o.status === "active"
                ? <button className="btn sm danger" onClick={() => confirm(t("mg.confirm_suspend_org", { name: o.name })) && run(() => api(`/admin/organizations/${o.id}`, { method: "PATCH", json: { status: "suspended" } })).then(load)}>{t("mg.suspend")}</button>
                : <button className="btn sm" onClick={() => run(() => api(`/admin/organizations/${o.id}`, { method: "PATCH", json: { status: "active" } })).then(load)}>{t("mg.activate")}</button>)}
            </div></td></tr>)}</tbody></table>
      </div>
      <Drawer open={!!team} onClose={() => { setTeam(null); load(); }} title={team?.name || ""}>{team && <TeamCard orgId={team.id} />}</Drawer>
      <Modal open={!!add} onClose={() => setAdd(null)}>
        {add && <div className="col gap-10" style={{ padding: 20, width: "min(420px, 92vw)" }} role="dialog" aria-label={t("mg.add_org")}>
          <h3>{t("mg.add_org")}</h3>
          <label className="field"><span>{t("mg.f.org_name")}</span><input className="input" value={add.name} onChange={(e) => setAdd({ ...add, name: e.target.value })} /></label>
          <label className="field"><span>{t("mg.col.kind")}</span><select className="select input" value={add.kind} onChange={(e) => setAdd({ ...add, kind: e.target.value })}>{["bureau", "supplier"].map((k) => <option key={k} value={k}>{t(`mg.kind.${k}`)}</option>)}</select></label>
          <p className="tiny muted">{t("mg.add_org_hint")}</p>
          <div className="row gap-6"><button className="btn primary" disabled={add.name.trim().length < 2} onClick={async () => { if (await run(() => api("/admin/organizations", { method: "POST", json: add }))) { setAdd(null); load(); } }}>{t("common.save")}</button>
            <button className="btn ghost" onClick={() => setAdd(null)}>{t("common.cancel")}</button></div>
        </div>}
      </Modal>
    </div>
  );
}

// ------------------------------------------------------------------ platform: suppliers
type SupForm = { name: string; kind: string; city: string; website: string; commission_pct: number; org_id: string; verification: string; phone: string; email: string };

export function SuppliersAdmin() {
  const { t } = useT();
  const run = useRun();
  const [q, setQ] = useState("");
  const [rows, setRows] = useState<SupplierRow[] | null>(null);
  const [orgs, setOrgs] = useState<Org[]>([]);
  const [form, setForm] = useState<{ id: string | null; f: SupForm } | null>(null);
  const load = useCallback(() => api<SupplierRow[]>(`/admin/suppliers/all?${new URLSearchParams({ q })}`).then(setRows).catch(() => setRows([])), [q]);
  useEffect(() => { const tm = setTimeout(load, 250); return () => clearTimeout(tm); }, [load]);
  useEffect(() => { api<Org[]>("/admin/organizations?kind=supplier").then(setOrgs).catch(() => {}); }, []);
  if (!rows) return <Loading />;
  const open = (s?: SupplierRow) => setForm(s
    ? { id: s.id, f: { name: s.name, kind: s.kind, city: s.city, website: s.website, commission_pct: s.commission_pct, org_id: s.org_id || "", verification: s.verification, phone: s.contacts?.phone || "", email: s.contacts?.email || "" } }
    : { id: null, f: { name: "", kind: "store", city: "", website: "", commission_pct: 0, org_id: "", verification: "verified", phone: "", email: "" } });
  const save = async () => {
    if (!form) return;
    const body = { ...form.f, org_id: form.f.org_id || null };
    if (await run(() => api(form.id ? `/admin/suppliers/${form.id}` : "/admin/suppliers", { method: form.id ? "PATCH" : "POST", json: body }))) { setForm(null); load(); }
  };
  const F = (k: keyof SupForm, type = "text") => form && <label className="field"><span>{t(`mg.sf.${k}`)}</span><input className="input" type={type} value={String(form.f[k])} onChange={(e) => setForm({ ...form, f: { ...form.f, [k]: type === "number" ? Number(e.target.value) : e.target.value } })} /></label>;
  return (
    <div className="col gap-10">
      <div className="row between wrap gap-8">
        <label className="row gap-4 input" style={{ height: 38, minWidth: 260 }}><Search size={15} /><input aria-label={t("common.search")} placeholder={t("common.search")} value={q} onChange={(e) => setQ(e.target.value)} style={{ border: 0, outline: 0, background: "transparent", width: "100%" }} /></label>
        <button className="btn primary" onClick={() => open()}><Plus size={16} /> {t("mg.add_supplier")}</button>
      </div>
      <div className="card" style={{ overflow: "auto" }}>
        {!rows.length ? <Empty>{t("mg.no_suppliers")}</Empty> :
          <table className="table compact"><thead><tr><th>{t("mg.col.supplier")}</th><th>{t("mg.col.kind")}</th><th>{t("mg.col.org")}</th><th className="right">{t("mg.col.products")}</th><th className="right">{t("supc.commission")}</th><th>{t("mg.col.verification")}</th><th /></tr></thead>
            <tbody>{rows.map((s) => <tr key={s.id}>
              <td><b className="small">{s.name}</b> {s.is_demo && <Badge tone="danger">DEMO</Badge>}<div className="tiny muted">{s.city}{s.website ? ` · ${s.website}` : ""}</div></td>
              <td className="small">{t(`sob.kind.${s.kind}`)}</td><td className="small">{s.org_name || <span className="muted">{t("mg.no_org")}</span>}</td>
              <td className="right">{s.products}</td><td className="right">{s.commission_pct}%</td>
              <td><Badge tone={STATUS_TONE[s.verification]}>{t(`sob.v.${s.verification}`)}</Badge></td>
              <td><div className="row gap-4 wrap"><Link className="btn sm" to={`/app/supplier?supplier=${s.id}`}>{t("mg.open_cabinet_btn")}</Link>
                <button className="icon-btn" aria-label={t("mg.edit")} title={t("mg.edit")} onClick={() => open(s)}><Pencil size={14} /></button>
                <button className="icon-btn" aria-label={t("common.delete")} title={t("common.delete")} onClick={() => confirm(t("mg.confirm_delete_supplier", { name: s.name, n: s.products })) && run(() => api(`/admin/suppliers/${s.id}`, { method: "DELETE" })).then(load)}><Trash2 size={14} /></button></div></td>
            </tr>)}</tbody></table>}
      </div>
      <Drawer open={!!form} onClose={() => setForm(null)} title={form?.id ? t("mg.edit_supplier") : t("mg.add_supplier")}
        footer={<div className="row gap-6"><button className="btn primary" disabled={!form || form.f.name.trim().length < 2} onClick={save}>{t("common.save")}</button><button className="btn ghost" onClick={() => setForm(null)}>{t("common.cancel")}</button></div>}>
        {form && <div className="col gap-10">
          {F("name")}
          <div className="grid g2">
            <label className="field"><span>{t("mg.sf.kind")}</span><select className="select input" value={form.f.kind} onChange={(e) => setForm({ ...form, f: { ...form.f, kind: e.target.value } })}>{["store", "manufacturer", "installer"].map((k) => <option key={k} value={k}>{t(`sob.kind.${k}`)}</option>)}</select></label>
            {F("city")}{F("website")}{F("commission_pct", "number")}{F("phone")}{F("email", "email")}
            <label className="field"><span>{t("mg.sf.verification")}</span><select className="select input" value={form.f.verification} onChange={(e) => setForm({ ...form, f: { ...form.f, verification: e.target.value } })}>{["pending", "verified", "rejected"].map((k) => <option key={k} value={k}>{t(`sob.v.${k}`)}</option>)}</select></label>
            <label className="field"><span>{t("mg.sf.org_id")}</span><select className="select input" value={form.f.org_id} onChange={(e) => setForm({ ...form, f: { ...form.f, org_id: e.target.value } })}><option value="">{t("mg.no_org")}</option>{orgs.map((o) => <option key={o.id} value={o.id}>{o.name}</option>)}</select></label>
          </div>
          <p className="tiny muted">{t("mg.supplier_org_hint")}</p>
        </div>}
      </Drawer>
    </div>
  );
}
