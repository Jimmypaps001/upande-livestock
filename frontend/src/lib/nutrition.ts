import { call, type Envelope } from "@/lib/frappe";

/* ── Wire shapes ────────────────────────────────────────────────────────────
   Named after the keys serverscripts/feeding/feed_nutrition.py returns. The
   page sends facts (item and kilos); every figure, the recursive expansion of
   made feeds and the verdict on missing data are the server's. */

export type NutrientLine = { item_code: string; qty: number };

export type MissingFeed = {
  item_code: string;
  item_name: string;
  reason: string;
  fields: string[];
  qty_kg: number;
  via: string | null;
};

export type NutritionLine = {
  item_code: string;
  item_name: string;
  qty: number;
  /** A made feed, expanded through its BOM. */
  made: boolean;
  /** What a typed Lab analysis on a made feed says, shown beside the computed one. */
  lab_check?: Record<string, number>;
  computed?: { cp_pct: number; carbohydrate_pct: number; me_mj_per_kg: number };
};

export type Nutrition = {
  as_fed_kg: number;
  dm_kg: number;
  dm_pct: number;
  cp_pct: number;
  carbohydrate_pct: number;
  ndf_pct: number;
  fat_pct: number;
  me_mj_per_kg: number;
  me_mj_total: number;
  ca_pct: number;
  p_pct: number;
  cost: number;
  cost_per_kg_as_fed: number;
  cost_per_kg_dm: number;
  missing: MissingFeed[];
  unpriced: Array<{ item_code: string; item_name: string }>;
  lines: NutritionLine[];
};

export type LibraryFeed = {
  item_code: string;
  item_name: string;
  category: string | null;
  is_made: boolean;
  /** Has a Livestock Feed record to open in the desk. */
  recorded?: boolean;
  /** Made feeds' figures are computed from their recipe, never typed. */
  computed?: boolean;
  has_data: boolean;
  nutrient_source: string | null;
  dry_matter_pct: number;
  cp_pct: number;
  carbohydrate_pct: number;
  ndf_pct: number;
  fat_pct: number;
  me_mj_per_kg: number;
};

export type FeedLibrary = {
  feeds: LibraryFeed[];
  /** Feed items nobody has described yet. */
  undescribed: Array<{ item_code: string; item_name: string; has_data: false }>;
  premanufacture_concentrate: boolean;
};

const NS = "upande_livestock.serverscripts.feeding";

export function feedNutrition(lines: NutrientLine[]): Promise<Envelope<Nutrition>> {
  return call<Nutrition>(`${NS}.feed_nutrition.feed_nutrition`, { lines: JSON.stringify(lines) });
}

export function recipeNutrition(bom: string): Promise<Envelope<Nutrition>> {
  return call<Nutrition>(`${NS}.feed_nutrition.recipe_nutrition`, { bom });
}

export function livestockFeeds(): Promise<Envelope<FeedLibrary>> {
  return call<FeedLibrary>(`${NS}.feed_nutrition.livestock_feeds`);
}

/** Rewrite lines so no concentrate is left in them — the server does the
 *  scaling from each concentrate's BOM. */
export function expandConcentrates(
  lines: NutrientLine[],
): Promise<Envelope<{ lines: Array<NutrientLine & { item_name: string }>; expanded: string[] }>> {
  return call(`${NS}.expand_concentrate.expand_concentrates`, { payload: { lines } });
}

/* ── Manufacture all ──────────────────────────────────────────────────── */

export type AllFeedsHerd = {
  herd: string;
  heads: number;
  portion: number;
  qty: number;
  short?: Array<{ item_code: string; item_name: string; short_qty: number; uom: string }>;
  status?: "made" | "waiting for stock" | "error";
  work_order?: string;
  produced_qty?: number;
  uom?: string;
  warnings?: string[];
  error?: string;
};

export type AllFeedsConcentrate = {
  item_code: string;
  item_name: string;
  qty: number;
  batches?: number;
  uom?: string;
  can_manufacture?: boolean;
  work_order?: string;
  warning?: string;
};

export type AllFeeds = {
  preview: boolean;
  date: string;
  premanufacture_concentrate: boolean;
  concentrates: AllFeedsConcentrate[];
  herds: AllFeedsHerd[];
  skipped: Array<{ herd: string; reason: string }>;
};

export function manufactureAllFeeds(args: {
  date?: string;
  portion?: number;
  preview?: boolean;
}): Promise<Envelope<AllFeeds>> {
  return call<AllFeeds>(`${NS}.manufacture_all_feeds.manufacture_all_feeds`, {
    date: args.date,
    portion: args.portion ?? 1,
    preview: args.preview ? 1 : 0,
  });
}

/* ── Small helpers the screens share ─────────────────────────────────── */

export const CATEGORIES = [
  "Forage",
  "Energy (grain / by-product)",
  "Protein",
  "Mineral & vitamin",
  "Additive",
  "Concentrate (made)",
  "Ration (made)",
] as const;

export function hasNutrition(r: unknown): r is Nutrition {
  return !!r && typeof (r as Nutrition).as_fed_kg === "number" && Array.isArray((r as Nutrition).missing);
}
