import { useSearchParams } from "react-router-dom";
import { CreditCard, Wallet } from "lucide-react";
import { useT } from "../i18n";
import FinanceTab from "../components/FinanceTab";
import BillingAdmin from "../components/BillingAdmin";

type Tab = "ledger" | "billing";

/** Platform finance as its own section: ledger, revenue and settlements; tariffs and card payments. */
export default function Finance() {
  const { t } = useT();
  const [sp, setSp] = useSearchParams();
  const tab = (sp.get("tab") as Tab) || "ledger";
  const tabs: [Tab, typeof Wallet][] = [["ledger", Wallet], ["billing", CreditCard]];
  return (
    <div className="col gap-16">
      <div><h1>{t("nav.finance")}</h1><p className="muted" style={{ margin: 0 }}>{t("fin.section_lead")}</p></div>
      <div className="tabs" role="tablist">{tabs.map(([k, I]) => <button key={k} role="tab" aria-selected={tab === k} className={`tab ${tab === k ? "on" : ""}`} onClick={() => setSp({ tab: k })}><I size={16} /> {t(`fin.tab.${k}`)}</button>)}</div>
      {tab === "ledger" && <FinanceTab />}
      {tab === "billing" && <BillingAdmin />}
    </div>
  );
}
