import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { saleAmount } from "@/lib/culling";
import { fmt } from "@/lib/utils";

/**
 * The two figures a live sale is priced on, and what they come to.
 *
 * Cattle sell by the kilogram: a rate is required, the exit weight is optional
 * (blank takes the latest weighing, which the server resolves). The amount shown
 * is a preview of the server's own sum, never what is sent.
 */
export function SalePricing({
  idPrefix,
  pricePerKg,
  setPricePerKg,
  exitWeight,
  setExitWeight,
  latestWeight,
}: {
  idPrefix: string;
  pricePerKg: string;
  setPricePerKg: (v: string) => void;
  exitWeight: string;
  setExitWeight: (v: string) => void;
  /** The latest weighing, used for the preview while the exit weight is blank. */
  latestWeight: number | null | undefined;
}) {
  const kg = exitWeight ? Number(exitWeight) : latestWeight ?? null;
  const amount = saleAmount(kg, pricePerKg ? Number(pricePerKg) : null);
  return (
    <>
      <div className="flex flex-col gap-1.5">
        <Label htmlFor={`${idPrefix}-price-kg`}>Price per kg</Label>
        <Input
          id={`${idPrefix}-price-kg`}
          type="number"
          min={0}
          value={pricePerKg}
          onChange={(e) => setPricePerKg(e.target.value)}
        />
      </div>
      <div className="flex flex-col gap-1.5">
        <Label htmlFor={`${idPrefix}-exit-kg`}>Exit weight (kg)</Label>
        <Input
          id={`${idPrefix}-exit-kg`}
          type="number"
          min={0}
          placeholder={latestWeight ? `Latest weighing: ${fmt(latestWeight)}` : "No weighing on record"}
          value={exitWeight}
          onChange={(e) => setExitWeight(e.target.value)}
        />
      </div>
      <p className="text-[12.5px] text-[var(--sd-muted)] sm:col-span-2" data-testid={`${idPrefix}-amount`}>
        {amount === null
          ? "Enter a price per kg and an exit weight to see the sale amount."
          : `Sale amount: ${fmt(kg ?? 0)} kg x ${fmt(Number(pricePerKg))} = ${fmt(amount)}`}
      </p>
    </>
  );
}
