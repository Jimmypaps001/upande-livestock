import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Notice } from "@/components/feeding/Notice";
import { isError } from "@/lib/frappe";
import { saveSire, sireProblem, SIRE_TYPES, type SireInput, type SireRow } from "@/lib/sires";

const BLANK: SireInput = {
  sire_name: "", sire_code: "", sire_type: "Semen", semen_item: "", animal: "", sexed: false, active: true,
};
const SELECT = "h-9 rounded-md border border-input bg-background px-3 text-sm";

/** Add or edit one sire. The server's words are shown as sent. */
export function SireDialog({
  open,
  sire,
  onOpenChange,
  onSaved,
}: {
  open: boolean;
  /** null: a new sire. */
  sire: SireRow | null;
  onOpenChange: (open: boolean) => void;
  onSaved?: () => void;
}) {
  const [v, setV] = useState<SireInput>(BLANK);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!open) return;
    setError(null);
    setV(
      sire
        ? {
            name: sire.name, sire_name: sire.sire_name, sire_code: sire.code, sire_type: sire.sire_type,
            semen_item: sire.semen_item, animal: sire.animal, sexed: !!sire.sexed, active: !!sire.active,
          }
        : BLANK,
    );
  }, [open, sire]);

  const set = (patch: Partial<SireInput>) => setV((cur) => ({ ...cur, ...patch }));

  async function submit() {
    const problem = sireProblem(v);
    if (problem) return setError(problem);
    setBusy(true);
    setError(null);
    const r = await saveSire(v);
    setBusy(false);
    if (isError(r)) return setError(r.error);
    onSaved?.();
    onOpenChange(false);
  }

  const text = (id: string, label: string, key: "sire_name" | "sire_code" | "semen_item" | "animal") => (
    <div className="grid gap-1">
      <Label htmlFor={id}>{label}</Label>
      <Input id={id} value={v[key]} onChange={(e) => set({ [key]: e.target.value })} />
    </div>
  );
  const check = (id: string, label: string, key: "sexed" | "active") => (
    <label htmlFor={id} className="flex items-center gap-2 text-sm">
      <input id={id} type="checkbox" checked={v[key]} onChange={(e) => set({ [key]: e.target.checked })} />
      {label}
    </label>
  );

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[90vh] max-w-lg overflow-y-auto">
        <DialogHeader>
          <DialogTitle>{sire ? "Edit sire" : "Add sire"}</DialogTitle>
          <DialogDescription>
            A semen sire names the straw item issued for him; a live bull names his animal record.
          </DialogDescription>
        </DialogHeader>
        {error && <Notice tone="error">{error}</Notice>}
        <div className="grid gap-3">
          {text("sire-name", "Name", "sire_name")}
          {text("sire-code", "Code", "sire_code")}
          <div className="grid gap-1">
            <Label htmlFor="sire-type">Type</Label>
            <select
              id="sire-type"
              className={SELECT}
              value={v.sire_type}
              onChange={(e) => set({ sire_type: e.target.value as SireInput["sire_type"] })}
            >
              {SIRE_TYPES.map((t) => (
                <option key={t} value={t}>
                  {t}
                </option>
              ))}
            </select>
          </div>
          {v.sire_type === "Semen" ? text("sire-item", "Semen item", "semen_item") : text("sire-animal", "Live bull (animal)", "animal")}
          {check("sire-sexed", "Sexed semen", "sexed")}
          {check("sire-active", "Active (offered on the Service form)", "active")}
        </div>
        <div className="flex justify-end gap-2 pt-2">
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button onClick={() => void submit()} disabled={busy}>
            {busy ? "Saving…" : "Save"}
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}
