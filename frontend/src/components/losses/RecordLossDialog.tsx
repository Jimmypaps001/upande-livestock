import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Notice } from "@/components/feeding/Notice";
import { uploadFile, isError } from "@/lib/frappe";
import { getLossScenarios, recordLoss, SALE_OUTCOMES, type LossScenario } from "@/lib/losses";

/**
 * Record a loss: pick the scenario, see what it asks for, attach the papers.
 * The server raises the claim and takes the animal out as far as the rules
 * allow; a sale that must wait for the claim is told so here.
 */
export function RecordLossDialog({
  open,
  onOpenChange,
  animal,
  onRecorded,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  animal: string;
  onRecorded?: () => void;
}) {
  const [scenarios, setScenarios] = useState<LossScenario[] | null>(null);
  const [scenario, setScenario] = useState("");
  const [date, setDate] = useState(new Date().toISOString().slice(0, 10));
  const [notes, setNotes] = useState("");
  const [customer, setCustomer] = useState("");
  const [price, setPrice] = useState("");
  const [files, setFiles] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState<string[] | null>(null);

  useEffect(() => {
    if (!open) return;
    setError(null);
    setDone(null);
    void getLossScenarios().then((r) => {
      if (isError(r)) setError(r.error);
      else setScenarios(r.scenarios);
    });
  }, [open]);

  const chosen = scenarios?.find((s) => s.name === scenario) ?? null;
  const sells = chosen ? SALE_OUTCOMES.includes(chosen.outcome) : false;

  async function attach(doc: string, file: File | undefined) {
    if (!file) return;
    const r = await uploadFile(file);
    if (isError(r)) setError(r.error);
    else setFiles((f) => ({ ...f, [doc]: r.file_url }));
  }

  async function submit() {
    if (!chosen) return;
    setBusy(true);
    setError(null);
    const r = await recordLoss({
      animal,
      scenario: chosen.name,
      incident_date: date,
      notes: notes.trim() || undefined,
      documents: Object.entries(files).map(([document_name, attachment]) => ({ document_name, attachment })),
      customer: sells && customer.trim() ? customer.trim() : undefined,
      sale_price: sells && price ? Number(price) : undefined,
    });
    setBusy(false);
    if (isError(r)) {
      setError(r.error);
      return;
    }
    const lines = [`Loss ${r.name} recorded.`];
    if (r.claim) lines.push(`Claim ${r.claim} raised (${r.claim_status}).`);
    if (r.claim_note) lines.push(r.claim_note);
    if (r.missing_documents) lines.push(`Still to attach: ${r.missing_documents}.`);
    if (r.blocked) lines.push(r.blocked);
    if (r.disposal_note) lines.push(r.disposal_note);
    setDone(lines);
    onRecorded?.();
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle>Record a loss for {animal}</DialogTitle>
          <DialogDescription>
            Injured, sick, dead or stolen. The scenario decides the claim and what happens to the animal.
          </DialogDescription>
        </DialogHeader>
        {error && <Notice tone="error">{error}</Notice>}
        {done && (
          <Notice tone="ok">
            {done.map((l) => (
              <span key={l} className="block">
                {l}
              </span>
            ))}
          </Notice>
        )}
        {scenarios && scenarios.length === 0 && !error && (
          <Notice tone="info">No loss scenario is set up yet. A manager adds them under Loss scenarios.</Notice>
        )}
        {!done && (
          <div className="grid gap-3">
            <div className="grid gap-1">
              <Label htmlFor="loss-scenario">Scenario</Label>
              <select
                id="loss-scenario"
                className="h-9 rounded-md border border-input bg-background px-3 text-sm"
                value={scenario}
                onChange={(e) => setScenario(e.target.value)}
              >
                <option value="">Choose a scenario</option>
                {(scenarios ?? []).map((s) => (
                  <option key={s.name} value={s.name}>
                    {s.scenario_name}
                  </option>
                ))}
              </select>
            </div>
            {chosen && (
              <p className="text-[12px] text-[var(--sd-muted)]">
                {chosen.outcome}
                {chosen.claim_insurance ? `, insurance claim (${chosen.incident_type})` : ", no claim"}.
                {chosen.description ? ` ${chosen.description}` : ""}
              </p>
            )}
            <div className="grid gap-1">
              <Label htmlFor="loss-date">Incident date</Label>
              <Input id="loss-date" type="date" value={date} max={new Date().toISOString().slice(0, 10)} onChange={(e) => setDate(e.target.value)} />
            </div>
            <div className="grid gap-1">
              <Label htmlFor="loss-notes">What happened</Label>
              <Input id="loss-notes" value={notes} onChange={(e) => setNotes(e.target.value)} />
            </div>
            {chosen && chosen.claim_insurance === 1 && chosen.required_documents.length > 0 && (
              <fieldset className="grid gap-2 rounded-md border border-[var(--sd-line)] p-3">
                <legend className="px-1 text-[12px] font-medium">Checklist for the claim</legend>
                {chosen.required_documents.map((d) => (
                  <div key={d.document_name} className="grid gap-1">
                    <Label htmlFor={`doc-${d.document_name}`}>
                      {d.document_name}
                      {d.mandatory ? " (required)" : ""}
                      {files[d.document_name] ? " - attached" : ""}
                    </Label>
                    <input
                      id={`doc-${d.document_name}`}
                      type="file"
                      className="text-[12px]"
                      onChange={(e) => void attach(d.document_name, e.target.files?.[0])}
                    />
                  </div>
                ))}
                <p className="text-[11px] text-[var(--sd-muted)]">
                  Required papers can be attached later on the claim; it cannot be recorded without them.
                </p>
              </fieldset>
            )}
            {sells && (
              <div className="grid grid-cols-2 gap-3">
                <div className="grid gap-1">
                  <Label htmlFor="loss-customer">Buyer (Customer)</Label>
                  <Input id="loss-customer" value={customer} onChange={(e) => setCustomer(e.target.value)} />
                </div>
                <div className="grid gap-1">
                  <Label htmlFor="loss-price">Sale price</Label>
                  <Input id="loss-price" type="number" min="0" value={price} onChange={(e) => setPrice(e.target.value)} />
                </div>
                <p className="col-span-2 text-[11px] text-[var(--sd-muted)]">
                  Leave blank to complete the sale later. The sale waits for the insurance claim as set in Settings.
                </p>
              </div>
            )}
          </div>
        )}
        <div className="flex justify-end gap-2">
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            {done ? "Close" : "Cancel"}
          </Button>
          {!done && (
            <Button disabled={!chosen || busy} onClick={() => void submit()}>
              {busy ? "Recording…" : "Record loss"}
            </Button>
          )}
        </div>
      </DialogContent>
    </Dialog>
  );
}
