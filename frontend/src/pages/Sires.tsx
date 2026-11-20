import { useCallback, useEffect, useMemo, useState } from "react";
import { Plus, Search } from "lucide-react";
import { Notice } from "@/components/feeding/Notice";
import { Page, PageHeading } from "@/components/PageShell";
import { RefreshButton } from "@/components/RefreshButton";
import { SireDialog } from "@/components/sires/SireDialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { isError } from "@/lib/frappe";
import { getSires, SIRE_TYPES, type SireRow } from "@/lib/sires";
import { cn } from "@/lib/utils";

const TYPES = ["All", ...SIRE_TYPES] as const;

/**
 * Breeding ▸ Sires — the bulls a Service can name, kept by the manager.
 *
 * A semen sire carries the straw item that is issued for him; a live bull his
 * animal record. A sire switched off stays on the services that used him but is
 * no longer offered on the form.
 */
export function Sires() {
  const [rows, setRows] = useState<SireRow[] | null>(null);
  const [loading, setLoading] = useState(true);
  const [failure, setFailure] = useState<string | null>(null);
  const [term, setTerm] = useState("");
  const [type, setType] = useState<(typeof TYPES)[number]>("All");
  const [editing, setEditing] = useState<SireRow | null | "new">(null);

  const load = useCallback(async () => {
    setLoading(true);
    const r = await getSires();
    setLoading(false);
    if (isError(r)) {
      setFailure(r.error);
      return;
    }
    setFailure(null);
    setRows(r.sires ?? []);
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const shown = useMemo(() => {
    const q = term.trim().toLowerCase();
    return (rows ?? []).filter(
      (s) => (type === "All" || s.sire_type === type) && (!q || `${s.sire_name} ${s.code}`.toLowerCase().includes(q)),
    );
  }, [rows, term, type]);

  return (
    <Page>
      <PageHeading
        eyebrow="Upande Livestock · Breeding"
        title="Sires"
        actions={
          <>
            <RefreshButton onClick={load} loading={loading} label="the sires" />
            <Button onClick={() => setEditing("new")}>
              <Plus className="mr-1.5 h-4 w-4" />
              Add sire
            </Button>
          </>
        }
      >
        The bulls a service can name, by name and code.
      </PageHeading>

      {failure && <Notice tone="error">{failure}</Notice>}

      <div className="flex flex-wrap items-center gap-3">
        <div className="relative min-w-[220px] max-w-sm flex-1">
          <Label htmlFor="sires-find" className="sr-only">
            Find a sire
          </Label>
          <Search className="pointer-events-none absolute left-3 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-[var(--sd-quiet)]" />
          <Input id="sires-find" value={term} onChange={(e) => setTerm(e.target.value)} placeholder="Name or code" className="pl-8" />
        </div>
        <div className="flex gap-1.5" role="group" aria-label="Sire type">
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

      {shown.length ? (
        <div className="overflow-x-auto rounded-[var(--sd-radius-card)] ring-1 ring-[var(--sd-line)]">
          <table className="w-full text-left text-[13px]">
            <thead className="text-[11.5px] uppercase tracking-wide text-[var(--sd-quiet)]">
              <tr>
                <th className="px-3 py-2">Sire</th>
                <th className="px-3 py-2">Code</th>
                <th className="px-3 py-2">Type</th>
                <th className="px-3 py-2">Straw / animal</th>
                <th className="px-3 py-2">Status</th>
                <th className="px-3 py-2" />
              </tr>
            </thead>
            <tbody>
              {shown.map((s) => (
                <tr key={s.name} className="border-t border-[var(--sd-line)]">
                  <td className="px-3 py-2 font-medium">
                    {s.sire_name}
                    {s.sexed ? <span className="ml-2 rounded-full bg-[var(--sd-bg-soft)] px-2 py-0.5 text-[11px]">sexed</span> : null}
                  </td>
                  <td className="px-3 py-2">{s.code || "—"}</td>
                  <td className="px-3 py-2">{s.sire_type}</td>
                  <td className="px-3 py-2">{s.sire_type === "Semen" ? s.semen_item || "—" : s.animal || "—"}</td>
                  <td className="px-3 py-2">{s.active ? "Active" : "Off"}</td>
                  <td className="px-3 py-2 text-right">
                    <Button variant="ghost" size="sm" onClick={() => setEditing(s)} aria-label={`Edit ${s.sire_name}`}>
                      Edit
                    </Button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : rows ? (
        <p className="py-10 text-center text-[13px] text-[var(--sd-muted)]">
          {rows.length ? "No sire matches." : "No sires yet. Add the first one."}
        </p>
      ) : null}

      <SireDialog
        open={editing !== null}
        sire={editing === "new" ? null : editing}
        onOpenChange={(o) => !o && setEditing(null)}
        onSaved={() => void load()}
      />
    </Page>
  );
}
