import { call, isError, type Envelope } from "@/lib/frappe";

/**
 * Recording a milking.
 *
 * Two endpoints, both of which already existed — nothing was written on the
 * server for this page:
 *
 *  * `milking_options` — the herds that are actually IN MILK. It derives the
 *    lactation groups from Herd Movement settings rather than from a
 *    hand-marked list, because a hand-marked list drifts the first time a herd
 *    is renamed. This page offers exactly what it answers and nothing else: the
 *    full herd list would let a milking be recorded against calves or dry cows.
 *  * `create_milk_recording` — inserts and submits a Milk Recording.
 *
 * A note on the yield field, because it has been got wrong here before: the
 * quantity is `total_yield_kg`. Not `quantity`, not `yield`. Every quantity on
 * this doctype is `*_kg` and the price on Livestock Settings is per kg, so
 * nothing in this module converts a unit — see lib/production.ts for the same
 * rule stated at greater length.
 *
 * Recent recordings are read through `frappe.client.get_list`, the framework's
 * own permission-checked read — the same door lib/frappe.ts already uses for
 * the item master. A user who may not read Milk Recording gets an empty list
 * from it, which is the correct answer rather than a leak.
 */

const MILKING_OPTIONS =
  "upande_livestock.serverscripts.milking.milking_options.milking_options";
const CREATE_MILK_RECORDING =
  "upande_livestock.serverscripts.milking.create_milk_recording.create_milk_recording";
const GET_LIST = "frappe.client.get_list";

export type MilkingHerd = { name: string; label: string };

export type MilkingOptions = {
  herds: MilkingHerd[];
  /** The lactation groups the server derived. Empty means "no restriction". */
  restricted_to: string[];
  company: string | null;
  employee: string | null;
};

/** Exactly the Select options on Milk Recording.discard_reason. */
export const DISCARD_REASONS = [
  "Mastitis",
  "Antibiotic withdrawal",
  "Colostrum",
  "Spoiled / soured",
  "Spilled",
  "Failed quality test",
  "Other",
] as const;

/** What the operator has typed. Strings throughout — these are input values. */
export type MilkingForm = {
  herd: string;
  milkingTime: string;
  cowsMilked: string;
  totalYieldKg: string;
  discardedKg: string;
  discardReason: string;
  discardNotes: string;
  pricePerKg: string;
  proteinPercent: string;
  bulkScc: string;
  remarks: string;
};

export function emptyForm(): MilkingForm {
  return {
    herd: "",
    milkingTime: nowHM(),
    cowsMilked: "",
    totalYieldKg: "",
    discardedKg: "",
    discardReason: "",
    discardNotes: "",
    pricePerKg: "",
    proteinPercent: "",
    bulkScc: "",
    remarks: "",
  };
}

/**
 * The body `create_milk_recording` reads.
 *
 * Named for the server's own keys rather than the form's, and built in one
 * place so the naming is asserted by a test instead of by memory.
 * `recording_date` is what `backdate.resolve(d, "recording_date")` looks for
 * after `event_date`; a past date there is what stamps the record backdated.
 */
export type MilkPayload = {
  herd: string;
  milking_time: string;
  recording_date: string;
  cows_milked: number;
  total_yield_kg: number;
  discarded_kg: number;
  discard_reason?: string;
  discard_reason_notes?: string;
  price_per_kg: number;
  protein_percent?: number;
  bulk_scc?: number;
  remarks?: string;
  company?: string;
  operator?: string;
};

export type MilkResult = {
  name: string;
  net_yield_kg: number;
  revenue: number;
  stock_entry: string | null;
  journal_entry: string | null;
};

function n(v: string): number {
  const parsed = parseFloat(v);
  return Number.isFinite(parsed) ? parsed : 0;
}

/** Total less discarded — what actually reaches the tank, and what the Stock
 *  Entry is built from. Never negative on this side; the server refuses one. */
export function netYield(totalKg: number, discardedKg: number): number {
  return totalKg - discardedKg;
}

export function revenue(netKg: number, pricePerKg: number): number {
  return netKg * pricePerKg;
}

export function formNet(form: MilkingForm): number {
  return netYield(n(form.totalYieldKg), n(form.discardedKg));
}

export function formRevenue(form: MilkingForm): number {
  return revenue(formNet(form), n(form.pricePerKg));
}

/**
 * The checks the browser can make before spending a round trip.
 *
 * Deliberately a subset of the doctype's own `validate` — the server stays the
 * authority, and whatever it refuses is surfaced unchanged. These exist only so
 * an obvious slip does not need a network call to be caught.
 */
export function validateForm(form: MilkingForm): string | null {
  if (!form.herd) return "Select a herd.";
  if (!form.milkingTime) return "Enter the time this herd was milked.";
  const total = n(form.totalYieldKg);
  if (total <= 0) return "Total yield must be greater than zero.";
  const discarded = n(form.discardedKg);
  if (discarded < 0) return "Discarded milk cannot be negative.";
  if (discarded > total) return "Discarded milk cannot exceed the total yield.";
  if (discarded > 0 && !form.discardReason)
    return "Say why the milk was discarded — it is a loss, and an unexplained loss cannot be acted on.";
  if (form.discardReason === "Other" && !form.discardNotes.trim())
    return "Describe the reason for the discard.";
  return null;
}

export function buildPayload(
  form: MilkingForm,
  date: string,
  ctx: { company?: string | null; operator?: string | null } = {},
): MilkPayload {
  const discarded = n(form.discardedKg);
  const payload: MilkPayload = {
    herd: form.herd,
    milking_time: form.milkingTime,
    recording_date: date,
    cows_milked: Math.max(0, Math.round(n(form.cowsMilked))),
    total_yield_kg: n(form.totalYieldKg),
    discarded_kg: discarded,
    price_per_kg: n(form.pricePerKg),
  };
  if (discarded > 0 && form.discardReason) payload.discard_reason = form.discardReason;
  if (form.discardNotes.trim()) payload.discard_reason_notes = form.discardNotes.trim();
  if (form.proteinPercent) payload.protein_percent = n(form.proteinPercent);
  if (form.bulkScc) payload.bulk_scc = n(form.bulkScc);
  if (form.remarks.trim()) payload.remarks = form.remarks.trim();
  if (ctx.company) payload.company = ctx.company;
  if (ctx.operator) payload.operator = ctx.operator;
  return payload;
}

/** "HH:MM" now, in the farm's wall clock — the same reasoning as todayISO(). */
export function nowHM(): string {
  const d = new Date();
  const p = (x: number) => String(x).padStart(2, "0");
  return `${p(d.getHours())}:${p(d.getMinutes())}`;
}

/** MariaDB hands back "9:40:00" as readily as "09:40:00". Show "09:40". */
export function formatTime(t: string | null | undefined): string {
  if (!t) return "—";
  const parts = String(t).split(":");
  if (parts.length < 2) return String(t);
  const h = parts[0].padStart(2, "0");
  const m = parts[1].padStart(2, "0");
  return `${h}:${m}`;
}

export function milkingOptions(): Promise<Envelope<MilkingOptions>> {
  return call(MILKING_OPTIONS, {});
}

export function createMilkRecording(
  payload: MilkPayload,
): Promise<Envelope<MilkResult>> {
  return call(CREATE_MILK_RECORDING, { payload });
}

/** One row of the "already recorded" list. */
export type RecentMilking = {
  name: string;
  recording_date: string;
  milking_time: string | null;
  herd: string;
  cows_milked: number;
  total_yield_kg: number;
  discarded_kg: number;
  net_yield_kg: number;
  custom_is_backdated: 0 | 1;
};

const RECENT_FIELDS = [
  "name",
  "recording_date",
  "milking_time",
  "herd",
  "cows_milked",
  "total_yield_kg",
  "discarded_kg",
  "net_yield_kg",
  "custom_is_backdated",
];

/**
 * The last few recordings, newest first — the operator's answer to "did
 * somebody already enter this one?". Filtered to the chosen herd when there is
 * one, because that is the question actually being asked at the parlour.
 */
export async function recentMilkings(
  herd?: string,
  limit = 8,
): Promise<{ rows: RecentMilking[]; error?: string }> {
  const r = await call<RecentMilking[]>(GET_LIST, {
    doctype: "Milk Recording",
    fields: RECENT_FIELDS,
    filters: herd ? { herd } : undefined,
    order_by: "recording_date desc, milking_time desc",
    limit_page_length: limit,
  });
  if (isError(r)) return { rows: [], error: r.error };
  return { rows: Array.isArray(r) ? r : [] };
}
