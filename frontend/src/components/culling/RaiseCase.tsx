import { useEffect, useMemo, useState } from "react";
import { ShieldCheck, Skull } from "lucide-react";
import { AnimalSearch } from "@/components/animals/AnimalSearch";
import { Notice } from "@/components/feeding/Notice";
import { DatePicker } from "@/components/DatePicker";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { isError } from "@/lib/frappe";
import {
  DEATH_CAUSES,
  FLOWS,
  getCullEvidence,
  raiseCull,
  recordMortality,
  type Evidence,
  type Flow,
} from "@/lib/culling";
import { cn, fmt, todayISO } from "@/lib/utils";
import type { AnimalSummary } from "@/lib/animals";

/**
 * Opening a case: who is leaving, why, and what the farm knows about her.
 *
 * THE EVIDENCE IS SHOWN BEFORE THE FLOW IS CHOSEN, not after. Which of the
 * four ways an animal leaves is the one decision on this page that money turns
 * on, and a person who picks it before seeing that she is the best cow in the
 * herd has picked it blind. It is also why a productive cow is not refused
 * here — she may be lame, or bad-tempered, or in the way; the record simply
 * says, in as many words, that she was performing.
 */
export function RaiseCase({
  animals,
  onRaised,
}: {
  animals: AnimalSummary[];
  onRaised: (message: string) => void;
}) {
  const [animal, setAnimal] = useState<string | null>(null);
  const [flow, setFlow] = useState<Flow>("Sale");
  const [reason, setReason] = useState("");
  const [cause, setCause] = useState<string>(DEATH_CAUSES[0]);
  const [when, setWhen] = useState(todayISO());
  const [buyer, setBuyer] = useState("");
  const [price, setPrice] = useState("");
  const [giftedTo, setGiftedTo] = useState("");
  const [evidence, setEvidence] = useState<Evidence | null>(null);
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<string | null>(null);

  useEffect(() => {
    let live = true;
    if (!animal) {
      setEvidence(null);
      return;
    }
    void getCullEvidence(animal).then((r) => {
      if (!live) return;
      setEvidence(isError(r) ? null : r);
    });
    return () => {
      live = false;
    };
  }, [animal]);

  const chosen = useMemo(() => FLOWS.find((f) => f.flow === flow)!, [flow]);

  async function submit() {
    if (!animal) return;
    setBusy(true);
    setFailure(null);
    // Two endpoints, two result shapes, one narrowing: `isError` cannot read a
    // union of envelopes, so each is checked where its own type is still known.
    const r: { error?: string; name?: string; claim?: { name: string; claimed_amount?: number } | null } =
      flow === "Mortality"
        ? await recordMortality({
            animal,
            death_cause: cause,
            remarks: reason || undefined,
            death_date: when,
          })
        : await raiseCull({
            animal,
            flow,
            reason: reason || undefined,
            disposal_date: when,
            buyer_name: flow === "Sale" ? buyer || undefined : undefined,
            sale_price: flow === "Sale" && price ? Number(price) : undefined,
            gifted_to: flow === "Gift" ? giftedTo || undefined : undefined,
          });
    setBusy(false);
    if (isError(r)) {
      setFailure(r.error);
      return;
    }
    const claim = (r as { claim?: { name: string; claimed_amount?: number } | null }).claim;
    onRaised(
      flow === "Mortality"
        ? claim
          ? `${animal} was recorded dead and moved out of her herd. Claim ${claim.name} is drafted against her policy for ${fmt(claim.claimed_amount ?? 0)}.`
          : `${animal} was recorded dead and moved out of her herd. No policy covered her, so there is nothing to claim.`
        : `Case ${(r as { name: string }).name} is open and with ${
            flow === "Gift" ? "the manager" : "the vet"
          }.`,
    );
    setAnimal(null);
    setReason("");
    setBuyer("");
    setPrice("");
    setGiftedTo("");
  }

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-col gap-1.5">
        <Label>Which animal</Label>
        <AnimalSearch animals={animals} selectedId={animal} onSelect={(a) => setAnimal(a.id)} />
      </div>

      {evidence && (
        <div className="rounded-[var(--sd-radius-lg)] bg-[var(--sd-bg-soft)] px-4 py-3.5 shadow-[var(--sd-shadow-inset)]">
          <p className="flex items-start gap-2 text-[13px] leading-relaxed text-[var(--sd-ink)]">
            {evidence.was_productive ? (
              <ShieldCheck className="mt-0.5 h-4 w-4 shrink-0 text-[var(--sd-sev-moderate)]" strokeWidth={1.75} />
            ) : (
              <Skull className="mt-0.5 h-4 w-4 shrink-0 text-[var(--sd-quiet)]" strokeWidth={1.75} />
            )}
            <span>{evidence.case}</span>
          </p>
          <p className="mt-2 text-[11.5px] text-[var(--sd-quiet)]">
            {evidence.is_capitalised
              ? `Book value ${fmt(evidence.book_value)} · asset ${evidence.asset}`
              : "Not capitalised — nothing will be written off."}
            {evidence.policy
              ? ` · insured with ${evidence.policy.insurer} at ${fmt(evidence.policy.payout_percent ?? 0)}%`
              : ""}
          </p>
        </div>
      )}

      <div className="flex flex-col gap-2">
        <Label>How is she leaving</Label>
        <div className="grid gap-2 sm:grid-cols-2">
          {FLOWS.map((f) => (
            <button
              key={f.flow}
              type="button"
              onClick={() => setFlow(f.flow)}
              className={cn(
                "rounded-[var(--sd-radius-lg)] px-3.5 py-3 text-left transition-all",
                f.flow === flow
                  ? "bg-[var(--sd-bg-soft)] shadow-[var(--sd-shadow-1)]"
                  : "hover:bg-[var(--sd-bg-soft)]",
              )}
            >
              <span className="block text-[13px] font-medium text-[var(--sd-ink)]">{f.label}</span>
              <span className="mt-0.5 block text-[11.5px] leading-snug text-[var(--sd-muted)]">
                {f.blurb}
              </span>
            </button>
          ))}
        </div>
      </div>

      <div className="grid gap-4 sm:grid-cols-2">
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="cull-when">{flow === "Mortality" ? "Date of death" : "Date"}</Label>
          <DatePicker id="cull-when" value={when} max={todayISO()} onChange={setWhen} />
        </div>

        {flow === "Mortality" && (
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="cull-cause">Cause of death</Label>
            <select
              id="cull-cause"
              value={cause}
              onChange={(e) => setCause(e.target.value)}
              className="h-9 w-full rounded-md border border-input bg-background px-3 text-sm"
            >
              {DEATH_CAUSES.map((c) => (
                <option key={c} value={c}>
                  {c}
                </option>
              ))}
            </select>
          </div>
        )}

        {flow === "Sale" && (
          <>
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="cull-buyer">Buyer</Label>
              <Input id="cull-buyer" value={buyer} onChange={(e) => setBuyer(e.target.value)} />
            </div>
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="cull-price">Asking price</Label>
              <Input
                id="cull-price"
                type="number"
                min={0}
                value={price}
                onChange={(e) => setPrice(e.target.value)}
              />
            </div>
          </>
        )}

        {flow === "Gift" && (
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="cull-gift">Given to</Label>
            <Input id="cull-gift" value={giftedTo} onChange={(e) => setGiftedTo(e.target.value)} />
          </div>
        )}
      </div>

      <div className="flex flex-col gap-1.5">
        <Label htmlFor="cull-reason">
          {flow === "Mortality" ? "What happened" : "Why she should go"}
        </Label>
        <Textarea
          id="cull-reason"
          value={reason}
          onChange={(e) => setReason(e.target.value)}
          placeholder={
            flow === "Mortality"
              ? "Found down after the morning milking; treated for milk fever on Tuesday."
              : "Third case of mastitis this lactation, and she has not held to two services."
          }
        />
      </div>

      {failure && <Notice tone="error">{failure}</Notice>}

      <div className="flex items-center gap-3">
        <Button onClick={submit} disabled={!animal || busy}>
          {busy
            ? "Working…"
            : flow === "Mortality"
              ? "Record the death"
              : `Open the case (${chosen.label.toLowerCase()})`}
        </Button>
        {flow === "Mortality" && (
          <span className="text-[11.5px] text-[var(--sd-muted)]">
            Posts at once — nobody approves a death.
          </span>
        )}
      </div>
    </div>
  );
}
