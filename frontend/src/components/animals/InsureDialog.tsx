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
import { getCoverPolicies, insureAnimal, type CoverPolicy } from "@/lib/animals-api";
import { bootstrap, isError } from "@/lib/frappe";

/** Only Accounts insures an animal for now; the server refuses everyone else too. */
export const INSURE_ROLES = ["Accounts Manager", "Accounts User", "System Manager"];

export function canInsure(roles: string[] = bootstrap().roles): boolean {
  return roles.some((r) => INSURE_ROLES.includes(r) || r === "Administrator");
}

/**
 * Put her under a running Upande Asset policy. With the insurer's endorsement
 * number it is confirmed at once; without, it goes to the insurer as a request.
 */
export function InsureDialog({
  open,
  onOpenChange,
  animal,
  onInsured,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  animal: string;
  onInsured?: () => void;
}) {
  const [policies, setPolicies] = useState<CoverPolicy[] | null>(null);
  const [policy, setPolicy] = useState("");
  const [sum, setSum] = useState("");
  const [effective, setEffective] = useState("");
  const [endorsement, setEndorsement] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState<string | null>(null);

  useEffect(() => {
    if (!open) return;
    setError(null);
    setDone(null);
    void getCoverPolicies(animal).then((r) => {
      if (isError(r)) setError(r.error);
      else setPolicies(r.policies);
    });
  }, [open, animal]);

  async function submit() {
    setBusy(true);
    setError(null);
    const r = await insureAnimal({
      animal,
      policy,
      sum_insured: sum ? Number(sum) : undefined,
      effective_date: effective || undefined,
      endorsement_no: endorsement.trim() || undefined,
    });
    setBusy(false);
    if (isError(r)) {
      setError(r.error);
      return;
    }
    setDone(endorsement.trim() ? "She is under cover." : "Request sent to the insurer.");
    onInsured?.();
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle>Insure {animal}</DialogTitle>
          <DialogDescription>
            Add her to a running policy. Leave the endorsement number empty to send the insurer a request.
          </DialogDescription>
        </DialogHeader>
        {error && <Notice tone="error">{error}</Notice>}
        {done && <Notice tone="ok">{done}</Notice>}
        {policies && policies.length === 0 && !error && (
          <Notice tone="info">There is no running policy to add her to. Create one in Upande Asset first.</Notice>
        )}
        <div className="grid gap-3">
          <div className="grid gap-1">
            <Label htmlFor="insure-policy">Policy</Label>
            <select
              id="insure-policy"
              className="h-9 rounded-md border border-input bg-background px-3 text-sm"
              value={policy}
              onChange={(e) => setPolicy(e.target.value)}
            >
              <option value="">Choose a policy</option>
              {(policies ?? []).map((p) => (
                <option key={p.name} value={p.name}>
                  {p.policy_number || p.name} · {p.insurer_name || p.policy_type} · to {p.end_date}
                </option>
              ))}
            </select>
          </div>
          <div className="grid gap-1">
            <Label htmlFor="insure-sum">Sum insured (blank: her book value)</Label>
            <Input id="insure-sum" type="number" min="0" value={sum} onChange={(e) => setSum(e.target.value)} />
          </div>
          <div className="grid gap-1">
            <Label htmlFor="insure-date">Effective date (blank: today)</Label>
            <Input id="insure-date" type="date" value={effective} onChange={(e) => setEffective(e.target.value)} />
          </div>
          <div className="grid gap-1">
            <Label htmlFor="insure-endorsement">Endorsement no.</Label>
            <Input id="insure-endorsement" value={endorsement} onChange={(e) => setEndorsement(e.target.value)} />
          </div>
        </div>
        <div className="flex justify-end gap-2">
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            {done ? "Close" : "Cancel"}
          </Button>
          {!done && (
            <Button disabled={!policy || busy} onClick={() => void submit()}>
              {busy ? "Insuring…" : "Insure"}
            </Button>
          )}
        </div>
      </DialogContent>
    </Dialog>
  );
}
