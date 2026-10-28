import { call } from "@/lib/frappe";

/**
 * A routine exit — sold, or slaughtered — recorded in one step.
 *
 * Both go straight through `record_disposal`: it creates and submits the
 * Livestock Disposal, which retires the animal and posts the sale. Death, gift
 * and a cull that needs the vet or a manager's signature stay on the Culling
 * screen; a bull going to the butcher does not need a case.
 */

const RECORD = "upande_livestock.serverscripts.disposal.record_disposal.record_disposal";
const OPTIONS = "upande_livestock.serverscripts.disposal.disposal_options.disposal_options";

export const EXIT_TYPES = ["Sold", "Slaughtered"] as const;
export type ExitType = (typeof EXIT_TYPES)[number];

export type ExitInput = {
  animal: string;
  type: ExitType;
  /** Blank when backdating is closed: the server dates the record itself. */
  date?: string;
  exitWeight?: string;
  pricePerKg?: string;
  customer?: string;
};

/** The record_disposal payload: price and customer only travel with a sale. */
export function exitPayload(i: ExitInput) {
  const sold = i.type === "Sold";
  return {
    animal: i.animal,
    disposal_type: i.type,
    disposal_date: i.date || undefined,
    exit_weight_kg: i.exitWeight ? Number(i.exitWeight) : undefined,
    price_per_kg: sold && i.pricePerKg ? Number(i.pricePerKg) : undefined,
    customer: sold && i.customer ? i.customer : undefined,
  };
}

/** What the form can refuse before the server does. */
export function validateExit(i: ExitInput): string | null {
  if (i.type === "Sold") {
    if (!(Number(i.pricePerKg) > 0)) return "Enter the price per kg the animal was sold at.";
    if (!i.customer) return "Choose the customer the sale is invoiced to.";
  }
  return null;
}

export function recordExit(i: ExitInput) {
  return call<{
    name: string;
    animal_status: string;
    exit_weight_kg: number | null;
    sale_price: number | null;
    final_adg_kg: number | null;
    /** Warned, not blocked: the farm decides, but it is told. */
    warnings: string[];
  }>(RECORD, { payload: exitPayload(i) });
}

export function getExitCustomers() {
  return call<{ customers: string[] }>(OPTIONS, {});
}
