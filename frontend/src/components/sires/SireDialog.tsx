import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Notice } from "@/components/feeding/Notice";
import { SearchPicker } from "@/components/ui/search-picker";
import { can } from "@/lib/can";
import { getAnimals } from "@/lib/animals-api";
import type { AnimalSummary } from "@/lib/animals";
import { isError } from "@/lib/frappe";
import { createSireItem, getSireItems, saveSire, type StrawItem, sireProblem, SIRE_TYPES, type SireInput, type SireRow } from "@/lib/sires";

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
  initialName = "",
}: {
  open: boolean;
  /** null: a new sire. */
  sire: SireRow | null;
  onOpenChange: (open: boolean) => void;
  onSaved?: (name: string) => void;
  /** Prefills the name of a new sire (what was typed in the picker). */
  initialName?: string;
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
            breed: sire.breed ?? "", supplier: sire.supplier ?? "",
          }
        : { ...BLANK, sire_name: initialName },
    );
  }, [open, sire, initialName]);

  const [straws, setStraws] = useState<StrawItem[]>([]);
  const [suggested, setSuggested] = useState<StrawItem | null>(null);
  const [making, setMaking] = useState(false);
  const [bulls, setBulls] = useState<AnimalSummary[]>([]);
  useEffect(() => {
    if (!open || v.sire_type !== "Live bull" || bulls.length) return;
    void getAnimals().then((r) => {
      if (!isError(r)) setBulls((r.animals ?? []).filter((a) => a.sex === "Male"));
    });
  }, [open, v.sire_type, bulls.length]);
  const canMake = can.flag("manage_sires");

  // The straws on offer, and the one this name or code points at.
  useEffect(() => {
    if (!open || v.sire_type !== "Semen") return;
    let live = true;
    const t = setTimeout(async () => {
      const r = await getSireItems(v.sire_name, v.sire_code, v.semen_item);
      if (!live || isError(r)) return;
      setStraws(r.items ?? []);
      setSuggested(r.suggested ?? null);
    }, 250);
    return () => {
      live = false;
      clearTimeout(t);
    };
  }, [open, v.sire_type, v.sire_name, v.sire_code, v.semen_item]);

  async function makeItem() {
    setMaking(true);
    setError(null);
    const r = await createSireItem(v.sire_name, v.sire_code);
    setMaking(false);
    if (isError(r)) return setError(r.error);
    setStraws((cur) => (cur.some((i) => i.value === r.item) ? cur : [...cur, { value: r.item, item_name: r.item, label: r.item, uom: "", group: "" }]));
    set({ semen_item: r.item });
  }

  const set = (patch: Partial<SireInput>) => setV((cur) => ({ ...cur, ...patch }));

  async function submit() {
    const problem = sireProblem(v);
    if (problem) return setError(problem);
    setBusy(true);
    setError(null);
    const r = await saveSire(v);
    setBusy(false);
    if (isError(r)) return setError(r.error);
    onSaved?.(r.name);
    onOpenChange(false);
  }

  const text = (id: string, label: string, key: "sire_name" | "sire_code" | "animal" | "breed" | "supplier") => (
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
          {v.sire_type === "Semen" ? (
            <div className="grid gap-1">
              <Label htmlFor="sire-item">Semen straw item</Label>
              <SearchPicker
                id="sire-item"
                label="Semen straw item"
                value={v.semen_item}
                onChange={(next) => set({ semen_item: next })}
                options={straws.map((i) => ({ value: i.value, label: i.label, short: i.item_name }))}
                placeholder="Search the straws…"
              />
              {!v.semen_item && suggested && (
                <p className="flex flex-wrap items-center gap-2 text-[12px] text-[var(--sd-muted)]">
                  Suggested: {suggested.item_name}
                  <Button type="button" size="sm" variant="outline" onClick={() => set({ semen_item: suggested.value })}>
                    Use it
                  </Button>
                </p>
              )}
              {!v.semen_item && !suggested && v.sire_name.trim() && canMake && (
                <p className="flex flex-wrap items-center gap-2 text-[12px] text-[var(--sd-muted)]">
                  No straw item found for him.
                  <Button type="button" size="sm" variant="outline" disabled={making} onClick={() => void makeItem()}>
                    {making ? "Creating…" : "Create the item"}
                  </Button>
                </p>
              )}
              <p className="text-[12px] text-[var(--sd-quiet)]">
                Picking this sire on a service issues this straw automatically.
              </p>
            </div>
          ) : (
            <div className="grid gap-1">
              <Label htmlFor="sire-animal">Live bull (animal)</Label>
              <SearchPicker
                id="sire-animal"
                label="Live bull (animal)"
                value={v.animal}
                onChange={(next) => set({ animal: next })}
                options={bulls.map((a) => ({ value: a.id, label: `${a.name} · ${a.id}`, short: a.name }))}
                placeholder="Search the bulls…"
              />
            </div>
          )}
          {text("sire-breed", "Breed", "breed")}
          {text("sire-supplier", "Supplier", "supplier")}
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
