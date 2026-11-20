/**
 * Milk quality — where the farm takes it, and what is still outstanding.
 *
 * The fields here move no stock and raise no journal, which is the whole
 * reason they are allowed to arrive after the milking has been submitted. The
 * quantities on the same recording do post, and none of them are touched from
 * this page.
 */
import { call, type Envelope } from "@/lib/frappe";

const OPTIONS = "upande_livestock.serverscripts.quality.quality_options.quality_options";
const RECORD = "upande_livestock.serverscripts.quality.record_milk_quality.record_milk_quality";

export type CaptureMode = "At milking" | "Afterwards";

export interface PendingRecording {
  name: string;
  herd: string;
  recording_date: string;
  milking_time: string | null;
  total_yield_kg: number;
  net_yield_kg: number;
  cows_milked: number;
}

export interface QualityResult {
  name: string;
  herd: string;
  recording_date: string;
  bulk_scc: number | null;
  fat_percent: number | null;
  protein_percent: number | null;
  lab_test_date: string | null;
  over_ceiling: boolean;
}

export interface QualityOptions {
  mode: CaptureMode;
  required_at_milking: boolean;
  required_in_lab: boolean;
  scc_ceiling: number;
  pending: PendingRecording[];
  recent: QualityResult[];
  can_write: boolean;
}

export function getQualityOptions(days = 60): Promise<Envelope<QualityOptions>> {
  return call<QualityOptions>(OPTIONS, { days });
}

export interface QualityEntry {
  recording: string;
  bulk_scc?: number;
  fat_percent?: number;
  protein_percent?: number;
  lab_test_date?: string;
  remarks?: string;
}

export function recordMilkQuality(entry: QualityEntry) {
  return call<{
    name: string;
    bulk_scc: number | null;
    fat_percent: number | null;
    protein_percent: number | null;
    over_ceiling: boolean;
    still_pending: boolean;
  }>(RECORD, { payload: entry });
}

/** The disclaimer shown when the lab boxes are left empty on the milking form. */
export const SKIPPED_NOTICE =
  "Left blank, this milking is filed as awaiting quality and appears on the " +
  "Quality page until a figure is entered. Nothing else about it changes — the " +
  "yield, the discard and the revenue post exactly as they would have.";

// ---------------------------------------------------------------------------
// The buyer's quality sheet (Milk Quality Test). The phone calls the same four
// server functions; the rules below only preview what the server will decide.

const TESTS = "upande_livestock.serverscripts.quality.quality_tests";

export type Chip = "pass" | "fail" | "warn" | null;
export type CheckKey = "resazurin" | "antibiotics" | "hydrogen_peroxide" | "frothing" | "aflatoxin";

export const CHECK_LABELS: Record<CheckKey, string> = {
  resazurin: "Resazurin",
  antibiotics: "Antibiotics",
  hydrogen_peroxide: "H₂O₂",
  frothing: "Frothing",
  aflatoxin: "Afla M1",
};

export interface QualityLimits {
  aflatoxin_limit_ppt: number;
  antibiotics_fail: boolean;
  resazurin_min_score: number;
}

export interface QualityTest {
  name: string;
  sample_date: string;
  shift: string;
  sample_type: string;
  buyer: string | null;
  milk_recording: string | null;
  quantity_l: number | null;
  receiving_temp_c: number | null;
  ph: number | null;
  tta: number | null;
  snf_percent: number | null;
  freezing_point: number | null;
  specific_gravity: number | null;
  protein_percent: number | null;
  butterfat_percent: number | null;
  resazurin_score: string;
  resazurin_result: string;
  antibiotics: string;
  hydrogen_peroxide: string;
  frothing: string;
  aflatoxin_ppt: number | null;
  sensory_score: string;
  sensory_note: string;
  overall_result: "Pass" | "Fail" | "Not assessed";
  failed_tests: string;
  aflatoxin_over_limit: boolean;
  remarks: string;
  lab_slip: string | null;
  recorded_by: string | null;
  checks: Record<CheckKey, Chip>;
}

export interface QualityTestOptions {
  date: string;
  default_buyer: string;
  sample_types: string[];
  shifts: string[];
  limits: QualityLimits;
  recordings: { name: string; herd: string; milking_time: string; net_yield_kg: number }[];
  can_write: boolean;
}

export interface QualityTestList {
  tests: QualityTest[];
  total: number;
  limits: QualityLimits;
  can_write: boolean;
}

export interface QualityTestFilters {
  from_date?: string;
  to_date?: string;
  buyer?: string;
  sample_type?: string;
  overall_result?: string;
}

/** Every field the form can send. Numbers stay strings until `payloadFrom`. */
export interface QualityTestForm {
  sample_date: string;
  shift: string;
  sample_type: string;
  buyer: string;
  milk_recording: string;
  quantity_l: string;
  receiving_temp_c: string;
  ph: string;
  tta: string;
  snf_percent: string;
  freezing_point: string;
  specific_gravity: string;
  protein_percent: string;
  butterfat_percent: string;
  resazurin_score: string;
  resazurin_result: string;
  antibiotics: string;
  hydrogen_peroxide: string;
  frothing: string;
  aflatoxin_ppt: string;
  sensory_score: string;
  sensory_note: string;
  remarks: string;
  lab_slip: string;
}

export const emptyForm = (date: string, buyer = ""): QualityTestForm => ({
  sample_date: date, shift: "", sample_type: "Bottle sample", buyer, milk_recording: "",
  quantity_l: "", receiving_temp_c: "", ph: "", tta: "", snf_percent: "", freezing_point: "",
  specific_gravity: "", protein_percent: "", butterfat_percent: "", resazurin_score: "",
  resazurin_result: "", antibiotics: "", hydrogen_peroxide: "", frothing: "", aflatoxin_ppt: "",
  sensory_score: "", sensory_note: "", remarks: "", lab_slip: "",
});

const NUMBER_FIELDS = [
  "quantity_l", "receiving_temp_c", "ph", "tta", "snf_percent", "freezing_point",
  "specific_gravity", "protein_percent", "butterfat_percent", "aflatoxin_ppt",
] as const;

/** Numbers are read with a comma or a dot; blanks are left out of the payload. */
export function payloadFrom(form: QualityTestForm): Record<string, string | number> {
  const out: Record<string, string | number> = {};
  for (const [k, v] of Object.entries(form)) {
    const text = String(v ?? "").trim();
    if (!text) continue;
    out[k] = (NUMBER_FIELDS as readonly string[]).includes(k) ? Number(text.replace(",", ".")) : text;
  }
  return out;
}

/** The first reason the form cannot be sent, or null. Mirrors the server. */
export function formProblem(form: QualityTestForm): string | null {
  for (const k of NUMBER_FIELDS) {
    const text = form[k].trim();
    if (text && !Number.isFinite(Number(text.replace(",", ".")))) return `${k.replace(/_/g, " ")} must be a number.`;
  }
  if (form.sensory_score.trim() && !/^[+\-−]?\d+$/.test(form.sensory_score.trim())) {
    return "Sensory score must be a whole number, such as +1, 0 or -1.";
  }
  const any = NUMBER_FIELDS.some((k) => k !== "quantity_l" && form[k].trim()) ||
    ["resazurin_score", "resazurin_result", "antibiotics", "hydrogen_peroxide", "frothing", "sensory_score"].some(
      (k) => form[k as keyof QualityTestForm].trim(),
    );
  return any ? null : "Enter at least one result.";
}

/** The deciding tests as the server judges them, for a live preview. */
export function previewChecks(form: QualityTestForm, lim: QualityLimits): Record<CheckKey, Chip> {
  let res: Chip = null;
  if (form.resazurin_result) res = form.resazurin_result === "Pass" ? "pass" : "fail";
  else if (form.resazurin_score !== "") res = Number(form.resazurin_score) >= lim.resazurin_min_score ? "pass" : "fail";
  const afla = Number(form.aflatoxin_ppt.replace(",", "."));
  return {
    resazurin: res,
    antibiotics: !form.antibiotics ? null : form.antibiotics === "Positive" ? (lim.antibiotics_fail ? "fail" : "warn") : "pass",
    hydrogen_peroxide: !form.hydrogen_peroxide ? null : form.hydrogen_peroxide === "Present" ? "fail" : "pass",
    frothing: !form.frothing ? null : form.frothing === "Pass" ? "pass" : "fail",
    aflatoxin: afla > 0 && lim.aflatoxin_limit_ppt > 0 ? (afla > lim.aflatoxin_limit_ppt ? "fail" : "pass") : null,
  };
}

export function previewOverall(checks: Record<CheckKey, Chip>): "Pass" | "Fail" | "Not assessed" {
  const v = Object.values(checks);
  return v.includes("fail") ? "Fail" : v.some(Boolean) ? "Pass" : "Not assessed";
}

export function getQualityTestOptions(date?: string) {
  return call<QualityTestOptions>(`${TESTS}.quality_test_options`, { date });
}

export function recordQualityTest(payload: Record<string, unknown>) {
  return call<{ name: string; duplicate: boolean; overall_result: string; failed_tests: string; test: QualityTest }>(
    `${TESTS}.record_quality_test`,
    { payload },
  );
}

export function getQualityTests(filters: QualityTestFilters = {}, limit = 50, start = 0) {
  return call<QualityTestList>(`${TESTS}.quality_tests`, { filters, limit, start });
}

export function getQualityTest(name: string) {
  return call<{ name: string; test: QualityTest }>(`${TESTS}.quality_test`, { name });
}
