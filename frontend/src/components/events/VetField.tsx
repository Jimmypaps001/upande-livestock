import { Label } from "@/components/ui/label";
import { Picker } from "@/components/ui/picker";
import type { VetChoice } from "@/lib/vets";
import { cn } from "@/lib/utils";

/**
 * Which vet did this, chosen from the farm's vets.
 *
 * A vet is a record (Settings → Livestock Vet), not a name typed into a box:
 * a typed name cannot be counted, so nobody could say whose cases recover. Only
 * enabled vets are offered. Optional — a herder's own look at a cow has no vet —
 * and starts on the signed-in user's own vet record when they have one.
 */
export function VetField({
  vets,
  value,
  onChange,
  label = "Vet",
  className,
}: {
  vets: VetChoice[];
  value: string;
  onChange: (next: string) => void;
  label?: string;
  className?: string;
}) {
  const id = `vet-${label.replace(/\W+/g, "-").toLowerCase()}`;
  return (
    <div className={cn("flex flex-col gap-1.5", className)}>
      <Label htmlFor={id}>{label}</Label>
      <Picker
        id={id}
        value={value}
        onChange={onChange}
        options={vets.map((v) => ({ value: v.value, label: v.detail ? `${v.label} · ${v.detail}` : v.label }))}
        label={label}
        clearable
        placeholder={vets.length ? "None" : "No vets set up"}
        disabled={!vets.length}
        className="w-[240px]"
      />
    </div>
  );
}
