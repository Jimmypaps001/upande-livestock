import { useCallback, useEffect, useMemo, useState } from "react";
import { AlertTriangle, Search } from "lucide-react";
import { CaseFile } from "@/components/health/CaseFile";
import { DatePicker } from "@/components/DatePicker";
import { Figure, FigureRow } from "@/components/Figure";
import { Notice } from "@/components/feeding/Notice";
import { Page, PageHeading } from "@/components/PageShell";
import { RefreshButton } from "@/components/RefreshButton";
import { RowsSkeleton } from "@/components/Loading";
import {
  Card, CardContent, CardDescription, CardHeaderRow, CardHeading, CardTitle, CardTools,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Picker } from "@/components/ui/picker";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { isError } from "@/lib/frappe";
import { getHealthCases, type CaseRegister, type CaseRow } from "@/lib/health";
import { cn, fmt, todayISO } from "@/lib/utils";

type Scope = { from: string; to: string };

function yearsBack(n: number): number[] {
  const now = new Date().getFullYear();
  return Array.from({ length: n }, (_, i) => now - i);
}

/** The windows a farm actually asks for, before it reaches for two dates. */
function preset(key: string): Scope | null {
  const today = todayISO();
  const year = today.slice(0, 4);
  const month = today.slice(0, 7);
  if (key === "month") return { from: `${month}-01`, to: today };
  if (key === "year") return { from: `${year}-01-01`, to: today };
  if (key === "12m") {
    const d = new Date();
    d.setFullYear(d.getFullYear() - 1);
    return { from: d.toISOString().slice(0, 10), to: today };
  }
  if (/^\d{4}$/.test(key)) return { from: `${key}-01-01`, to: `${key}-12-31` };
  return null;
}

/**
 * The register: the farm's health files, grouped and scoped.
 *
 * A LIST OF FOUR HUNDRED CASES IS NOT A REGISTER. It is a ward round with no
 * ward — the six cows being treated this morning are in there somewhere, in
 * date order, between files closed two years ago. So they are grouped the way a
 * hospital groups files, being treated and shut, and scoped to a window.
 *
 * OPENED IN A PERIOD AND OPEN IN IT ARE DIFFERENT QUESTIONS, and both get
 * answered. A file opened in March and still open in June is not one of June's
 * openings, but she is very much still a cow under treatment — so the open
 * group ignores the window and the counts do not.
 *
 * THE WINDOW IS PICKED IN STEPS, coarse before fine: this month, this year, a
 * year back, or a named year — and two dates underneath for when none of those
 * is the question. Nobody's first move is typing two dates.
 */
export function HealthCases() {
  const [scope, setScope] = useState<Scope>(() => preset("12m")!);
  const [reg, setReg] = useState<CaseRegister | null>(null);
  const [loading, setLoading] = useState(true);
  const [failure, setFailure] = useState<string | null>(null);
  const [term, setTerm] = useState("");
  const [open, setOpen] = useState<string | null>(null);
  const [tab, setTab] = useState("open");

  const load = useCallback(async () => {
    setLoading(true);
    const r = await getHealthCases({ from: scope.from, to: scope.to });
    setLoading(false);
    if (isError(r)) {
      setFailure(r.error);
      return;
    }
    setFailure(null);
    setReg(r);
  }, [scope.from, scope.to]);

  useEffect(() => {
    void load();
  }, [load]);

  const cases = reg?.cases ?? [];
  const matching = useMemo(() => {
    const q = term.trim().toLowerCase();
    if (!q) return cases;
    return cases.filter((c) =>
      [
        c.animal_name || c.animal,
        c.name,
        c.current_herd || "",
        c.provisional_diagnosis || "",
        c.confirmed_diagnosis || "",
        c.presenting_symptoms || "",
      ].some((f) => String(f).toLowerCase().includes(q)),
    );
  }, [cases, term]);

  const openFiles = matching.filter((c) => c.open);
  const closedFiles = matching.filter((c) => !c.open);
  const worrying = openFiles.filter((c) => c.concern);

  if (open) {
    return (
      <Page>
        <PageHeading eyebrow="Upande Livestock · Health" title="Health file">
          What was wrong, what was given, and which way she went.
        </PageHeading>
        <CaseFile name={open} onBack={() => setOpen(null)} onChanged={load} />
      </Page>
    );
  }

  return (
    <Page>
      <PageHeading eyebrow="Upande Livestock · Health" title="Health files">
        Every case the farm has opened. A file is opened when an animal is
        treated, written in as she is treated, and closed with an ending.
      </PageHeading>

      {failure && <Notice tone="error">{failure}</Notice>}

      <Card>
        <CardHeaderRow>
          <CardHeading>
            <CardTitle>The period</CardTitle>
            <CardDescription>
              Files opened or closed inside it, and everything still open
              whenever it started.
            </CardDescription>
          </CardHeading>
          <CardTools>
            <RefreshButton onClick={load} loading={loading} label="the register" />
          </CardTools>
        </CardHeaderRow>
        <CardContent className="flex flex-wrap items-end gap-4 pt-0">
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="hc-quick">Window</Label>
            <Picker
              id="hc-quick"
              value=""
              onChange={(key) => {
                const next = preset(key);
                if (next) setScope(next);
              }}
              options={[
                { value: "month", label: "This month" },
                { value: "year", label: "This year" },
                { value: "12m", label: "Last twelve months" },
                ...yearsBack(6).map((y) => ({ value: String(y), label: String(y) })),
              ]}
              label="Window"
              placeholder="Pick a period…"
              className="w-[190px]"
            />
          </div>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="hc-from">From</Label>
            <DatePicker
              id="hc-from"
              value={scope.from}
              max={scope.to}
              onChange={(from) => setScope((s) => ({ ...s, from }))}
            />
          </div>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="hc-to">To</Label>
            <DatePicker
              id="hc-to"
              value={scope.to}
              max={todayISO()}
              onChange={(to) => setScope((s) => ({ ...s, to }))}
            />
          </div>
          <div className="relative min-w-[220px] flex-1">
            <Label htmlFor="hc-find" className="sr-only">
              Find a file
            </Label>
            <Search className="pointer-events-none absolute left-3 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-[var(--sd-quiet)]" />
            <Input
              id="hc-find"
              value={term}
              onChange={(e) => setTerm(e.target.value)}
              placeholder="Animal, herd, diagnosis"
              className="pl-8"
            />
          </div>
        </CardContent>
      </Card>

      <FigureRow>
        <Figure
          loading={!reg}
          label="Opened"
          value={String(cases.filter((c) => inWindow(c.opened_date, scope)).length)}
          hint={`between ${scope.from} and ${scope.to}`}
        />
        <Figure
          loading={!reg}
          label="Closed"
          value={String(cases.filter((c) => inWindow(c.closed_date, scope)).length)}
          hint="files shut in the period"
        />
        <Figure
          loading={!reg}
          label="Still open"
          value={String(reg?.counts.open ?? 0)}
          hint="whenever they were opened"
        />
        <Figure
          loading={!reg}
          label="Worth a look"
          value={String(worrying.length)}
          hint={
            reg?.concern_days
              ? `open past ${reg.concern_days} days, or quiet for ${reg.stale_days}`
              : "the checks are switched off"
          }
        />
      </FigureRow>

      {reg?.truncated && (
        <Notice tone="info">
          Only the most recent {cases.length} files are shown. Narrow the period
          to see the rest.
        </Notice>
      )}

      <Tabs value={tab} onValueChange={setTab}>
        <TabsList>
          <TabsTrigger value="open">Being treated ({openFiles.length})</TabsTrigger>
          <TabsTrigger value="closed">Closed ({closedFiles.length})</TabsTrigger>
          <TabsTrigger value="all">All ({matching.length})</TabsTrigger>
        </TabsList>

        {(
          [
            ["open", openFiles, "Nothing is being treated in this period."],
            ["closed", closedFiles, "No file was closed in this period."],
            ["all", matching, "No file in this period."],
          ] as const
        ).map(([key, rows, empty]) => (
          <TabsContent key={key} value={key} className="pt-5">
            <Card>
              <CardContent className="pt-5">
                {!reg ? (
                  <RowsSkeleton rows={6} />
                ) : !rows.length ? (
                  <p className="text-[13px] text-[var(--sd-muted)]">{empty}</p>
                ) : (
                  // A register is a list you scroll THROUGH, not a page you
                  // scroll past. Up to two hundred files come back.
                  <ul className="flex max-h-[min(64vh,600px)] flex-col gap-1 overflow-y-auto">
                    {rows.map((c) => (
                      <Row key={c.name} c={c} onOpen={() => setOpen(c.name)} />
                    ))}
                  </ul>
                )}
              </CardContent>
            </Card>
          </TabsContent>
        ))}
      </Tabs>
    </Page>
  );
}

function inWindow(date: string | null, scope: Scope): boolean {
  return !!date && date >= scope.from && date <= scope.to;
}

function Row({ c, onOpen }: { c: CaseRow; onOpen: () => void }) {
  return (
    <li>
      <button
        type="button"
        onClick={onOpen}
        className="flex w-full items-center gap-3 rounded-[var(--sd-radius-lg)] px-3 py-2.5 text-left transition-colors hover:bg-[var(--sd-bg-soft)]"
      >
        <span className="flex min-w-0 flex-1 flex-col gap-0.5">
          <span className="truncate text-[13px] font-medium text-[var(--sd-ink)]">
            {c.animal_name || c.animal}
            <span className="ml-2 font-normal text-[11.5px] text-[var(--sd-quiet)]">
              {c.current_herd || "no herd"}
            </span>
          </span>
          <span className="truncate text-[11.5px] text-[var(--sd-muted)]">
            {c.opened_date}
            {" · "}
            {c.confirmed_diagnosis || c.provisional_diagnosis || c.presenting_symptoms || "no diagnosis recorded"}
          </span>
        </span>

        {c.concern && (
          <span
            title={c.concern.says}
            className="hidden shrink-0 items-center gap-1 text-[11.5px] text-[var(--sd-sev-moderate)] sm:inline-flex"
          >
            <AlertTriangle className="h-3.5 w-3.5" strokeWidth={2} />
            {c.concern.kind === "stale" ? "quiet" : "long"}
          </span>
        )}

        <span className="hidden w-24 shrink-0 text-right text-[11.5px] tabular-nums text-[var(--sd-quiet)] sm:block">
          {c.treatments} treatment{c.treatments === 1 ? "" : "s"}
        </span>

        <span
          className={cn(
            "w-[92px] shrink-0 rounded-[var(--sd-radius-pill)] px-2.5 py-1 text-center text-[11px]",
            c.open
              ? "bg-[var(--sd-bg-soft)] text-[var(--sd-ink)]"
              : "bg-[var(--sd-bg-soft)] text-[var(--sd-quiet)]",
          )}
        >
          {c.open ? `${c.days_open ?? 0} d open` : c.case_status}
        </span>
      </button>
    </li>
  );
}
