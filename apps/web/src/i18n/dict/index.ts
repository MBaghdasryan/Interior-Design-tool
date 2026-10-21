import type { Dict } from "../index";
import { common } from "./common";
import { enums } from "./enums";
import { errors, notices, rules, steps, works } from "./system";
import { pages } from "./pages";
import { projects } from "./projects";
import { workspace } from "./workspace";

export const DICT: Dict = { ...common, ...enums, ...errors, ...steps, ...rules, ...notices, ...works, ...pages, ...projects, ...workspace };
