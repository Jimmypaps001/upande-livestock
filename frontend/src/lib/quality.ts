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
