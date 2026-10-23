import { createContext, useContext } from "react";

/** Cabinet scope: platform staff open a bureau (`org_id=…`) or a supplier (`supplier_id=…`) cabinet;
 *  every cabinet request carries the same query so reads and edits land in the chosen organisation. */
export const ScopeCtx = createContext<{ qs: string }>({ qs: "" });
export const useScope = () => useContext(ScopeCtx);
export const withQs = (path: string, qs: string) => (qs ? `${path}${path.includes("?") ? "&" : "?"}${qs}` : path);
