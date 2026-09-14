import { useCallback, useEffect, useMemo, useState } from "react";
import { Flag, Stethoscope } from "lucide-react";
import { CaseBadge } from "@/components/culling/CaseBadge";
import { RaiseCase } from "@/components/culling/RaiseCase";
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
import { Textarea } from "@/components/ui/textarea";
import { RowsSkeleton } from "@/components/Loading";
import { useToast } from "@/components/Toast";
import { isError } from "@/lib/frappe";
import {
  approveCull,
  asSummaries,
  getCullBoard,
  postCull,
  rejectCull,
  settleClaim,
  vetVerdict,
  VERDICTS,
  type CullBoard,
  type CullCase,
  type Verdict,
} from "@/lib/culling";
import { OperatorField } from "@/components/events/OperatorField";
import { useOperator } from "@/lib/operator";
import { cn, fmt } from "@/lib/utils";

/**
 * Everything leaving the farm, and whose turn each case is.
 *
 * ONE QUEUE, NOT FOUR SCREENS. The four flows differ in who signs and what
 * posts, but they are one job — a person opening this page wants to know what
 * is waiting on them, not which of four kinds of departure it happens to be.
 * Written as four pages, the gate that matters is always on the page nobody
 * opened.
 *
 * The case, once opened, is never recomputed. It is the argument that was made
 * on the day against the herd as it stood; a cow raised when she was bottom of
 * the herd should not quietly stop being a candidate because two worse ones
 * were bought in since.
 */
export function Culling() {
  const [board, setBoard] = useState<CullBoard | null>(null);
  const [loading, setLoading] = useState(true);
  const [failure, setFailure] = useState<string | null>(null);
  const [active, setActive] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const toast = useToast();
  const [notes, setNotes] = useState("");
  const [price, setPrice] = useState("");
  const [buyer, setBuyer] = useState("");
  const who = useOperator();

  const load = useCallback(async () => {
    setLoading(true);
    const r = await getCullBoard();
    setLoading(false);
    if (isError(r)) {
      setFailure(r.error);
      return;
    }
    setFailure(null);
    setBoard(r);
    setActive((current) => (current && r.cases.some((c) => c.name === current) ? current : r.cases[0]?.name ?? null));
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const cases = board?.cases ?? [];
  const roster = useMemo(() => asSummaries(board?.animals ?? []), [board?.animals]);
  const chosen = useMemo(() => cases.find((c) => c.name === active) ?? null, [cases, active]);

  useEffect(() => {
    setNotes("");
    setPrice(chosen?.sale_price ? String(chosen.sale_price) : "");
    setBuyer(chosen?.buyer_name ?? "");
  }, [chosen?.name]);

  async function act(fn: () => Promise<{ error?: string } | Record<string, unknown>>, said: string) {
    setBusy(true);
    const r = (await fn()) as { error?: string };
    setBusy(false);
    if (isError(r)) {
      toast(r.error, "error");
      return;
    }
    toast(said);
    void load();
  }

  return (
    <Page>
      <PageHeading eyebrow="Upande Livestock · Herd" title="Culling">
        Every animal leaving the farm passes through here — sold, disposed of,
        died or given away. Her records stay; only her place in a herd, in the
        head count and in the feed run goes.
      </PageHeading>

      {failure && <Notice tone="error">{failure}</Notice>}

      <FigureRow>
        <Figure loading={!board} label="With the vet" value={String(board?.counts.awaiting_vet ?? 0)} hint="awaiting a health verdict" />
        <Figure loading={!board} label="With the manager" value={String(board?.counts.awaiting_approval ?? 0)} hint="awaiting a signature" />
        <Figure loading={!board} label="Ready to post" value={String(board?.counts.ready_to_post ?? 0)} hint="approved, not yet gone" />
        <Figure loading={!board} label="Flagged" value={String(board?.counts.flagged ?? 0)} hint="marked for review, no case yet" />
      </FigureRow>

      <div className="grid min-w-0 gap-5 lg:grid-cols-[minmax(0,360px)_minmax(0,1fr)]">
        <Card>
          <CardHeaderRow>
            <CardHeading>
              <CardTitle>Open cases</CardTitle>
              <CardDescription>Whose turn it is, newest first.</CardDescription>
            </CardHeading>
            <CardTools>
              <RefreshButton onClick={load} loading={loading} label="the queue" />
            </CardTools>
          </CardHeaderRow>
          <CardContent className="pt-0">
            {!board ? (
              <RowsSkeleton rows={4} />
            ) : !cases.length ? (
              <p className="text-[13px] text-[var(--sd-muted)]">
                Nothing open. Every animal on the farm is staying on it.
              </p>
            ) : (
              <ul className="flex flex-col gap-1.5">
                {cases.map((c) => (
                  <li key={c.name}>
                    <button
                      type="button"
                      onClick={() => setActive(c.name)}
                      className={cn(
                        "flex w-full items-start gap-3 rounded-[var(--sd-radius-lg)] px-3 py-2.5 text-left transition-all",
                        c.name === active ? "bg-[var(--sd-bg-soft)]" : "hover:bg-[var(--sd-bg-soft)]",
                      )}
                    >
                      <span className="flex min-w-0 flex-1 flex-col gap-0.5">
                        <span className="truncate text-[13px] font-medium text-[var(--sd-ink)]">
                          {c.animal_name || c.animal}
                        </span>
                        <span className="text-[11.5px] text-[var(--sd-muted)]">
                          {c.flow} · {c.herd || "no herd"} · {c.disposal_date}
                        </span>
                      </span>
                      <CaseBadge status={c.status} waitingOn={c.waiting_on} />
                    </button>
                  </li>
                ))}
              </ul>
            )}

            {!!board?.flagged.length && (
              <div className="mt-5 border-t border-[var(--sd-line)] pt-4">
                <p className="mb-2 flex items-center gap-2 text-[11px] font-medium uppercase tracking-[0.14em] text-[var(--sd-quiet)]">
                  <Flag className="h-3.5 w-3.5" strokeWidth={2} />
                  Marked for review
                </p>
                <ul className="flex flex-col gap-2">
                  {board.flagged.map((f) => (
                    <li key={f.name} className="px-3 text-[12px] leading-snug text-[var(--sd-muted)]">
                      <span className="font-medium text-[var(--sd-ink)]">{f.burn_name || f.name}</span>
                      {f.reason ? ` — ${f.reason}` : ""}
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </CardContent>
        </Card>

        <div className="flex min-w-0 flex-col gap-5">
          <Card>
            <CardHeaderRow>
              <CardHeading>
                <CardTitle>{chosen ? chosen.animal_name || chosen.animal : "Nothing selected"}</CardTitle>
                <CardDescription>
                  {chosen
                    ? `${chosen.flow} · opened ${chosen.disposal_date} · with ${chosen.waiting_on}`
                    : "Pick a case on the left, or open a new one below."}
                </CardDescription>
              </CardHeading>
            </CardHeaderRow>
            <CardContent className="flex flex-col gap-4 pt-0">
              {!chosen ? (
                <p className="text-[13px] text-[var(--sd-muted)]">
                  A case records the argument for letting an animal go, and carries it
                  past the people who have to agree.
                </p>
              ) : (
                <CaseChain
                  c={chosen}
                  busy={busy}
                  notes={notes}
                  setNotes={setNotes}
                  price={price}
                  setPrice={setPrice}
                  buyer={buyer}
                  setBuyer={setBuyer}
                  act={act}
                  who={who}
                />
              )}
            </CardContent>
          </Card>

          <Card>
            <CardHeaderRow>
              <CardHeading>
                <CardTitle>Open a case</CardTitle>
                <CardDescription>
                  The farm's figures for her are shown before the flow is chosen.
                </CardDescription>
              </CardHeading>
            </CardHeaderRow>
            <CardContent className="pt-0">
              <RaiseCase
                who={who}
                animals={roster}
                onRaised={(m) => {
                  toast(m);
                  void load();
                }}
              />
            </CardContent>
          </Card>

          {!!board?.open_claims.length && (
            <Card>
              <CardHeaderRow>
                <CardHeading>
                  <CardTitle>Insurance claims</CardTitle>
                  <CardDescription>
                    Raised and not yet settled. A drafted claim nobody sends is worth nothing.
                  </CardDescription>
                </CardHeading>
              </CardHeaderRow>
              <CardContent className="flex flex-col gap-2 pt-0">
                {board.open_claims.map((cl) => (
                  <div
                    key={cl.name}
                    className="flex flex-wrap items-center gap-3 rounded-[var(--sd-radius-lg)] bg-[var(--sd-bg-soft)] px-3.5 py-3 shadow-[var(--sd-shadow-inset)]"
                  >
                    <span className="flex min-w-0 flex-1 flex-col">
                      <span className="truncate text-[13px] font-medium text-[var(--sd-ink)]">
                        {cl.animal} · {fmt(cl.claimed_amount)}
                      </span>
                      <span className="text-[11.5px] text-[var(--sd-muted)]">
                        {cl.policy} · {cl.cause || "no cause given"} · {cl.status}
                      </span>
                    </span>
                    {cl.status === "Draft" && (
                      <Button
                        variant="outline"
                        size="sm"
                        disabled={busy}
                        onClick={() =>
                          act(() => settleClaim(cl.name, "Submitted"), `${cl.name} is with the insurer.`)
                        }
                      >
                        Sent to the insurer
                      </Button>
                    )}
                    {cl.status === "Submitted" && (
                      <Button
                        variant="outline"
                        size="sm"
                        disabled={busy}
                        onClick={() =>
                          act(
                            () => settleClaim(cl.name, "Paid", cl.claimed_amount),
                            `${cl.name} is settled in full.`,
                          )
                        }
                      >
                        Paid in full
                      </Button>
                    )}
                  </div>
                ))}
              </CardContent>
            </Card>
          )}

          {!!board?.recent.length && (
            <Card>
              <CardHeaderRow>
                <CardHeading>
                  <CardTitle>Recently left</CardTitle>
                  <CardDescription>What the farm has to show for it.</CardDescription>
                </CardHeading>
              </CardHeaderRow>
              <CardContent className="pt-0">
                <ul className="flex flex-col gap-1">
                  {board.recent.slice(0, 12).map((r) => (
                    <li
                      key={r.name}
                      className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-0.5 px-1 py-1.5 text-[12.5px]"
                    >
                      <span className="text-[var(--sd-ink)]">
                        {r.animal_name || r.animal}
                        <span className="ml-2 text-[var(--sd-muted)]">{r.disposal_type}</span>
                      </span>
                      <span className="tabular-nums text-[var(--sd-quiet)]">
                        {r.disposal_date}
                        {r.sale_price ? ` · ${fmt(r.sale_price)}` : ""}
                        {r.claim ? ` · claim ${r.claim_status?.toLowerCase()}` : ""}
                      </span>
                    </li>
                  ))}
                </ul>
              </CardContent>
            </Card>
          )}
        </div>
      </div>
    </Page>
  );
}

/**
 * The buttons a case's own position allows, and only those.
 *
 * Which gate a case sits at decides what can be done to it, so the chain is
 * read off `status` rather than off the flow: a sale awaiting a vet and a gift
 * awaiting a manager are the same shape of decision to the person in front of
 * it, and offering an action the server will refuse is worse than offering
 * none.
 */
function CaseChain({
  c,
  busy,
  notes,
  setNotes,
  price,
  setPrice,
  buyer,
  setBuyer,
  act,
  who,
}: {
  c: CullCase;
  busy: boolean;
  notes: string;
  setNotes: (v: string) => void;
  price: string;
  setPrice: (v: string) => void;
  buyer: string;
  setBuyer: (v: string) => void;
  act: (fn: () => Promise<{ error?: string } | Record<string, unknown>>, said: string) => void;
  who: ReturnType<typeof useOperator>;
}) {
  const verdicts: readonly Verdict[] =
    c.flow === "Sale" ? (["Fit for sale", "Not fit for sale"] as const) : VERDICTS;

  return (
    <>
      {c.evidence && (
        <div className="rounded-[var(--sd-radius-lg)] bg-[var(--sd-bg-soft)] px-4 py-3.5 text-[13px] leading-relaxed text-[var(--sd-ink)] shadow-[var(--sd-shadow-inset)]">
          {c.evidence}
          {c.was_productive && (
            <p className="mt-2 text-[11.5px] text-[var(--sd-sev-moderate)]">
              She was performing when this case was opened. That is not a refusal — it is
              on the record.
            </p>
          )}
        </div>
      )}

      {c.death_cause && (
        <p className="text-[13px] text-[var(--sd-muted)]">Cause of death: {c.death_cause}</p>
      )}

      {c.vet_verdict && (
        <p className="flex items-center gap-2 text-[13px] text-[var(--sd-muted)]">
          <Stethoscope className="h-4 w-4 shrink-0 text-[var(--sd-quiet)]" strokeWidth={1.75} />
          The vet saw her on {c.vet_on}: {c.vet_verdict.toLowerCase()}.
        </p>
      )}

      {c.status === "Awaiting Vet" && (
        <div className="flex flex-col gap-3">
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="vet-notes">What the vet found</Label>
            <Textarea id="vet-notes" value={notes} onChange={(e) => setNotes(e.target.value)} />
          </div>
          <div className="flex flex-wrap gap-2">
            {verdicts.map((v) => (
              <Button
                key={v}
                variant={v === "Not fit for sale" ? "outline" : "default"}
                disabled={busy}
                onClick={() =>
                  act(
                    () => vetVerdict(c.name, v, notes),
                    v === "Not fit for sale"
                      ? "The case is closed — she is not fit to sell."
                      : "Recorded. The case has moved on.",
                  )
                }
              >
                {v}
              </Button>
            ))}
          </div>
        </div>
      )}

      {c.status === "Awaiting Approval" && (
        <div className="flex flex-col gap-3">
          {c.flow === "Sale" && (
            <div className="grid gap-4 sm:grid-cols-2">
              <div className="flex flex-col gap-1.5">
                <Label htmlFor="ap-buyer">Buyer</Label>
                <Input id="ap-buyer" value={buyer} onChange={(e) => setBuyer(e.target.value)} />
              </div>
              <div className="flex flex-col gap-1.5">
                <Label htmlFor="ap-price">Price</Label>
                <Input
                  id="ap-price"
                  type="number"
                  min={0}
                  value={price}
                  onChange={(e) => setPrice(e.target.value)}
                />
              </div>
              <p className="text-[11.5px] text-[var(--sd-muted)] sm:col-span-2">
                The approval is of these terms, not of the idea — so they are settled here
                rather than at posting.
              </p>
            </div>
          )}
          <div className="flex flex-wrap gap-2">
            <Button
              disabled={busy}
              onClick={() =>
                act(
                  () =>
                    approveCull(
                      c.name,
                      c.flow === "Sale"
                        ? { sale_price: price ? Number(price) : undefined, buyer_name: buyer || undefined }
                        : {},
                    ),
                  "Approved. She can be posted out.",
                )
              }
            >
              Approve
            </Button>
            <Button
              variant="outline"
              disabled={busy || !notes.trim()}
              onClick={() => act(() => rejectCull(c.name, notes), "The case is refused.")}
            >
              Refuse
            </Button>
          </div>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="ap-reason">Reason, if refusing</Label>
            <Textarea id="ap-reason" value={notes} onChange={(e) => setNotes(e.target.value)} />
          </div>
        </div>
      )}

      {c.status === "Approved" && (
        <div className="flex flex-col gap-3">
          <Notice tone="info">
            Posting is the step that cannot be undone by editing a record. She leaves her
            herd, her status becomes final, and the asset is sold or written off.
          </Notice>
          {who.mustAsk && <OperatorField operator={who.operator} onChange={who.setOperator} />}
          <div className="flex flex-wrap gap-2">
            <Button
              disabled={busy || who.needed}
              onClick={() =>
                act(() => postCull(c.name, who.value),
                    `${c.animal} has left the farm and her herd.`)
              }
            >
              Post it
            </Button>
            <Button
              variant="outline"
              disabled={busy || !notes.trim()}
              onClick={() => act(() => rejectCull(c.name, notes), "The case is refused.")}
            >
              Refuse
            </Button>
          </div>
        </div>
      )}
    </>
  );
}
