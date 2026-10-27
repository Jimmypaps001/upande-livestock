import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Picker } from "@/components/ui/picker";
import { HERD_CLASSES, showsBandFields, type HerdClass, type HerdDetails } from "@/lib/herds";

/**
 * What kind of herd this is, and — for a fattening or calf herd — the weight
 * band it holds and the gain it is expected to make.
 *
 * The band decides where an animal goes next: when she outgrows it, the farm is
 * told to move her up (see Weight Band Move Due). Breeding and other herds have
 * no band, so the boxes are not drawn rather than offered and ignored.
 */
export function HerdBandFields({
  idPrefix,
  value,
  onChange,
  disabled,
}: {
  idPrefix: string;
  value: HerdDetails;
  onChange: (next: HerdDetails) => void;
  disabled?: boolean;
}) {
  const set = (patch: Partial<HerdDetails>) => onChange({ ...value, ...patch });
  return (
    <div className="flex flex-col gap-4">
      <div className="grid gap-4 sm:grid-cols-2">
        <div className="flex flex-col gap-1.5">
          <Label htmlFor={`${idPrefix}-class`}>Herd class</Label>
          <Picker
            id={`${idPrefix}-class`}
            value={value.herd_class}
            onChange={(c) => set({ herd_class: c as HerdClass })}
            options={[...HERD_CLASSES]}
            label="Herd class"
            disabled={disabled}
          />
        </div>

        <div className="flex flex-col gap-1.5">
          <Label htmlFor={`${idPrefix}-monthly`}>Monthly weighing</Label>
          <label className="flex h-9 items-center gap-2 text-[13px] text-[var(--sd-ink)]">
            <input
              id={`${idPrefix}-monthly`}
              type="checkbox"
              checked={value.weigh_monthly}
              disabled={disabled}
              onChange={(e) => set({ weigh_monthly: e.target.checked })}
            />
            Weigh every animal each month
          </label>
        </div>
      </div>

      {showsBandFields(value.herd_class) && (
        <div className="grid gap-4 sm:grid-cols-3">
          <div className="flex flex-col gap-1.5">
            <Label htmlFor={`${idPrefix}-min`}>Band from (kg)</Label>
            <Input
              id={`${idPrefix}-min`}
              type="number"
              min={0}
              inputMode="decimal"
              value={value.min_weight_kg}
              disabled={disabled}
              onChange={(e) => set({ min_weight_kg: e.target.value })}
            />
          </div>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor={`${idPrefix}-max`}>Band up to (kg)</Label>
            <Input
              id={`${idPrefix}-max`}
              type="number"
              min={0}
              inputMode="decimal"
              value={value.max_weight_kg}
              disabled={disabled}
              onChange={(e) => set({ max_weight_kg: e.target.value })}
            />
            <span className="text-[11px] text-[var(--sd-quiet)]">Blank for the top band.</span>
          </div>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor={`${idPrefix}-adg`}>Target gain (kg/day)</Label>
            <Input
              id={`${idPrefix}-adg`}
              type="number"
              min={0}
              step="0.01"
              inputMode="decimal"
              value={value.target_adg_kg}
              disabled={disabled}
              onChange={(e) => set({ target_adg_kg: e.target.value })}
            />
          </div>
        </div>
      )}
    </div>
  );
}
