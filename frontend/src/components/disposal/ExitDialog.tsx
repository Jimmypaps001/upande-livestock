import { useEffect, useState } from "react";
import { EventDate } from "@/components/EventDate";
import { Notice } from "@/components/feeding/Notice";
import { SalePricing } from "@/components/culling/SalePricing";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Picker } from "@/components/ui/picker";
import { getCullEvidence } from "@/lib/culling";
import { EXIT_TYPES, getExitCustomers, recordExit, validateExit, type ExitType } from "@/lib/disposal";
import { isError } from "@/lib/frappe";
import { fmt } from "@/lib/utils";

/**
 * Sell or slaughter one animal: type, date, exit weight, and for a sale the
 * price per kg and the buyer. The amount is a preview of the server's own sum;
 * a withdrawal warning the server returns is shown after the exit is recorded,
 * because a warning does not stop the farm.
 */
export function ExitDialog({
  animal,
  label,
  latestWeight,
  open,
  onOpenChange,
  onDone,
}: {
  animal: string;
  label?: string;
  /** Known latest weighing; looked up when not given. */
  latestWeight?: number | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onDone: (message: string) => void;
}) {
  const [type, setType] = useState<ExitType>("Sold");
  const [date, setDate] = useState("");
  const [exitWeight, setExitWeight] = useState("");
  const [pricePerKg, setPricePerKg] = useState("");
  const [customer, setCustomer] = useState("");
  const [customers, setCustomers] = useState<string[]>([]);
  const [looked, setLooked] = useState<number | null>(null);
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<string | null>(null);
  const [warnings, setWarnings] = useState<string[]>([]);
  const [recorded, setRecorded] = useState<string | null>(null);

  useEffect(() => {
    if (!open) return;
    setType("Sold");
    setExitWeight("");
    setPricePerKg("");
    setCustomer("");
    setFailure(null);
    setWarnings([]);
    setRecorded(null);
    let live = true;
    void getExitCustomers().then((r) => {
      if (live && !isError(r)) setCustomers(r.customers || []);
    });
    if (latestWeight === undefined) {
      void getCullEvidence(animal).then((r) => {
        if (live) setLooked(isError(r) ? null : r.latest_weight_kg ?? null);
      });
    }
    return () => {
      live = false;
    };
  }, [open, animal, latestWeight]);

  const weight = latestWeight !== undefined ? latestWeight : looked;
  const name = label || animal;

  async function submit() {
    const input = { animal, type, date, exitWeight, pricePerKg, customer };
    const problem = validateExit(input);
    if (problem) {
      setFailure(problem);
      return;
    }
    setBusy(true);
    setFailure(null);
    const r = await recordExit(input);
    setBusy(false);
    if (isError(r)) {
      setFailure(r.error);
      return;
    }
    const message =
      type === "Sold"
        ? `${name} was sold for ${fmt(r.sale_price ?? 0)}.`
        : `${name} was recorded as slaughtered.`;
    if (r.warnings?.length) {
      setWarnings(r.warnings);
      setRecorded(message);
      return;
    }
    onOpenChange(false);
    onDone(message);
  }

  function close() {
    const message = recorded;
    onOpenChange(false);
    if (message) onDone(message);
  }

  return (
    <Dialog open={open} onOpenChange={(o) => (o ? onOpenChange(true) : close())}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle>Exit {name}</DialogTitle>
          <DialogDescription>
            Sold or slaughtered, in one step. She leaves the herd and the farm's books follow.
          </DialogDescription>
        </DialogHeader>

        {recorded ? (
          <div className="flex flex-col gap-3">
            <Notice tone="ok">{recorded}</Notice>
            {warnings.map((w) => (
              <Notice key={w} tone="error">{w}</Notice>
            ))}
            <div>
              <Button onClick={close}>Close</Button>
            </div>
          </div>
        ) : (
          <div className="flex flex-col gap-4">
            <div className="grid gap-4 sm:grid-cols-2">
              <div className="flex flex-col gap-1.5">
                <Label htmlFor="exit-type">Leaving as</Label>
                <Picker
                  id="exit-type"
                  value={type}
                  onChange={(v) => setType(v as ExitType)}
                  options={[...EXIT_TYPES]}
                  label="Leaving as"
                />
              </div>
              <div className="flex flex-col gap-1.5">
                <Label htmlFor="exit-date">Date</Label>
                <EventDate id="exit-date" value={date} onChange={setDate} />
              </div>

              {type === "Sold" ? (
                <>
                  <div className="flex flex-col gap-1.5 sm:col-span-2">
                    <Label htmlFor="exit-customer">Customer</Label>
                    <Picker
                      id="exit-customer"
                      value={customer}
                      onChange={setCustomer}
                      options={customers}
                      label="Customer"
                      placeholder="Choose the buyer…"
                    />
                  </div>
                  <SalePricing
                    idPrefix="exit"
                    pricePerKg={pricePerKg}
                    setPricePerKg={setPricePerKg}
                    exitWeight={exitWeight}
                    setExitWeight={setExitWeight}
                    latestWeight={weight}
                  />
                </>
              ) : (
                <div className="flex flex-col gap-1.5 sm:col-span-2">
                  <Label htmlFor="exit-exit-kg">Exit weight (kg)</Label>
                  <Input
                    id="exit-exit-kg"
                    type="number"
                    min={0}
                    placeholder={weight ? `Latest weighing: ${fmt(weight)}` : "No weighing on record"}
                    value={exitWeight}
                    onChange={(e) => setExitWeight(e.target.value)}
                  />
                </div>
              )}
            </div>

            {failure && <Notice tone="error">{failure}</Notice>}

            <div className="flex flex-wrap items-center gap-3">
              <Button onClick={submit} disabled={busy}>
                {busy ? "Recording…" : type === "Sold" ? "Record the sale" : "Record the slaughter"}
              </Button>
              <Button variant="outline" onClick={close} disabled={busy}>
                Cancel
              </Button>
            </div>
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}
