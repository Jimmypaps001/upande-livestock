import { useEffect, useState } from "react";
import { EventDate } from "@/components/EventDate";
import { Notice } from "@/components/feeding/Notice";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Picker } from "@/components/ui/picker";
import { isError } from "@/lib/frappe";
import {
  CLASS_KEYS,
  recordCountEvent,
  recordTreatment,
  recordWeightSample,
  type ClassKey,
  type Options,
  type ShoatHerd,
} from "@/lib/shoats";

export type RecordKind = "event" | "weight" | "treatment";

const TITLES: Record<RecordKind, string> = {
  event: "Record head count or movement",
  weight: "Weigh a sample",
  treatment: "Record a treatment",
};

/**
 * One dialog for the three things a herdsman records against a shoat herd by
 * number: a count or movement, a weight sample, a treatment. Everything it
 * sends the server checks again; the box only keeps the obvious mistakes
 * (nothing entered, a death with no cause) from making the trip. A warning the
 * server returns is shown after the record is saved, because a warning does not
 * stop the farm.
 */
export function ShoatRecordDialog({
  kind,
  herd,
  options,
  otherHerds,
  open,
  onOpenChange,
  onDone,
}: {
  kind: RecordKind;
  herd: ShoatHerd;
  options: Options | null;
  otherHerds: { name: string; label: string }[];
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onDone: (message: string) => void;
}) {
  const [date, setDate] = useState("");
  const [type, setType] = useState("Head Count");
  const [counts, setCounts] = useState<Record<ClassKey, string>>({ females: "", males: "", young: "", others: "" });
  const [bornDead, setBornDead] = useState("");
  const [cause, setCause] = useState("");
  const [other, setOther] = useState("");
  const [amount, setAmount] = useState("");
  const [matingStart, setMatingStart] = useState("");
  const [sampleClass, setSampleClass] = useState("All");
  const [weighed, setWeighed] = useState("");
  const [average, setAverage] = useState("");
  const [product, setProduct] = useState("");
  const [treatType, setTreatType] = useState("Deworming");
  const [dose, setDose] = useState("");
  const [treated, setTreated] = useState("");
  const [withdrawal, setWithdrawal] = useState("");
  const [diagnosis, setDiagnosis] = useState("");
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<string | null>(null);
  const [recorded, setRecorded] = useState<{ message: string; warnings: string[] } | null>(null);

  useEffect(() => {
    if (!open) return;
    setType(kind === "event" ? "Head Count" : type);
    setCounts({ females: "", males: "", young: "", others: "" });
    setBornDead("");
    setCause("");
    setOther("");
    setAmount("");
    setMatingStart("");
    setWeighed("");
    setAverage("");
    setDose("");
    setTreated("");
    setWithdrawal("");
    setDiagnosis("");
    setFailure(null);
    setRecorded(null);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, kind, herd.name]);

  const n = (v: string) => (v.trim() === "" ? 0 : Math.trunc(Number(v)));
  const countsPayload = () => Object.fromEntries(CLASS_KEYS.map((k) => [k, n(counts[k])]));

  function problem(): string | null {
    if (kind === "event") {
      const total = CLASS_KEYS.reduce((s, k) => s + n(counts[k]), 0);
      if (type !== "Head Count" && type !== "Mating" && total <= 0 && type !== "Birth") return "Enter how many animals.";
      if (type === "Birth" && n(counts.young) + n(bornDead) <= 0) return "Enter the lambs or kids born.";
      if (type === "Death" && !cause) return "Say what the animals died of.";
      if ((type === "Transfer In" || type === "Transfer Out") && !other) return "Choose the other herd.";
      if (type === "Mating" && (n(counts.females) <= 0 || n(counts.males) <= 0)) return "Enter the ewes or does put to the male, and the males in.";
    } else if (kind === "weight") {
      if (n(weighed) <= 0) return "Say how many animals were weighed.";
      if (!(Number(average) > 0)) return "Enter the average weight in kg.";
    } else {
      if (!product) return "Choose the product.";
      if (!(Number(dose) > 0)) return "Enter the dose per head.";
      if (n(treated) <= 0) return "Say how many animals were treated.";
    }
    return null;
  }

  async function submit() {
    const bad = problem();
    if (bad) {
      setFailure(bad);
      return;
    }
    setBusy(true);
    setFailure(null);
    let r;
    let message: string;
    if (kind === "event") {
      r = await recordCountEvent({
        herd: herd.name, event_type: type, event_date: date || undefined, ...countsPayload(),
        born_dead: n(bornDead), cause: cause || undefined, other_herd: other || undefined,
        amount: amount ? Number(amount) : undefined, mating_start: matingStart || undefined,
      });
      message = `${type} recorded for ${herd.label}.`;
    } else if (kind === "weight") {
      r = await recordWeightSample({
        herd: herd.name, sample_date: date || undefined, sample_class: sampleClass,
        animals_weighed: n(weighed), average_kg: Number(average),
      });
      message = `Weight sample recorded for ${herd.label}.`;
    } else {
      r = await recordTreatment({
        herd: herd.name, treatment_date: date || undefined, treatment_type: treatType, product,
        dose_per_head: Number(dose), number_treated: n(treated), withdrawal_days: n(withdrawal),
        diagnosis: diagnosis || undefined,
      });
      message = `${treatType} recorded for ${herd.label}.`;
    }
    setBusy(false);
    if (isError(r)) {
      setFailure(r.error);
      return;
    }
    const warnings = r.warnings || [];
    if (warnings.length) {
      setRecorded({ message, warnings });
      return;
    }
    onOpenChange(false);
    onDone(message);
  }

  function close() {
    const message = recorded?.message;
    onOpenChange(false);
    if (message) onDone(message);
  }

  const labels = herd.labels;
  const showCounts = kind === "event" && type !== "Birth";
  const types = (options?.event_types || []).map((e) => e.name);

  return (
    <Dialog open={open} onOpenChange={(o) => (o ? onOpenChange(true) : close())}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle>{TITLES[kind]}</DialogTitle>
          <DialogDescription>
            {herd.label} · {herd.head.total} head now
          </DialogDescription>
        </DialogHeader>
        {recorded ? (
          <div className="flex flex-col gap-3">
            <Notice tone="ok">{recorded.message}</Notice>
            {recorded.warnings.map((w) => (
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
                <Label htmlFor="shoat-date">Date</Label>
                <EventDate id="shoat-date" value={date} onChange={setDate} />
              </div>
              {kind === "event" && (
                <div className="flex flex-col gap-1.5">
                  <Label htmlFor="shoat-type">Event</Label>
                  <Picker id="shoat-type" label="Event" value={type} onChange={setType} options={types} />
                </div>
              )}
              {kind === "weight" && (
                <div className="flex flex-col gap-1.5">
                  <Label htmlFor="shoat-class">Class weighed</Label>
                  <Picker
                    id="shoat-class" label="Class weighed" value={sampleClass} onChange={setSampleClass}
                    options={[{ value: "All", label: "Whole herd" },
                      ...CLASS_KEYS.map((k) => ({ value: k, label: labels[k] }))]}
                  />
                </div>
              )}
              {kind === "treatment" && (
                <div className="flex flex-col gap-1.5">
                  <Label htmlFor="shoat-treat-type">Type</Label>
                  <Picker id="shoat-treat-type" label="Type" value={treatType} onChange={setTreatType}
                    options={options?.treatment_types || ["Treatment", "Dipping", "Deworming", "Vaccination"]} />
                </div>
              )}
            </div>

            {kind === "event" && type === "Birth" && (
              <div className="grid gap-4 sm:grid-cols-2">
                <Field id="shoat-young" label={`${labels.young} born alive`} value={counts.young}
                  onChange={(v) => setCounts({ ...counts, young: v })} />
                <Field id="shoat-dead" label="Born dead" value={bornDead} onChange={setBornDead} />
              </div>
            )}
            {showCounts && (
              <div className="grid gap-4 sm:grid-cols-4">
                {CLASS_KEYS.map((k) => (
                  <Field key={k} id={`shoat-${k}`} label={labels[k]} value={counts[k]}
                    onChange={(v) => setCounts({ ...counts, [k]: v })} />
                ))}
              </div>
            )}
            {kind === "event" && type === "Death" && (
              <div className="flex flex-col gap-1.5">
                <Label htmlFor="shoat-cause">Cause</Label>
                <Picker id="shoat-cause" label="Cause" value={cause} onChange={setCause}
                  options={options?.death_causes || []} />
              </div>
            )}
            {kind === "event" && (type === "Transfer In" || type === "Transfer Out" || type === "Weaning") && (
              <div className="flex flex-col gap-1.5">
                <Label htmlFor="shoat-other">{type === "Transfer In" ? "From herd" : "To herd"}</Label>
                <Picker id="shoat-other" label="Other herd" value={other} onChange={setOther} clearable={type === "Weaning"}
                  options={otherHerds.map((h) => ({ value: h.name, label: h.label }))} />
              </div>
            )}
            {kind === "event" && ["Purchase", "Sale", "Slaughter"].includes(type) && (
              <Field id="shoat-amount" label="Amount" value={amount} onChange={setAmount} />
            )}
            {kind === "event" && type === "Mating" && (
              <div className="flex flex-col gap-1.5">
                <Label htmlFor="shoat-mstart">Mating started</Label>
                <EventDate id="shoat-mstart" value={matingStart} onChange={setMatingStart} />
              </div>
            )}

            {kind === "weight" && (
              <div className="grid gap-4 sm:grid-cols-2">
                <Field id="shoat-weighed" label="Animals weighed" value={weighed} onChange={setWeighed} />
                <Field id="shoat-average" label="Average weight (kg)" value={average} onChange={setAverage} />
              </div>
            )}

            {kind === "treatment" && (
              <>
                <div className="flex flex-col gap-1.5">
                  <Label htmlFor="shoat-product">Product</Label>
                  <Picker id="shoat-product" label="Product" value={product} onChange={setProduct}
                    options={(options?.drugs || []).map((d) => ({
                      value: d.item_code, label: `${d.item_name} (${d.qty} ${d.uom})`,
                    }))} />
                </div>
                <div className="grid gap-4 sm:grid-cols-3">
                  <Field id="shoat-dose" label="Dose per head" value={dose} onChange={setDose} />
                  <Field id="shoat-treated" label="Number treated" value={treated} onChange={setTreated} />
                  <Field id="shoat-withdrawal" label="Withdrawal (days)" value={withdrawal} onChange={setWithdrawal} />
                </div>
                <div className="flex flex-col gap-1.5">
                  <Label htmlFor="shoat-diagnosis">Reason</Label>
                  <Input id="shoat-diagnosis" value={diagnosis} onChange={(e) => setDiagnosis(e.target.value)} />
                </div>
              </>
            )}

            {failure && <Notice tone="error">{failure}</Notice>}
            <div className="flex gap-2">
              <Button onClick={() => void submit()} disabled={busy}>
                {busy ? "Saving…" : "Save"}
              </Button>
              <Button variant="outline" onClick={() => onOpenChange(false)} disabled={busy}>
                Cancel
              </Button>
            </div>
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}

function Field({ id, label, value, onChange }: { id: string; label: string; value: string; onChange: (v: string) => void }) {
  return (
    <div className="flex flex-col gap-1.5">
      <Label htmlFor={id}>{label}</Label>
      <Input id={id} inputMode="decimal" value={value} onChange={(e) => onChange(e.target.value)} />
    </div>
  );
}
