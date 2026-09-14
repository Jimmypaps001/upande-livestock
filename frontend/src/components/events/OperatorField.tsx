import { useId } from "react";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { cn } from "@/lib/utils";

/**
 * The "who is doing this" box, shown only when the app cannot work it out.
 *
 * A user with an Employee linked never sees it. Everyone else sees it once per
 * device — see `useOperator` — because the server refuses an event that does
 * not say who made it, and discovering that by clicking a button that appears
 * to do nothing is how this was found.
 */
export function OperatorField({
  operator,
  onChange,
  className,
}: {
  operator: string;
  onChange: (next: string) => void;
  className?: string;
}) {
  // A page can carry two of these — the Herds page asks once for splitting a
  // herd and once for buying an animal in. A fixed id would put the same id on
  // both, which is invalid HTML and binds the label to whichever the browser
  // saw first, so clicking one label focuses the other field.
  const id = useId();
  return (
    <div className={cn("flex flex-col gap-1.5", className)}>
      <Label htmlFor={id}>Who is recording this</Label>
      <Input
        id={id}
        value={operator}
        onChange={(e) => onChange(e.target.value)}
        placeholder="HR-EMP-00042"
        className="w-[200px]"
      />
      <span className="text-[11px] text-[var(--sd-quiet)]">
        Your login has no Employee linked. Answered once, remembered on this device.
      </span>
    </div>
  );
}
