import { useCallback, useEffect, useMemo, useState } from "react";
import { AlertTriangle, ArrowRight, Clock, Search } from "lucide-react";
import { DatePicker } from "@/components/DatePicker";
import { Figure, FigureRow } from "@/components/Figure";
import { Notice } from "@/components/feeding/Notice";
import { RowsSkeleton } from "@/components/Loading";
import { Page, PageHeading } from "@/components/PageShell";
import { RefreshButton } from "@/components/RefreshButton";
import { Button } from "@/components/ui/button";
import {
  Card, CardContent, CardDescription, CardHeaderRow, CardHeading, CardTitle, CardTools,
} from "@/components/ui/card";
import { CheckCircle } from "@/components/ui/check-circle";
import { OperatorField } from "@/components/events/OperatorField";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Picker } from "@/components/ui/picker";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Textarea } from "@/components/ui/textarea";
import { useToast } from "@/components/Toast";
import { isError } from "@/lib/frappe";
import {
  getMovementOptions, getMovementSuggestions, moveAnimals,
  type AnimalChoice, type MoveSuggestion, type MovementOptions, type MovementSuggestions,
} from "@/lib/events";
import { useOperator } from "@/lib/operator";
import { cn, todayISO } from "@/lib/utils";

/**
 * Who is due out of the herd they are in, and moving them.
 *
 * TWO KINDS OF RULE, ONE LIST. A weaner leaves her pen because she has been in
 * it long enough; a high yielder leaves because she is four months in calf and
 * her yield is falling away. A herdsman with a gate open does not care which
 * rule produced the row — only that she is due — so both arrive here together
 * and each says why in the farm's own words.
 *
 * MOVING IS A BATCH, BECAUSE THE JOB IS. Nobody walks one cow across the yard
 * and comes back for the next. The selection is the point of the screen, so it
 * is grouped by where they are going and everything due to one herd can be
 * taken in a single tick — then unpicked, because the person at the gate can
 * see a cow this list cannot.
 */
export function Movement() {
  const [due, setDue] = useState<MovementSuggestions | null>(null);
  const [options, setOptions] = useState<MovementOptions | null>(null);
  const [loading, setLoading] = useState(true);
  const [failure, setFailure] = useState<string | null>(null);
  const [picked, setPicked] = useState<Set<string>>(new Set());
  const [when, setWhen] = useState(todayISO());
  const [remarks, setRemarks] = useState("");
  const [busy, setBusy] = useState<string | null>(null);
  const toast = useToast();
  const who = useOperator(options?.employee);

  const load = useCallback(async () => {
    setLoading(true);
    const [s, o] = await Promise.all([getMovementSuggestions(), getMovementOptions()]);
    setLoading(false);
    if (isError(s)) {
      setFailure(s.error);
      return;
    }
    setFailure(null);
    setDue(s);
    if (!isError(o)) setOptions(o);
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const rows = due?.growth ?? [];

  // Grouped by destination: a move is "these cows, to that herd", and a list
  // sorted any other way makes the operator do the grouping in their head.
  const groups = useMemo(() => {
    const by = new Map<string, MoveSuggestion[]>();
    for (const r of rows) {
      if (!r.to_herd) continue;
      by.set(r.to_herd, [...(by.get(r.to_herd) ?? []), r]);
    }
    return [...by.entries()]
      .map(([herd, animals]) => ({
        herd,
        animals: [...animals].sort((a, b) => b.days_over - a.days_over),
      }))
      .sort((a, b) => b.animals.length - a.animals.length);
  }, [rows]);

  const overdue = rows.filter((r) => r.overdue).length;

  function toggle(animal: string) {
    setPicked((s) => {
      const next = new Set(s);
      if (next.has(animal)) next.delete(animal);
      else next.add(animal);
      return next;
    });
  }

  const needsOperator = who.needed;

  async function moveThese(herd: string, chosen: string[], key: string) {
    if (!chosen.length) return;
    if (needsOperator) {
      toast(
        "A movement has to say who made it, and your login has no Employee linked. " +
          "Put one in the box above, or link an Employee to your user.",
      );
      return;
    }
    setBusy(key);
    const r = await moveAnimals({
      animals: chosen,
      new_herd: herd,
      event_date: when,
      remarks: remarks.trim() || undefined,
      operator: who.value,
    });
    setBusy(null);
    if (isError(r)) {
      toast(r.error, "error");
      return;
    }
    toast(
      `${r.count} animal${r.count === 1 ? "" : "s"} moved into ${r.herd}, which now holds ${r.heads}.`,
    );
    setPicked((s) => {
      const next = new Set(s);
      chosen.forEach((a) => next.delete(a));
      return next;
    });
    setRemarks("");
    void load();
  }

  const move = (herd: string, animals: MoveSuggestion[]) =>
    moveThese(herd, animals.filter((a) => picked.has(a.animal)).map((a) => a.animal), herd);

  return (
    <Page>
      <PageHeading eyebrow="Upande Livestock · Herd" title="Movement">
        Who is due out of the herd they are in. A calf moves when she has been
        in her pen long enough; a milking cow moves when she is far enough in
        calf — both are here, and each says which.
      </PageHeading>

      {/* Failures of the page itself sit at the top; what a BUTTON said sits
          beside the buttons, below — an answer to a click at the bottom of a
          long page must not appear only above the fold. */}
      {failure && <Notice tone="error">{failure}</Notice>}


      <FigureRow>
        <Figure loading={!due} label="Due to move" value={String(rows.length)}
                hint="across every herd" />
        <Figure loading={!due} label="Late" value={String(overdue)}
                hint="past the farm's own limit" />
        <Figure loading={!due} label="Picked" value={String(picked.size)} hint="ready to move" />
        <Figure loading={!due} label="Destinations" value={String(groups.length)}
                hint="herds they are going to" />
      </FigureRow>

      <div className="flex flex-wrap items-end gap-4">
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="mv-when">Moved on</Label>
          <DatePicker id="mv-when" value={when} max={todayISO()} onChange={setWhen} />
        </div>
        <div className="flex min-w-[240px] flex-1 flex-col gap-1.5">
          <Label htmlFor="mv-why">Why (optional)</Label>
          <Textarea
            id="mv-why"
            value={remarks}
            onChange={(e) => setRemarks(e.target.value)}
            className="min-h-[38px]"
            placeholder="Coming into milk."
          />
        </div>
        {who.mustAsk && (
          <OperatorField operator={who.operator} onChange={who.setOperator} />
        )}
        <RefreshButton onClick={load} loading={loading} label="who is due" />
      </div>

      
      <Tabs defaultValue="due">
        <TabsList>
          <TabsTrigger value="due">Due to move</TabsTrigger>
          <TabsTrigger value="any">Move anyone</TabsTrigger>
        </TabsList>

        <TabsContent value="due" className="flex flex-col gap-5 pt-5">
      {!due ? (
        <Card>
          <CardContent className="pt-6">
            <RowsSkeleton rows={6} />
          </CardContent>
        </Card>
      ) : !groups.length ? (
        <Card>
          <CardContent className="pt-6">
            <p className="text-[13px] text-[var(--sd-muted)]">
              Nobody is due to move. Every animal is in the herd the farm's own rules
              put her in.
            </p>
          </CardContent>
        </Card>
      ) : (
        groups.map((g) => (
          <DestinationCard
            key={g.herd}
            herd={g.herd}
            animals={g.animals}
            picked={picked}
            busy={busy === g.herd}
            onToggle={toggle}
            onPickAll={(on) =>
              setPicked((s) => {
                const next = new Set(s);
                g.animals.forEach((a) => (on ? next.add(a.animal) : next.delete(a.animal)));
                return next;
              })
            }
            onMove={() => move(g.herd, g.animals)}
          />
        ))
      )}
        </TabsContent>

        {/* The farm moves animals for reasons no rule knows about — a lame cow
            off the concrete, a group split for space, a bull out of the way of
            a visitor. The due list cannot see any of that, so the whole herd is
            selectable too. */}
        <TabsContent value="any" className="pt-5">
          <MoveAnyone
            animals={options?.animals ?? []}
            herds={(options?.herds ?? []).map((h) => h.name)}
            picked={picked}
            busy={busy === "any"}
            onToggle={toggle}
            onPickAll={(ids, on) =>
              setPicked((s) => {
                const next = new Set(s);
                ids.forEach((a) => (on ? next.add(a) : next.delete(a)));
                return next;
              })
            }
            onMove={(herd, chosen) => moveThese(herd, chosen, "any")}
          />
        </TabsContent>
      </Tabs>
    </Page>
  );
}

function MoveAnyone({
  animals,
  herds,
  picked,
  busy,
  onToggle,
  onPickAll,
  onMove,
}: {
  animals: AnimalChoice[];
  herds: string[];
  picked: Set<string>;
  busy: boolean;
  onToggle: (animal: string) => void;
  onPickAll: (ids: string[], on: boolean) => void;
  onMove: (herd: string, chosen: string[]) => void;
}) {
  const [term, setTerm] = useState("");
  const [herd, setHerd] = useState("");

  const results = useMemo(() => {
    const q = term.trim().toLowerCase();
    if (!q) return animals;
    return animals.filter((a) =>
      [a.name, a.label, a.herd_label || a.herd || ""].some((f) => f.toLowerCase().includes(q)),
    );
  }, [animals, term]);

  // Only what is BOTH picked and not already there: a cow selected and then
  // filtered out of view is still going, and one already standing in the
  // destination is not a move.
  const chosen = useMemo(
    () => animals.filter((a) => picked.has(a.name) && a.herd !== herd).map((a) => a.name),
    [animals, picked, herd],
  );
  const shownIds = results.map((a) => a.name);
  const allShown = shownIds.length > 0 && shownIds.every((id) => picked.has(id));

  return (
    <Card>
      <CardHeaderRow>
        <CardHeading>
          <CardTitle>Move anyone</CardTitle>
          <CardDescription>
            Search the herd and pick who is going. Nothing here has to be due.
          </CardDescription>
        </CardHeading>
        <CardTools>
          <Picker
            value={herd}
            onChange={setHerd}
            options={herds}
            label="Herd they are moving to"
            placeholder="Moving to…"
            className="w-[190px]"
          />
          <Button
            size="sm"
            disabled={busy || !herd || !chosen.length}
            onClick={() => onMove(herd, chosen)}
          >
            {busy ? "Moving…" : `Move ${chosen.length || ""}`.trim()}
          </Button>
          {(!herd || !chosen.length) && (
            <span className="text-[11.5px] text-[var(--sd-quiet)]">
              {!chosen.length ? "Pick who is going." : "Choose where they are going."}
            </span>
          )}
        </CardTools>
      </CardHeaderRow>
      <CardContent className="flex flex-col gap-3 pt-0">
        <div className="flex flex-wrap items-center gap-2">
          <div className="relative min-w-[220px] flex-1">
            <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-[var(--sd-quiet)]" />
            <Input
              value={term}
              onChange={(e) => setTerm(e.target.value)}
              placeholder="Number, name or herd…"
              aria-label="Find animals to move"
              className="h-9 rounded-[var(--sd-radius-pill)] bg-[var(--sd-bg-soft)] pl-9 text-[13px]"
            />
          </div>
          <Button
            variant="outline"
            size="sm"
            disabled={!shownIds.length}
            onClick={() => onPickAll(shownIds, !allShown)}
            aria-label={
              allShown ? "Unpick everyone shown" : `Pick all ${shownIds.length} shown`
            }
          >
            {allShown ? "Unpick all shown" : `Select all ${shownIds.length} shown`}
          </Button>
          <span className="text-[11.5px] text-[var(--sd-quiet)]">
            {picked.size} picked
            {herd && chosen.length !== picked.size
              ? ` · ${picked.size - chosen.length} already in ${herd}`
              : ""}
          </span>
        </div>

        {!animals.length ? (
          <RowsSkeleton rows={6} />
        ) : !results.length ? (
          <p className="text-[13px] text-[var(--sd-muted)]">Nobody matches that.</p>
        ) : (
          <ul className="flex max-h-[460px] flex-col gap-0.5 overflow-y-auto">
            {results.map((a) => {
              const on = picked.has(a.name);
              const here = !!herd && a.herd === herd;
              return (
                <li key={a.name}>
                  <div
                    className={cn(
                      "flex items-center gap-3 rounded-[var(--sd-radius-lg)] px-3 py-2.5 transition-colors",
                      on ? "bg-[var(--sd-bg-soft)]" : "hover:bg-[var(--sd-bg-soft)]",
                      here && "opacity-50",
                    )}
                  >
                    <CheckCircle
                      checked={on}
                      onCheckedChange={() => onToggle(a.name)}
                      label={`Move ${a.label}`}
                    />
                    <button
                      type="button"
                      onClick={() => onToggle(a.name)}
                      className="flex min-w-0 flex-1 items-center gap-3 text-left"
                    >
                      <span className="flex min-w-0 flex-1 flex-col">
                        <span className="truncate text-[13px] font-medium text-[var(--sd-ink)]">
                          {a.label}
                        </span>
                        <span className="truncate text-[11.5px] text-[var(--sd-muted)]">
                          {a.herd_label || a.herd || "no herd"}
                          {a.repro ? ` · ${a.repro}` : ""}
                        </span>
                      </span>
                      {here && (
                        <span className="shrink-0 text-[11px] text-[var(--sd-quiet)]">
                          already there
                        </span>
                      )}
                    </button>
                  </div>
                </li>
              );
            })}
          </ul>
        )}
      </CardContent>
    </Card>
  );
}

function DestinationCard({
  herd,
  animals,
  picked,
  busy,
  onToggle,
  onPickAll,
  onMove,
}: {
  herd: string;
  animals: MoveSuggestion[];
  picked: Set<string>;
  busy: boolean;
  onToggle: (animal: string) => void;
  onPickAll: (on: boolean) => void;
  onMove: () => void;
}) {
  const chosen = animals.filter((a) => picked.has(a.animal)).length;
  const all = chosen === animals.length && animals.length > 0;
  const overdue = animals.filter((a) => a.overdue).length;

  return (
    <Card>
      <CardHeaderRow>
        <CardHeading>
          <CardTitle className="flex flex-wrap items-center gap-2">
            <span className="text-[var(--sd-muted)]">Moving to</span>
            <ArrowRight className="h-4 w-4 text-[var(--sd-quiet)]" strokeWidth={2} />
            {herd}
          </CardTitle>
          <CardDescription>
            {animals.length} due{overdue ? `, ${overdue} of them late` : ""}.
          </CardDescription>
        </CardHeading>
        <CardTools>
          <Button
            variant="outline"
            size="sm"
            onClick={() => onPickAll(!all)}
            aria-label={
              all ? `Unpick every animal due into ${herd}` : `Pick every animal due into ${herd}`
            }
          >
            {all ? "Unpick all" : `Select all ${animals.length}`}
          </Button>
          <Button size="sm" disabled={busy || !chosen} onClick={onMove}>
            {busy ? "Moving…" : `Move ${chosen || ""}`.trim()}
          </Button>
          {!chosen && (
            <span className="text-[11.5px] text-[var(--sd-quiet)]">Pick who is going.</span>
          )}
        </CardTools>
      </CardHeaderRow>
      <CardContent className="pt-0">
        {/* EACH GROUP SCROLLS INSIDE ITSELF. Ninety-four heifers due into one
            herd is a card the length of four screens, and with three such cards
            the page becomes a wall of cows with the next herd's Move button
            somewhere past the horizon. The buttons live in the card header, so
            capping the list keeps every one of them on screen. */}
        <ul className="flex max-h-[min(52vh,420px)] flex-col gap-0.5 overflow-y-auto">
          {animals.map((a) => {
            const on = picked.has(a.animal);
            return (
              <li key={a.animal}>
                <div
                  className={cn(
                    "flex items-center gap-3 rounded-[var(--sd-radius-lg)] px-3 py-2.5 transition-colors",
                    on ? "bg-[var(--sd-bg-soft)]" : "hover:bg-[var(--sd-bg-soft)]",
                  )}
                >
                  <CheckCircle
                    checked={on}
                    onCheckedChange={() => onToggle(a.animal)}
                    label={`Move ${a.label || a.animal} to ${herd}`}
                  />
                  {/* The row is the label, so the whole of it toggles — a
                      herdsman on a tablet should not have to find an 18px
                      circle. */}
                  <button
                    type="button"
                    onClick={() => onToggle(a.animal)}
                    className="flex min-w-0 flex-1 items-center gap-3 text-left"
                  >
                    <span className="flex min-w-0 flex-1 flex-col">
                      <span className="truncate text-[13px] font-medium text-[var(--sd-ink)]">
                        {a.label || a.animal}
                      </span>
                      <span className="truncate text-[11.5px] text-[var(--sd-muted)]">
                        {a.from_herd}
                        {a.reason ? ` · ${a.reason}` : ""}
                      </span>
                    </span>
                    <span
                      className={cn(
                        "flex shrink-0 items-center gap-1.5 text-[11.5px] tabular-nums",
                        a.overdue ? "text-[var(--sd-sev-critical)]" : "text-[var(--sd-quiet)]",
                      )}
                    >
                      {a.overdue ? (
                        <AlertTriangle className="h-3.5 w-3.5" strokeWidth={2} />
                      ) : (
                        <Clock className="h-3.5 w-3.5" strokeWidth={2} />
                      )}
                      {a.overdue ? `${a.days_over} days late` : "due"}
                    </span>
                  </button>
                </div>
              </li>
            );
          })}
        </ul>
      </CardContent>
    </Card>
  );
}
