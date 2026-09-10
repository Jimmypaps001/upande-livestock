import { useEffect, useRef, useState } from "react";
import { Check, ChevronDown, Loader2, X } from "lucide-react";
import { Input } from "@/components/ui/input";
import { searchLink } from "@/lib/frappe";
import { cn } from "@/lib/utils";

/**
 * A picker over real records, and only real records.
 *
 * Every link on this page names something the farm posts against — the
 * warehouse the milk lands in, the account the journal entry credits, the herd
 * a newborn joins. A wrong value in one of those does not raise; it posts
 * somewhere else and is found in the reconciliation. So what the operator types
 * is a search term and never a value: the field only changes when a row in the
 * list is chosen, or when Clear is pressed.
 *
 * The list comes from the framework's own autosuggest endpoint, so it shows
 * exactly what a desk Link field would show for this user — including nothing
 * at all, if they are not permitted to list that doctype. That case says so,
 * because "you cannot search Account" and "there are no Accounts" are different
 * problems and only one of them is the operator's to solve.
 */
export function LinkPicker({
  id,
  doctype,
  value,
  onChange,
  disabled,
}: {
  id?: string;
  doctype: string;
  value: string | null;
  onChange: (next: string | null) => void;
  disabled?: boolean;
}) {
  const [open, setOpen] = useState(false);
  const [term, setTerm] = useState("");
  const [rows, setRows] = useState<Array<{ value: string; description: string }>>([]);
  const [busy, setBusy] = useState(false);
  const [failed, setFailed] = useState(false);
  const box = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (!open) return;
    const onDocClick = (e: MouseEvent) => {
      if (box.current && !box.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", onDocClick);
    return () => document.removeEventListener("mousedown", onDocClick);
  }, [open]);

  // Debounced so a typed word is one search, not seven.
  useEffect(() => {
    if (!open) return;
    let live = true;
    setBusy(true);
    const t = setTimeout(async () => {
      const found = await searchLink(doctype, term);
      if (!live) return;
      setBusy(false);
      setFailed(found === null);
      setRows(found || []);
    }, 200);
    return () => {
      live = false;
      clearTimeout(t);
    };
  }, [open, term, doctype]);

  function choose(next: string | null) {
    onChange(next);
    setOpen(false);
    setTerm("");
  }

  return (
    <div ref={box} className="relative">
      <div className="flex items-center gap-1.5">
        <button
          id={id}
          type="button"
          disabled={disabled}
          onClick={() => setOpen((o) => !o)}
          className={cn(
            "flex h-9 w-full items-center justify-between gap-2 rounded-md border border-input bg-background px-3 text-left text-sm shadow-sm transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/30 disabled:cursor-not-allowed disabled:opacity-50",
            !value && "text-muted-foreground",
          )}
        >
          <span className="truncate">{value || `No ${doctype} chosen`}</span>
          <ChevronDown className="h-4 w-4 shrink-0 text-[var(--sd-quiet)]" />
        </button>
        {value && !disabled && (
          <button
            type="button"
            title="Clear"
            onClick={() => choose(null)}
            className="flex h-9 w-9 shrink-0 items-center justify-center rounded-md border border-input text-[var(--sd-quiet)] transition-colors hover:text-[var(--sd-ink)]"
          >
            <X className="h-4 w-4" />
          </button>
        )}
      </div>

      {open && (
        <div className="absolute z-30 mt-1 w-full rounded-[var(--sd-radius-lg)] border border-[var(--sd-line)] bg-[var(--sd-card)] p-1.5 shadow-[0_12px_32px_-16px_rgba(10,10,10,0.4)]">
          <Input
            autoFocus
            value={term}
            placeholder={`Search ${doctype}…`}
            onChange={(e) => setTerm(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Escape") setOpen(false);
            }}
          />
          <div className="mt-1.5 max-h-56 overflow-y-auto">
            {busy && (
              <div className="flex items-center gap-2 px-2 py-2 text-[12px] text-[var(--sd-muted)]">
                <Loader2 className="h-3.5 w-3.5 animate-spin" />
                Searching…
              </div>
            )}
            {!busy && failed && (
              <p className="px-2 py-2 text-[12px] text-[var(--sd-muted)]">
                Could not search {doctype}. You may not be permitted to list it — ask
                whoever set up your roles.
              </p>
            )}
            {!busy && !failed && rows.length === 0 && (
              <p className="px-2 py-2 text-[12px] text-[var(--sd-muted)]">
                No {doctype} matches that.
              </p>
            )}
            {!busy &&
              rows.map((row) => (
                <button
                  key={row.value}
                  type="button"
                  onClick={() => choose(row.value)}
                  className="flex w-full items-start gap-2 rounded-[var(--sd-radius)] px-2 py-1.5 text-left text-[13px] transition-colors hover:bg-[var(--sd-bg-soft)]"
                >
                  <Check
                    className={cn(
                      "mt-0.5 h-3.5 w-3.5 shrink-0",
                      row.value === value ? "text-[var(--sd-ink)]" : "opacity-0",
                    )}
                  />
                  <span className="min-w-0">
                    <span className="block truncate font-medium text-[var(--sd-ink)]">
                      {row.value}
                    </span>
                    {row.description && (
                      <span className="block truncate text-[11px] text-[var(--sd-quiet)]">
                        {row.description}
                      </span>
                    )}
                  </span>
                </button>
              ))}
          </div>
        </div>
      )}
    </div>
  );
}
