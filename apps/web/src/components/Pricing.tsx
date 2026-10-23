import type { ReactNode } from "react";
import { Check } from "lucide-react";
import { useT } from "../i18n";
import { amd } from "../lib/format";

export interface PricePlan { key: string; name: string; audience: string; price_amd_month: number; price_amd_year?: number | null; price_from?: boolean; custom?: boolean;
  setup_amd?: number | null; max_projects?: number | null; seats?: number | null; extra_seat_amd?: number | null; storage_gb?: number | null; ai_credits_month?: number;
  ai_credits_once?: number; max_render?: string; sku_limit?: number | null; commission_pct?: number | null; designer_reward_pct?: number | null; features?: string[] }
export interface CreditPack { key: string; credits: number; price_amd: number; validity_months?: number }
export interface PublicPricing { version: string; bureau_plans: PricePlan[]; supplier_plans: PricePlan[]; credit_packs: CreditPack[]; credit_costs: Record<string, number>;
  trial: { days: number; credits: number; max_projects: number }; online_payments: boolean }

const nf = new Intl.NumberFormat("ru-RU");
// commercial-model features that the product does not have yet: shown, but marked «soon» — never promised as available
export const SOON = new Set(["tasks", "margin_reports", "designer_commission", "sso", "api", "own_domain", "client_tariffs", "revenue_share", "analytics"]);
export const amdN = (n: number) => amd(n);
const gb = (g: number) => (g < 1 ? `${Math.round(g * 1000)} MB` : g >= 1000 ? `${g / 1000} TB` : `${g} GB`);

/** Bullet points of a plan, derived from its numbers (never free text) so every language says the same. */
export function planBullets(p: PricePlan, t: (k: string, v?: Record<string, unknown>) => string): string[] {
  const out: string[] = [];
  if (p.seats) out.push(t("price.b.seats", { n: p.seats }) + (p.extra_seat_amd ? ` · ${t("price.b.extra_seat", { v: amdN(p.extra_seat_amd) })}` : ""));
  if (p.audience === "supplier" || p.audience === "manufacturer") {
    if (p.sku_limit) out.push(t("price.b.skus", { n: nf.format(p.sku_limit) }));
    if (p.commission_pct != null) out.push(t("price.b.commission", { n: p.commission_pct }));
  } else if (p.max_projects) out.push(t("price.b.projects", { n: p.max_projects }));
  else out.push(t("price.b.projects_contract"));
  if (p.storage_gb) out.push(t("price.b.storage", { v: gb(p.storage_gb) }));
  if (p.ai_credits_month) out.push(t("price.b.credits_month", { n: nf.format(p.ai_credits_month) }));
  if (p.ai_credits_once) out.push(t("price.b.credits_once", { n: p.ai_credits_once }));
  if (p.max_render) out.push(t(`price.b.render.${p.max_render.toLowerCase()}`));
  for (const f of p.features || []) out.push(t(`price.f.${f}`) + (SOON.has(f) ? ` · ${t("price.soon")}` : ""));
  return out;
}

export function PlanCard({ plan, interval, current, highlight, action }: { plan: PricePlan; interval: "month" | "year"; current?: boolean; highlight?: boolean; action?: ReactNode }) {
  const { t } = useT();
  const yearly = interval === "year" && plan.price_amd_year != null;
  const price = yearly ? plan.price_amd_year! : plan.price_amd_month;
  return (
    <article className={`card price-card ${highlight ? "hl" : ""} ${current ? "current" : ""}`} aria-label={plan.name}>
      <div className="row between"><h3>{plan.name}</h3>{current ? <span className="badge sage">{t("price.current")}</span> : highlight ? <span className="badge terra">{t("price.popular")}</span> : null}</div>
      <div className="price">
        {plan.custom && !price ? <b>{t("price.individual")}</b> : <>
          {plan.price_from && <span className="small muted">{t("price.from")} </span>}
          <b>{price === 0 ? t("price.free") : amdN(price)}</b>{price > 0 && <span className="small muted"> / {t(yearly ? "price.per_year" : "price.per_month")}</span>}
        </>}
      </div>
      {yearly && plan.price_amd_month > 0 && <div className="tiny" style={{ color: "var(--sage-ink)" }}>{t("price.year_saving", { v: amdN(plan.price_amd_month * 12 - price) })}</div>}
      {plan.setup_amd ? <div className="tiny muted">{t("price.setup", { v: amdN(plan.setup_amd) })}</div> : null}
      <ul className="bullets">{planBullets(plan, t).map((b) => <li key={b}><Check size={14} aria-hidden /> {b}</li>)}</ul>
      {action && <div className="mt-8" style={{ marginTop: "auto" }}>{action}</div>}
    </article>
  );
}
