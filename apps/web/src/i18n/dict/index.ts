import type { Dict } from "../index";
import { common } from "./common";
import { enums } from "./enums";
import { errors, notices, rules, steps, works } from "./system";
import { pages } from "./pages";
import { projects } from "./projects";
import { workspace } from "./workspace";
import { account } from "./account";
import { management } from "./management";
import { cabinets } from "./cabinets";
import { billing } from "./billing";

export const DICT: Dict = { ...common, ...enums, ...errors, ...steps, ...rules, ...notices, ...works, ...pages, ...projects, ...workspace, ...account, ...management, ...cabinets, ...billing };
