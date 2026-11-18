/**
 * The Gallagher weigh-scale import: what the server's preview says about a
 * file and what the commit did with it (serverscripts/weights/gallagher_import).
 *
 * The browser holds the file between the two calls and sends it both times, so
 * the server keeps nothing and a stale preview cannot record what the file does
 * not say.
 */
import { call, type Envelope } from "@/lib/frappe";

const NS = "upande_livestock.serverscripts.weights.gallagher_import";

export type RowStatus = "ready" | "already_recorded" | "repeat" | "unmatched" | "invalid";

export interface GallagherRow {
  row: number;
  vid: string;
  eid: string;
  date: string | null;
  date_text: string;
  time: string;
  weight_kg: number;
  notes: string;
  animal: string | null;
  label: string;
  herd: string;
  herd_label: string;
  matched_by: "eid" | "vid" | null;
  status: RowStatus;
  why: string | null;
  last_weight_date: string | null;
  older_than_last: boolean;
}

export interface DateRef {
  row: number;
  vid: string;
  eid: string;
  animal: string | null;
  label: string;
  date: string;
  last_weight_date: string | null;
}

/** How slash dates (9/15/2026) were read: month first or day first, once per file. */
export type DateOrder = "auto" | "mdy" | "dmy";

export interface GallagherPreview {
  date_order: {
    used: "mdy" | "dmy";
    asked: DateOrder;
    /** True when the file's own dates decided it; false when it could not say. */
    settled: boolean;
    day_first_rows: number;
    month_first_rows: number;
  };
  file: { name: string; format: string; rows: number };
  dates: {
    from: string | null;
    to: string | null;
    per_date: { date: string; rows: number; future: number; already_recorded: number }[];
    unreadable: number;
    future: DateRef[];
    older_than_last: DateRef[];
    repeats: DateRef[];
    already_recorded: DateRef[];
    on_several_days: string[];
    notes: string[];
  };
  summary: {
    rows: number;
    matched_rows: number;
    matched_animals: number;
    unmatched_rows: number;
    invalid_rows: number;
    to_record: number;
    already_recorded: number;
    repeats: number;
    active_animals: number;
    weighed_active: number;
    not_weighed: number;
  };
  rows: GallagherRow[];
  unmatched: GallagherRow[];
  herds: {
    herd: string;
    label: string;
    active: number;
    weighed: number;
    not_weighed: number;
    in_file: boolean;
  }[];
  scope_herds: string[];
  not_weighed: {
    animal: string;
    label: string;
    tag: string;
    herd: string;
    herd_label: string;
    last_weight_date: string | null;
    last_weight_kg: number | null;
  }[];
  default_method: string;
}

export interface GallagherResult {
  recorded: number;
  already_recorded: number;
  not_recorded: number;
  failed: { row: number; animal: string; label: string; why: string }[];
  eids_filled: number;
  method: string;
}

/** A file as the two calls carry it: base64, so a spreadsheet survives JSON. */
export interface GallagherFile {
  filename: string;
  content: string;
}

export function readFile(file: File): Promise<GallagherFile> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onerror = () => reject(new Error("The file could not be read."));
    reader.onload = () => {
      const url = String(reader.result || "");
      resolve({ filename: file.name, content: url.slice(url.indexOf(",") + 1) });
    };
    reader.readAsDataURL(file);
  });
}

const post = <T>(method: string, payload: Record<string, unknown>): Promise<Envelope<T>> =>
  call<T>(`${NS}.${method}`, { payload });

export const previewGallagher = (f: GallagherFile, herds: string[] = [], date_order: DateOrder = "auto") =>
  post<GallagherPreview>("preview", { ...f, herds, date_order });

export const commitGallagher = (f: GallagherFile, herds: string[] = [], date_order: DateOrder = "auto") =>
  post<GallagherResult>("commit", { ...f, herds, date_order });
