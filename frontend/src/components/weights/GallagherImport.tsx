import { useCallback, useRef, useState } from "react";
import { FileUp } from "lucide-react";
import { Notice } from "@/components/feeding/Notice";
import { STICKY_HEAD, ScrollTable } from "@/components/ScrollTable";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { isError } from "@/lib/frappe";
import {
  commitGallagher,
  previewGallagher,
  readFile,
  type DateOrder,
  type GallagherFile,
  type GallagherPreview,
  type GallagherResult,
} from "@/lib/gallagher";
import { cn, fmt } from "@/lib/utils";

/**
 * Drop a Gallagher session file here and read what it says before anything is
 * recorded: the days it covers, who it found, who it did not, and which animals
 * on the farm did not go through the race. Import writes the weights.
 */
export function GallagherDrop({ onImported }: { onImported?: () => void }) {
  const [over, setOver] = useState(false);
  const [open, setOpen] = useState(false);
  const [file, setFile] = useState<GallagherFile | null>(null);
  const [preview, setPreview] = useState<GallagherPreview | null>(null);
  const [result, setResult] = useState<GallagherResult | null>(null);
  const [failure, setFailure] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [herds, setHerds] = useState<string[]>([]);
  const [order, setOrder] = useState<DateOrder>("auto");
  const input = useRef<HTMLInputElement>(null);

  const run = useCallback(async (f: GallagherFile, scope: string[], dateOrder: DateOrder) => {
    setBusy(true);
    const r = await previewGallagher(f, scope, dateOrder);
    setBusy(false);
    if (isError(r)) {
      setFailure(r.error);
      setPreview(null);
      return;
    }
    setFailure(null);
    setPreview(r as GallagherPreview);
  }, []);

  async function take(picked: File | undefined) {
    if (!picked) return;
    setOpen(true);
    setResult(null);
    setPreview(null);
    setHerds([]);
    setOrder("auto");
    setFailure(null);
    let f: GallagherFile;
    try {
      f = await readFile(picked);
    } catch (e) {
      setFailure(e instanceof Error ? e.message : "The file could not be read.");
      return;
    }
    setFile(f);
    await run(f, [], "auto");
  }

  function toggleHerd(h: string) {
    const next = herds.includes(h) ? herds.filter((x) => x !== h) : [...herds, h];
    setHerds(next);
    if (file) void run(file, next, order);
  }

  function changeOrder(next: DateOrder) {
    setOrder(next);
    if (file) void run(file, herds, next);
  }

  async function doImport() {
    if (!file) return;
    setBusy(true);
    const r = await commitGallagher(file, herds, order);
    setBusy(false);
    if (isError(r)) {
      setFailure(r.error);
      return;
    }
    setFailure(null);
    setResult(r as GallagherResult);
    onImported?.();
  }

  const s = preview?.summary;
  return (
    <>
      <div
        onDragOver={(e) => {
          e.preventDefault();
          setOver(true);
        }}
        onDragLeave={() => setOver(false)}
        onDrop={(e) => {
          e.preventDefault();
          setOver(false);
          void take(e.dataTransfer.files?.[0]);
        }}
        className={cn(
          "flex flex-wrap items-center gap-3 rounded-[var(--sd-radius-lg)] border border-dashed px-4 py-3.5 transition-colors",
          over
            ? "border-[var(--sd-ink)] bg-[var(--sd-bg-soft)]"
            : "border-[var(--sd-line)]",
        )}
      >
        <FileUp className="h-5 w-5 text-[var(--sd-muted)]" strokeWidth={1.75} />
        <div className="min-w-0 flex-1">
          <p className="text-[13px] font-medium text-[var(--sd-ink)]">Import Gallagher file</p>
          <p className="text-[11.5px] text-[var(--sd-muted)]">
            Drop the scale's session file here (CSV or Excel), or choose it.
          </p>
        </div>
        <Button variant="outline" size="sm" onClick={() => input.current?.click()}>
          Choose file
        </Button>
        <input
          ref={input}
          type="file"
          accept=".csv,.xls,.xlsx"
          className="hidden"
          aria-label="Gallagher file"
          onChange={(e) => {
            void take(e.target.files?.[0]);
            e.target.value = "";
          }}
        />
      </div>

      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent className="max-h-[94vh] w-[min(1000px,96vw)] max-w-none overflow-y-auto">
          <DialogHeader>
            <DialogTitle>Import Gallagher file</DialogTitle>
            <DialogDescription>
              {file?.filename ?? "Reading the file"} — check it over, then import.
            </DialogDescription>
          </DialogHeader>

          {failure && <Notice tone="error">{failure}</Notice>}
          {busy && !preview && !result && (
            <p className="text-[13px] text-[var(--sd-muted)]">Reading the file…</p>
          )}

          {result ? (
            <Result result={result} onClose={() => setOpen(false)} />
          ) : (
            preview &&
            s && (
              <div className="flex flex-col gap-4">
                <DateCheck p={preview} order={order} onOrder={changeOrder} />

                <div className="grid gap-2 sm:grid-cols-3">
                  <Stat label="Rows in file" value={s.rows} />
                  <Stat label="Animals matched" value={s.matched_animals} />
                  <Stat label="To record" value={s.to_record} />
                  <Stat label="Not found" value={s.unmatched_rows + s.invalid_rows} />
                  <Stat label="Already recorded" value={s.already_recorded + s.repeats} />
                  <Stat
                    label="Active not weighed"
                    value={s.not_weighed}
                    hint={`of ${s.active_animals}${herds.length ? " in the chosen herds" : " on the farm"}`}
                  />
                </div>

                {preview.unmatched.length > 0 && (
                  <section className="flex flex-col gap-1.5">
                    <h3 className="text-[13px] font-medium text-[var(--sd-ink)]">
                      Rows that cannot be recorded ({preview.unmatched.length})
                    </h3>
                    <ScrollTable className="rounded-[var(--sd-radius-lg)] bg-[var(--sd-bg-soft)] shadow-[var(--sd-shadow-inset)]">
                      <table className="w-full min-w-[560px] border-collapse text-[13px]">
                        <thead className={STICKY_HEAD}>
                          <tr className="text-left text-[11px] uppercase tracking-[0.06em] text-[var(--sd-quiet)]">
                            <th className="px-3.5 py-2 font-medium">Row</th>
                            <th className="px-3 py-2 font-medium">VID</th>
                            <th className="px-3 py-2 font-medium">EID</th>
                            <th className="px-3 py-2 text-right font-medium">Weight (kg)</th>
                            <th className="px-3.5 py-2 font-medium">Why</th>
                          </tr>
                        </thead>
                        <tbody>
                          {preview.unmatched.map((r) => (
                            <tr key={r.row} className="border-t border-[var(--sd-line)] align-top">
                              <td className="px-3.5 py-1.5 tabular-nums">{r.row}</td>
                              <td className="px-3 py-1.5">{r.vid || "—"}</td>
                              <td className="px-3 py-1.5 tabular-nums">{r.eid || "—"}</td>
                              <td className="px-3 py-1.5 text-right tabular-nums">{fmt(r.weight_kg)}</td>
                              <td className="px-3.5 py-1.5 text-[12px] text-[var(--sd-muted)]">
                                {r.why}
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </ScrollTable>
                  </section>
                )}

                <section className="flex flex-col gap-2">
                  <h3 className="text-[13px] font-medium text-[var(--sd-ink)]">
                    Active animals not weighed in this session
                  </h3>
                  <div className="flex flex-wrap gap-1.5">
                    {preview.herds.map((h) => (
                      <button
                        key={h.herd || "none"}
                        type="button"
                        onClick={() => toggleHerd(h.herd)}
                        aria-pressed={herds.includes(h.herd)}
                        className={cn(
                          "rounded-[var(--sd-radius-pill)] px-3 py-1 text-[12px] transition-colors",
                          herds.includes(h.herd)
                            ? "bg-[var(--sd-ink)] text-[var(--sd-card)]"
                            : "bg-[var(--sd-bg-soft)] text-[var(--sd-muted)] hover:text-[var(--sd-ink)]",
                        )}
                      >
                        {h.label} · {h.weighed}/{h.active}
                      </button>
                    ))}
                  </div>
                  <p className="text-[11.5px] text-[var(--sd-muted)]">
                    {herds.length
                      ? "Showing the chosen herds. Choose a herd again to take it off."
                      : "Showing the whole farm. Choose herds to narrow it."}
                  </p>
                  {preview.not_weighed.length === 0 ? (
                    <Notice tone="ok">Every active animal here went through.</Notice>
                  ) : (
                    <ScrollTable className="rounded-[var(--sd-radius-lg)] bg-[var(--sd-bg-soft)] shadow-[var(--sd-shadow-inset)]">
                      <table className="w-full min-w-[460px] border-collapse text-[13px]">
                        <thead className={STICKY_HEAD}>
                          <tr className="text-left text-[11px] uppercase tracking-[0.06em] text-[var(--sd-quiet)]">
                            <th className="px-3.5 py-2 font-medium">Animal</th>
                            <th className="px-3 py-2 font-medium">Herd</th>
                            <th className="px-3.5 py-2 text-right font-medium">Last weighed</th>
                          </tr>
                        </thead>
                        <tbody>
                          {preview.not_weighed.map((a) => (
                            <tr key={a.animal} className="border-t border-[var(--sd-line)]">
                              <td className="px-3.5 py-1.5 font-medium text-[var(--sd-ink)]">
                                {a.label}
                              </td>
                              <td className="px-3 py-1.5">{a.herd_label}</td>
                              <td className="px-3.5 py-1.5 text-right tabular-nums">
                                {a.last_weight_date
                                  ? `${a.last_weight_date}${a.last_weight_kg ? ` · ${fmt(a.last_weight_kg)} kg` : ""}`
                                  : "never"}
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </ScrollTable>
                  )}
                </section>

                <div className="flex flex-wrap items-center gap-3">
                  <Button onClick={doImport} disabled={busy || s.to_record === 0}>
                    {busy ? "Working…" : `Import ${s.to_record} weight${s.to_record === 1 ? "" : "s"}`}
                  </Button>
                  <Button variant="outline" onClick={() => setOpen(false)}>
                    Cancel
                  </Button>
                  {s.to_record === 0 && (
                    <span className="text-[11.5px] text-[var(--sd-muted)]">
                      Nothing in this file can be recorded.
                    </span>
                  )}
                </div>
              </div>
            )
          )}
        </DialogContent>
      </Dialog>
    </>
  );
}

function Stat({ label, value, hint }: { label: string; value: number; hint?: string }) {
  return (
    <div className="rounded-[var(--sd-radius-lg)] bg-[var(--sd-bg-soft)] px-4 py-3">
      <p className="text-[11px] uppercase tracking-[0.06em] text-[var(--sd-quiet)]">{label}</p>
      <p className="text-[22px] font-medium tabular-nums text-[var(--sd-ink)]">{value}</p>
      {hint && <p className="text-[11px] text-[var(--sd-muted)]">{hint}</p>}
    </div>
  );
}

function DateCheck({
  p,
  order,
  onOrder,
}: {
  p: GallagherPreview;
  order: DateOrder;
  onOrder: (o: DateOrder) => void;
}) {
  const d = p.dates;
  const used = p.date_order.used;
  const other = used === "mdy" ? "dmy" : "mdy";
  const name = (o: string) => (o === "mdy" ? "month first (9/15/2026)" : "day first (15/9/2026)");
  return (
    <section className="flex flex-col gap-2">
      <h3 className="text-[13px] font-medium text-[var(--sd-ink)]">Date check</h3>
      <p className="text-[13px] text-[var(--sd-muted)]">
        {d.from
          ? d.from === d.to
            ? `Weighed on ${d.from}.`
            : `Weighed from ${d.from} to ${d.to}.`
          : "No readable dates."}{" "}
        {d.per_date.map((x) => `${x.date}: ${x.rows} rows`).join(" · ")}
      </p>
      <p className="text-[13px] text-[var(--sd-muted)]">
        Dates read {name(used)}
        {p.date_order.settled ? ", as the file's own dates show." : "; the file does not say, so month first is assumed."}{" "}
        <button
          type="button"
          className="underline underline-offset-2"
          onClick={() => onOrder(order === "auto" ? other : order === "mdy" ? "dmy" : "mdy")}
        >
          Read them {name(other)} instead
        </button>
        {order !== "auto" && (
          <>
            {" · "}
            <button type="button" className="underline underline-offset-2" onClick={() => onOrder("auto")}>
              Let the file decide
            </button>
          </>
        )}
      </p>
      {d.notes.map((n, i) => (
        <Notice key={i} tone={d.mixed || d.future.length || d.unreadable ? "error" : "info"}>
          {n}
        </Notice>
      ))}
      {d.on_several_days.length > 0 && (
        <Notice tone="info">
          Weighed on more than one day in this file: {d.on_several_days.join(", ")}.
        </Notice>
      )}
    </section>
  );
}

function Result({ result, onClose }: { result: GallagherResult; onClose: () => void }) {
  return (
    <div className="flex flex-col gap-3">
      <Notice tone={result.failed.length ? "info" : "ok"}>
        {result.recorded} weight{result.recorded === 1 ? "" : "s"} recorded
        {result.already_recorded ? `, ${result.already_recorded} already there` : ""}
        {result.not_recorded ? `, ${result.not_recorded} left out` : ""}
        {result.eids_filled ? `, ${result.eids_filled} ear tag numbers saved on their animals` : ""}.
      </Notice>
      {result.failed.length > 0 && (
        <Notice tone="error">
          {result.failed.length} would not take:{" "}
          {result.failed.map((f) => `${f.label || f.animal} (row ${f.row}) — ${f.why}`).join("; ")}
        </Notice>
      )}
      <div>
        <Button onClick={onClose}>Done</Button>
      </div>
    </div>
  );
}
