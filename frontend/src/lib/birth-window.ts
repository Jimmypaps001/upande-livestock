/**
 * The birth window, and the retro path for a birth outside it.
 *
 * A birth is recorded straight away when the dam has a confirmed pregnancy, or
 * a service that puts the birth between service + min and service + max days
 * (Livestock Settings → Birth Window; 270–295 for cattle). Otherwise the server
 * refuses with `code: "birth_needs_service"`, and the missing service — and,
 * where the farm allows, its pregnancy diagnosis, and the herd she was in that
 * day — are back-recorded with the birth in one request (common/retro_birth).
 *
 * The server decides (birth_check, record_birth). The date arithmetic here only
 * keeps the form from offering a date it would refuse.
 */
import { call } from "@/lib/frappe";
import { parseYmd, ymd } from "@/lib/utils";

const NS = "upande_livestock.serverscripts";

/** The `code` a refused birth carries. */
export const NEEDS_SERVICE = "birth_needs_service";

/** `iso` moved by `days` (negative = earlier), as YYYY-MM-DD; "" for a bad date. */
export function addDays(iso: string, days: number): string {
  const d = parseYmd(iso);
  if (!d) return "";
  return ymd(new Date(d.getFullYear(), d.getMonth(), d.getDate() + days));
}

/** The service dates that put a birth on `birthDate` inside [min, max] days. */
export function serviceRangeFor(birthDate: string, minDays: number, maxDays: number): { from: string; to: string } {
  const [low, high] = minDays <= maxDays ? [minDays, maxDays] : [maxDays, minDays];
  return { from: addDays(birthDate, -high), to: addDays(birthDate, -low) };
}

/** Does a service on `serviceDate` put a birth on `birthDate` inside the window? */
export function fitsWindow(serviceDate: string, birthDate: string, minDays: number, maxDays: number): boolean {
  if (!serviceDate || !birthDate) return false;
  const { from, to } = serviceRangeFor(birthDate, minDays, maxDays);
  return !!from && from <= serviceDate && serviceDate <= to;
}

/** A back-recorded diagnosis must fall strictly between the service and the birth. */
export function pdDateValid(pdDate: string, serviceDate: string, birthDate: string): boolean {
  if (!pdDate || !serviceDate || !birthDate) return false;
  return serviceDate < pdDate && pdDate < birthDate;
}

/** Days from one ISO date to another (b − a). */
export function daysBetween(a: string, b: string): number | null {
  const x = parseYmd(a);
  const y = parseYmd(b);
  if (!x || !y) return null;
  return Math.round((Date.UTC(y.getFullYear(), y.getMonth(), y.getDate()) -
    Date.UTC(x.getFullYear(), x.getMonth(), x.getDate())) / 86_400_000);
}

/** What birth_check (and a refused record_birth) answers. */
export interface BirthCheck {
  ok?: boolean;
  allowed?: boolean;
  basis?: { kind: "diagnosis" | "service"; service: string; service_date: string } | null;
  message?: string;
  current_herd?: string;
  dam: string;
  birth_date: string;
  window: { min_days: number; max_days: number };
  service_from: string;
  service_to: string;
  retro_allowed: boolean;
  retro_refusal: string;
  is_manager: boolean;
  backdating_open: boolean;
  allow_diagnosis: boolean;
  herd_on_service_date?: string;
  service_date_fits?: boolean;
}

export const birthCheck = (p: { dam: string; birth_date?: string; service_date?: string }) =>
  call<BirthCheck>(`${NS}.breeding.birth_check.birth_check`, { payload: p });

/** Is this answer the server's "record the service first" refusal? */
export function needsService(r: unknown): r is { error: string; code: string } & BirthCheck {
  return !!r && typeof r === "object" && (r as { code?: unknown }).code === NEEDS_SERVICE;
}

/** What the person fills in on the retro path. */
export interface RetroForm {
  service_date: string;
  service_type: string;
  sire: string;
  /** Straw item code ("" for none / natural service). */
  straw: string;
  straw_qty: string;
  straw_store: string;
  with_diagnosis: boolean;
  diagnosis_date: string;
  herd: string;
}

export const blankRetro = (): RetroForm => ({
  service_date: "",
  service_type: "",
  sire: "",
  straw: "",
  straw_qty: "1",
  straw_store: "",
  with_diagnosis: false,
  diagnosis_date: "",
  herd: "",
});

/** What is still missing or wrong before the retro path may be sent; [] when ready. */
export function retroProblems(f: RetroForm, birthDate: string, check: BirthCheck): string[] {
  const out: string[] = [];
  const { min_days, max_days } = check.window;
  if (!f.service_date) out.push("Give the service date.");
  else if (!fitsWindow(f.service_date, birthDate, min_days, max_days))
    out.push(`The service must be between ${check.service_from} and ${check.service_to}.`);
  if (!f.service_type) out.push("Say how she was served.");
  if (!f.herd) out.push("Choose the herd she was in on the service date.");
  if (f.with_diagnosis) {
    if (!check.allow_diagnosis) out.push("Settings do not allow a diagnosis here.");
    else if (!pdDateValid(f.diagnosis_date, f.service_date, birthDate))
      out.push("The diagnosis must be dated after the service and before the birth.");
  }
  return out;
}

/** The `retro` block record_birth takes. */
export function retroPayload(f: RetroForm, check: BirthCheck): Record<string, unknown> {
  // Both shapes: the items table where Service posts stock, the straw fields
  // where it does not (create_service_event.build_service reads whichever applies).
  const qty = Number(f.straw_qty) || 1;
  const store = f.straw_store || undefined;
  const straw = f.straw
    ? {
        items: [{ item_code: f.straw, qty, source_warehouse: store }],
        semen_item: f.straw,
        semen_qty: qty,
        semen_warehouse: store,
      }
    : {};
  return {
    service_date: f.service_date,
    service_type: f.service_type,
    sire: f.sire || undefined,
    ...straw,
    herd: f.herd,
    diagnosis: f.with_diagnosis && check.allow_diagnosis ? { diagnosis_date: f.diagnosis_date } : null,
  };
}

