import { useCallback, useEffect, useMemo, useState } from "react";
import { Plus, Search } from "lucide-react";
import { Notice } from "@/components/feeding/Notice";
import { Page, PageHeading } from "@/components/PageShell";
import { RefreshButton } from "@/components/RefreshButton";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Picker } from "@/components/ui/picker";
import { AddVetDialog } from "@/components/vets/AddVetDialog";
import { VetCard } from "@/components/vets/VetCard";
import { isError } from "@/lib/frappe";
import { getVetsList, VET_PERIODS, type VetPeriod, type VetsList } from "@/lib/vets";
import { cn } from "@/lib/utils";

const TYPES = ["All", "Internal", "External"] as const;

/**
 * People ▸ Vets — each vet's work for a period, as a card of figures.
 *
 * Modelled on the Scouts screen of the scouting app: the people, their KPIs, a
 * period to measure over. The figures are only as good as the `vet` filled on
 * records (see the Vet Performance report, whose counting this shares); a
 * vet whose work was never entered under their name reads low.
 */
export function Vets() {
  const [period, setPeriod] = useState<VetPeriod>("90d");
  const [data, setData] = useState<VetsList | null>(null);
  const [loading, setLoading] = useState(true);
  const [failure, setFailure] = useState<string | null>(null);
  const [term, setTerm] = useState("");
  const [type, setType] = useState<(typeof TYPES)[number]>("All");
  const [adding, setAdding] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    const r = await getVetsList(period);
    setLoading(false);
    if (isError(r)) {
      setFailure(r.error);
      return;
    }
    setFailure(null);
    setData(r);
  }, [period]);

  useEffect(() => {
    void load();
  }, [load]);

  const shown = useMemo(() => {
    const q = term.trim().toLowerCase();
    return (data?.vets ?? []).filter(
      (v) =>
        (type === "All" || v.type === type) &&
        (!q || [v.vet_name, v.vet, v.practice_name, v.registration_number].some((f) => (f || "").toLowerCase().includes(q))),
    );
  }, [data, term, type]);

  return (
    <Page>
      <PageHeading
        eyebrow="Upande Livestock · People"
        title="Vets"
        actions={
          <>
            <div className="w-[170px]">
              <Picker
                id="vets-period"
                label="Period"
                value={period}
                onChange={(p) => setPeriod(p as VetPeriod)}
                options={VET_PERIODS.map((p) => ({ value: p.value, label: p.label }))}
              />
            </div>
            <RefreshButton onClick={load} loading={loading} label="the vets" />
            <Button onClick={() => setAdding(true)}>
              <Plus className="mr-1.5 h-4 w-4" />
              Add vet
            </Button>
          </>
        }
      >
        Who is treating the herd, and what they did{data ? ` between ${data.from} and ${data.to}` : ""}.
      </PageHeading>

      {failure && <Notice tone="error">{failure}</Notice>}

      <div className="flex flex-wrap items-center gap-3">
        <div className="relative min-w-[220px] max-w-sm flex-1">
          <Label htmlFor="vets-find" className="sr-only">
            Find a vet
          </Label>
          <Search className="pointer-events-none absolute left-3 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-[var(--sd-quiet)]" />
          <Input
            id="vets-find"
            value={term}
            onChange={(e) => setTerm(e.target.value)}
            placeholder="Name, practice, registration"
            className="pl-8"
          />
        </div>
        <div className="flex gap-1.5" role="group" aria-label="Vet type">
          {TYPES.map((t) => (
            <button
              key={t}
              type="button"
              aria-pressed={type === t}
              onClick={() => setType(t)}
              className={cn(
                "rounded-full px-3 py-1 text-[12.5px] font-medium ring-1 ring-[var(--sd-line)]",
                type === t ? "bg-[var(--sd-ink)] text-white" : "text-[var(--sd-muted)] hover:text-[var(--sd-ink)]",
              )}
            >
              {t}
            </button>
          ))}
        </div>
      </div>

      {!data && loading ? (
        <div className="grid min-w-0 gap-4 grid-cols-[repeat(auto-fill,minmax(min(100%,380px),1fr))]" aria-busy>
          {[0, 1, 2].map((i) => (
            <div key={i} className="h-[330px] animate-pulse rounded-[var(--sd-radius-card)] bg-[var(--sd-bg-soft)]" />
          ))}
        </div>
      ) : shown.length ? (
        <div className="grid min-w-0 gap-4 grid-cols-[repeat(auto-fill,minmax(min(100%,380px),1fr))]">
          {shown.map((v) => (
            <VetCard key={v.vet} vet={v} />
          ))}
        </div>
      ) : data ? (
        <p className="py-10 text-center text-[13px] text-[var(--sd-muted)]">
          {data.vets.length ? "No vet matches." : "No vets yet. Add the first one."}
        </p>
      ) : null}

      <AddVetDialog open={adding} onOpenChange={setAdding} onAdded={() => void load()} />
    </Page>
  );
}
