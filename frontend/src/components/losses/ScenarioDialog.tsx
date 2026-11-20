import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Notice } from "@/components/feeding/Notice";
import { isError } from "@/lib/frappe";
import { OUTCOMES, saveLossScenario, TREATMENTS, TRIGGERS, type LossDocument, type LossScenario } from "@/lib/losses";

const BLANK: Partial<LossScenario> = {
  scenario_name: "",
  active: 1,
  trigger: "Injury",
  outcome: "Write off",
  claim_insurance: 0,
  incident_type: "",
  loss_treatment: "",
  notify_roles: "",
  description: "",
  required_documents: [],
};

const SELECT = "h-9 rounded-md border border-input bg-background px-3 text-sm";

/** Add or edit one loss scenario: what it claims, what it needs, where the animal goes. */
export function ScenarioDialog({
  open,
  onOpenChange,
  scenario,
  incidentTypes,
  onSaved,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  scenario: LossScenario | null;
  incidentTypes: string[];
  onSaved: () => void;
}) {
  const [s, setS] = useState<Partial<LossScenario>>(BLANK);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (open) {
      setS(scenario ? { ...scenario } : { ...BLANK });
      setError(null);
    }
  }, [open, scenario]);

  const docs: LossDocument[] = s.required_documents ?? [];
  const set = (patch: Partial<LossScenario>) => setS((cur) => ({ ...cur, ...patch }));
  const setDoc = (i: number, patch: Partial<LossDocument>) =>
    set({ required_documents: docs.map((d, j) => (j === i ? { ...d, ...patch } : d)) });

  async function save() {
    setBusy(true);
    setError(null);
    const r = await saveLossScenario(s);
    setBusy(false);
    if (isError(r)) {
      setError(r.error);
      return;
    }
    onSaved();
    onOpenChange(false);
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[90vh] max-w-lg overflow-y-auto">
        <DialogHeader>
          <DialogTitle>{scenario ? `Edit ${scenario.scenario_name}` : "New loss scenario"}</DialogTitle>
          <DialogDescription>What a kind of loss means: the claim, the papers, and where the animal goes.</DialogDescription>
        </DialogHeader>
        {error && <Notice tone="error">{error}</Notice>}
        <div className="grid gap-3">
          <div className="grid gap-1">
            <Label htmlFor="sc-name">Name</Label>
            <Input id="sc-name" value={s.scenario_name ?? ""} disabled={!!scenario} onChange={(e) => set({ scenario_name: e.target.value })} />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div className="grid gap-1">
              <Label htmlFor="sc-trigger">Trigger</Label>
              <select id="sc-trigger" className={SELECT} value={s.trigger} onChange={(e) => set({ trigger: e.target.value })}>
                {TRIGGERS.map((t) => (
                  <option key={t}>{t}</option>
                ))}
              </select>
            </div>
            <div className="grid gap-1">
              <Label htmlFor="sc-outcome">Outcome</Label>
              <select id="sc-outcome" className={SELECT} value={s.outcome} onChange={(e) => set({ outcome: e.target.value })}>
                {OUTCOMES.map((t) => (
                  <option key={t}>{t}</option>
                ))}
              </select>
            </div>
          </div>
          <label className="flex items-center gap-2 text-sm">
            <input type="checkbox" checked={!!s.claim_insurance} onChange={(e) => set({ claim_insurance: e.target.checked ? 1 : 0 })} />
            Claim insurance
          </label>
          {!!s.claim_insurance && (
            <div className="grid grid-cols-2 gap-3">
              <div className="grid gap-1">
                <Label htmlFor="sc-incident">Incident type</Label>
                <select id="sc-incident" className={SELECT} value={s.incident_type ?? ""} onChange={(e) => set({ incident_type: e.target.value })}>
                  <option value="">Choose</option>
                  {incidentTypes.map((t) => (
                    <option key={t}>{t}</option>
                  ))}
                </select>
              </div>
              <div className="grid gap-1">
                <Label htmlFor="sc-treatment">Loss treatment</Label>
                <select id="sc-treatment" className={SELECT} value={s.loss_treatment ?? ""} onChange={(e) => set({ loss_treatment: e.target.value })}>
                  <option value="">Choose</option>
                  {TREATMENTS.map((t) => (
                    <option key={t}>{t}</option>
                  ))}
                </select>
              </div>
            </div>
          )}
          <fieldset className="grid gap-2 rounded-md border border-[var(--sd-line)] p-3">
            <legend className="px-1 text-[12px] font-medium">Required documents</legend>
            {docs.map((d, i) => (
              <div key={i} className="flex items-center gap-2">
                <Input aria-label={`Document ${i + 1}`} value={d.document_name} onChange={(e) => setDoc(i, { document_name: e.target.value })} />
                <label className="flex shrink-0 items-center gap-1 text-[12px]">
                  <input type="checkbox" checked={!!d.mandatory} onChange={(e) => setDoc(i, { mandatory: e.target.checked ? 1 : 0 })} />
                  Required
                </label>
                <Button type="button" variant="outline" size="sm" onClick={() => set({ required_documents: docs.filter((_, j) => j !== i) })}>
                  Remove
                </Button>
              </div>
            ))}
            <Button type="button" variant="outline" size="sm" className="justify-self-start" onClick={() => set({ required_documents: [...docs, { document_name: "", mandatory: 1 }] })}>
              Add a document
            </Button>
          </fieldset>
          <div className="grid gap-1">
            <Label htmlFor="sc-roles">Notify roles (comma separated; blank uses the Accounts alert roles)</Label>
            <Input id="sc-roles" value={s.notify_roles ?? ""} onChange={(e) => set({ notify_roles: e.target.value })} />
          </div>
          <label className="flex items-center gap-2 text-sm">
            <input type="checkbox" checked={!!s.active} onChange={(e) => set({ active: e.target.checked ? 1 : 0 })} />
            Active
          </label>
        </div>
        <div className="flex justify-end gap-2">
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button disabled={busy || !(s.scenario_name ?? "").trim()} onClick={() => void save()}>
            {busy ? "Saving…" : "Save"}
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}
