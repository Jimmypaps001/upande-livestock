import { useCallback, useEffect, useMemo, useState } from "react";
import { Check, PackagePlus, Split } from "lucide-react";
import { AnimalSearch } from "@/components/animals/AnimalSearch";
import { DatePicker } from "@/components/DatePicker";
import { Figure, FigureRow } from "@/components/Figure";
import { Notice } from "@/components/feeding/Notice";
import { Page, PageHeading } from "@/components/PageShell";
import { RefreshButton } from "@/components/RefreshButton";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeaderRow,
  CardHeading,
  CardTitle,
  CardTools,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useToast } from "@/components/Toast";
import { isError } from "@/lib/frappe";
import { asSummaries, getCullBoard, type FarmAnimal } from "@/lib/culling";
import { buyInAnimal, createHerd } from "@/lib/herds";
import { OperatorField } from "@/components/events/OperatorField";
import { useOperator } from "@/lib/operator";
import { cn, todayISO } from "@/lib/utils";

/**
 * Who stands with whom.
 *
 * Two ways a herd changes shape — animals already here moving together, and an
 * animal arriving bought — on one page because they are one decision and the
 * person making it is the same person. Splitting them across two screens would
 * mean the herd you just created is not on the list of the one that fills it.
 *
 * Neither writes `current_herd`. Both go through a Movement on the server, so
 * an animal's timeline can always answer where she was in March and who moved
 * her.
 */
export function Herds() {
  const who = useOperator();
  const [roster, setRoster] = useState<FarmAnimal[]>([]);
  const [herds, setHerds] = useState<string[]>([]);
  const [loading, setLoading] = useState(true);
  const [failure, setFailure] = useState<string | null>(null);
  const toast = useToast();

  const load = useCallback(async () => {
    setLoading(true);
    const r = await getCullBoard();
    setLoading(false);
    if (isError(r)) {
      setFailure(r.error);
      return;
    }
    setFailure(null);
    setRoster(r.animals);
    setHerds([...new Set(r.animals.map((a) => a.current_herd).filter(Boolean) as string[])].sort());
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  return (
    <Page>
      <PageHeading eyebrow="Upande Livestock · Herd" title="Herds">
        Split a herd off the animals already here, or bring one in from
        outside. Every animal arrives by a movement, so her record always says
        where she came from.
      </PageHeading>

      {failure && <Notice tone="error">{failure}</Notice>}

      <FigureRow>
        <Figure label="Animals on the farm" value={String(roster.length)} hint="active" />
        <Figure label="Herds" value={String(herds.length)} hint="holding at least one animal" />
      </FigureRow>

      <div className="grid min-w-0 gap-5 lg:grid-cols-2">
        <SplitHerd
          who={who}
          roster={roster}
          loading={loading}
          onReload={load}
          onDone={(m) => {
            toast(m);
            void load();
          }}
        />
        <BuyIn
          who={who}
          herds={herds}
          onDone={(m) => {
            toast(m);
            void load();
          }}
        />
      </div>
    </Page>
  );
}

type Who = ReturnType<typeof useOperator>;

function SplitHerd({
  who,
  roster,
  loading,
  onReload,
  onDone,
}: {
  who: Who;
  roster: FarmAnimal[];
  loading: boolean;
  onReload: () => void;
  onDone: (message: string) => void;
}) {
  const [name, setName] = useState("");
  const [picked, setPicked] = useState<string[]>([]);
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<string | null>(null);

  const summaries = useMemo(() => asSummaries(roster), [roster]);
  const chosen = useMemo(() => new Set(picked), [picked]);

  async function submit() {
    setBusy(true);
    setFailure(null);
    const r = await createHerd({ herd_name: name.trim(), animals: picked, operator: who.value });
    setBusy(false);
    if (isError(r)) {
      setFailure(r.error);
      return;
    }
    onDone(
      r.heads
        ? `${r.herd} holds ${r.heads} animal${r.heads === 1 ? "" : "s"}, moved out of ${
            r.emptied_from.join(", ") || "no herd"
          }.`
        : `${r.herd} is ready and empty.`,
    );
    setName("");
    setPicked([]);
  }

  return (
    <Card>
      <CardHeaderRow>
        <CardHeading>
          <CardTitle>Split a herd off</CardTitle>
          <CardDescription>
            Pick the animals that go together. They keep their history; only where
            they stand changes.
          </CardDescription>
        </CardHeading>
        <CardTools>
          <RefreshButton onClick={onReload} loading={loading} label="the roster" />
        </CardTools>
      </CardHeaderRow>
      <CardContent className="flex flex-col gap-4 pt-0">
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="h-name">What the herd is called</Label>
          <Input
            id="h-name"
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="Lactating group 4"
          />
        </div>

        <div className="flex max-h-[320px] flex-col gap-1.5 overflow-hidden">
          <Label>Who goes into it</Label>
          <AnimalSearch
            animals={summaries}
            selectedId={null}
            onSelect={(a) =>
              setPicked((p) => (p.includes(a.id) ? p.filter((x) => x !== a.id) : [...p, a.id]))
            }
          />
        </div>

        {!!picked.length && (
          <div className="rounded-[var(--sd-radius-lg)] bg-[var(--sd-bg-soft)] px-3.5 py-3 shadow-[var(--sd-shadow-inset)]">
            <p className="mb-1.5 text-[11px] font-medium uppercase tracking-[0.14em] text-[var(--sd-quiet)]">
              {picked.length} picked
            </p>
            <div className="flex flex-wrap gap-1.5">
              {picked.map((id) => (
                <button
                  key={id}
                  type="button"
                  onClick={() => setPicked((p) => p.filter((x) => x !== id))}
                  className={cn(
                    "inline-flex items-center gap-1 rounded-[var(--sd-radius-pill)] bg-[var(--sd-card)] px-2.5 py-1 text-[11.5px] tabular-nums text-[var(--sd-ink)]",
                    "shadow-[var(--sd-shadow-1)] transition-colors hover:text-[var(--sd-sev-critical)]",
                  )}
                >
                  <Check className="h-3 w-3" strokeWidth={2.5} />
                  {id}
                </button>
              ))}
            </div>
            <p className="mt-2 text-[11px] text-[var(--sd-quiet)]">
              {chosen.size === picked.length ? "Tap one to take it out again." : ""}
            </p>
          </div>
        )}

        {failure && <Notice tone="error">{failure}</Notice>}

        {who.needed && <OperatorField operator={who.operator} onChange={who.setOperator} />}
        <Button onClick={submit} disabled={busy || !name.trim() || who.needed}>
          <Split className="mr-2 h-4 w-4" strokeWidth={1.75} />
          {busy
            ? "Moving…"
            : picked.length
              ? `Create it with ${picked.length} animal${picked.length === 1 ? "" : "s"}`
              : "Create it empty"}
        </Button>
      </CardContent>
    </Card>
  );
}

function BuyIn({
  who,
  herds,
  onDone,
}: {
  who: Who;
  herds: string[];
  onDone: (message: string) => void;
}) {
  const [sex, setSex] = useState<"Female" | "Male">("Female");
  const [herd, setHerd] = useState("");
  const [given, setGiven] = useState("");
  const [seller, setSeller] = useState("");
  const [sellerTag, setSellerTag] = useState("");
  const [price, setPrice] = useState("");
  const [born, setBorn] = useState("");
  const [arrived, setArrived] = useState(todayISO());
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<string | null>(null);

  useEffect(() => {
    if (!herd && herds.length) setHerd(herds[0]);
  }, [herds, herd]);

  async function submit() {
    setBusy(true);
    setFailure(null);
    const r = await buyInAnimal({
      sex,
      herd,
      name_given: given.trim() || undefined,
      seller: seller.trim() || undefined,
      seller_tag: sellerTag.trim() || undefined,
      purchase_value: price ? Number(price) : undefined,
      date_of_birth: born || undefined,
      arrival_date: arrived,
      operator: who.value,
    });
    setBusy(false);
    if (isError(r)) {
      setFailure(r.error);
      return;
    }
    onDone(
      `${r.name} is on the farm as ${r.animal}, in ${r.herd}${
        r.asset ? `, on the books at ${r.purchase_value}` : ", not capitalised"
      }.`,
    );
    setGiven("");
    setSeller("");
    setSellerTag("");
    setPrice("");
    setBorn("");
  }

  return (
    <Card>
      <CardHeaderRow>
        <CardHeading>
          <CardTitle>Bring one in</CardTitle>
          <CardDescription>
            She gets the farm's next register number, not the seller's tag — that is
            kept as a note.
          </CardDescription>
        </CardHeading>
      </CardHeaderRow>
      <CardContent className="flex flex-col gap-4 pt-0">
        <div className="grid gap-4 sm:grid-cols-2">
          <div className="flex flex-col gap-1.5">
            <Label>Female or male</Label>
            <div className="flex items-center gap-1 rounded-[var(--sd-radius-pill)] bg-[var(--sd-bg-soft)] p-0.5">
              {(["Female", "Male"] as const).map((s) => (
                <button
                  key={s}
                  type="button"
                  onClick={() => setSex(s)}
                  className={cn(
                    "flex-1 rounded-[var(--sd-radius-pill)] px-3 py-1.5 text-[12px] font-medium transition-all",
                    s === sex
                      ? "bg-[var(--sd-card)] text-[var(--sd-ink)] shadow-[var(--sd-shadow-1)]"
                      : "text-[var(--sd-muted)] hover:text-[var(--sd-ink)]",
                  )}
                >
                  {s}
                </button>
              ))}
            </div>
            <span className="text-[11px] text-[var(--sd-quiet)]">
              Decides her number series, so it cannot be guessed.
            </span>
          </div>

          <div className="flex flex-col gap-1.5">
            <Label htmlFor="b-herd">Into which herd</Label>
            <select
              id="b-herd"
              value={herd}
              onChange={(e) => setHerd(e.target.value)}
              className="h-9 w-full rounded-md border border-input bg-background px-3 text-sm"
            >
              {herds.map((h) => (
                <option key={h} value={h}>
                  {h}
                </option>
              ))}
            </select>
          </div>

          <div className="flex flex-col gap-1.5">
            <Label htmlFor="b-name">What she is called</Label>
            <Input id="b-name" value={given} onChange={(e) => setGiven(e.target.value)} />
          </div>

          <div className="flex flex-col gap-1.5">
            <Label htmlFor="b-seller">Bought from</Label>
            <Input id="b-seller" value={seller} onChange={(e) => setSeller(e.target.value)} />
          </div>

          <div className="flex flex-col gap-1.5">
            <Label htmlFor="b-tag">Their tag for her</Label>
            <Input
              id="b-tag"
              value={sellerTag}
              onChange={(e) => setSellerTag(e.target.value)}
              placeholder="KD-441"
            />
          </div>

          <div className="flex flex-col gap-1.5">
            <Label htmlFor="b-price">What she cost</Label>
            <Input
              id="b-price"
              type="number"
              min={0}
              value={price}
              onChange={(e) => setPrice(e.target.value)}
            />
            <span className="text-[11px] text-[var(--sd-quiet)]">
              Leave blank for a gift or a transfer in — she is not capitalised.
            </span>
          </div>

          <div className="flex flex-col gap-1.5">
            <Label htmlFor="b-born">Born</Label>
            <DatePicker id="b-born" value={born} max={todayISO()} onChange={setBorn} />
          </div>

          <div className="flex flex-col gap-1.5">
            <Label htmlFor="b-arrived">Arrived</Label>
            <DatePicker id="b-arrived" value={arrived} max={todayISO()} onChange={setArrived} />
          </div>
        </div>

        {failure && <Notice tone="error">{failure}</Notice>}

        {who.needed && <OperatorField operator={who.operator} onChange={who.setOperator} />}
        <Button onClick={submit} disabled={busy || !herd || who.needed}>
          <PackagePlus className="mr-2 h-4 w-4" strokeWidth={1.75} />
          {busy ? "Bringing her in…" : "Bring her onto the farm"}
        </Button>
      </CardContent>
    </Card>
  );
}
