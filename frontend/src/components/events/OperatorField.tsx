import { useEffect, useId, useMemo, useRef, useState } from "react";
import { Check, Search } from "lucide-react";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { isError } from "@/lib/frappe";
import { searchEmployees, type EmployeeChoice } from "@/lib/people";
import { cn } from "@/lib/utils";

/**
 * Who is doing this, chosen from the staff list.
 *
 * This was a free-text box, which is not a picker: somebody typed "d" and the
 * save came back "Could not find Operator(technician): d" — a link field
 * refusing a value that was never going to be one. The operator is an Employee,
 * so the only sound control is one that can only produce an Employee.
 *
 * SEARCHED, NOT LISTED. There are 2,355 active employees; a dropdown of that
 * length is unusable and shipping it is 150 kB for somebody who was going to
 * type three letters. The list comes back as they type, matched on name or on
 * employee number — a man who knows his number should not have to remember how
 * somebody spelled him.
 *
 * Nothing is sent until a row is CHOSEN. Half-typed text is not a person, and
 * the old box let it reach the server as one.
 */
export function OperatorField({
  operator,
  onChange,
  className,
}: {
  operator: string;
  onChange: (next: string) => void;
  className?: string;
}) {
  // A page can carry two of these — the Herds page asks once for splitting a
  // herd and once for buying an animal in — so a fixed id would put the same
  // one on both and bind each label to whichever the browser saw first.
  const id = useId();
  const [term, setTerm] = useState("");
  const [rows, setRows] = useState<EmployeeChoice[]>([]);
  const [open, setOpen] = useState(false);
  const [chosen, setChosen] = useState<EmployeeChoice | null>(null);
  const box = useRef<HTMLDivElement | null>(null);

  // Debounced, because this searches 2,355 rows over a rural connection and a
  // request per keystroke would arrive out of order as well as too often.
  useEffect(() => {
    if (!open) return;
    const timer = setTimeout(() => {
      void searchEmployees(term).then((r) => {
        if (!isError(r)) setRows(r.employees);
      });
    }, 220);
    return () => clearTimeout(timer);
  }, [term, open]);

  useEffect(() => {
    function away(e: MouseEvent) {
      if (box.current && !box.current.contains(e.target as Node)) setOpen(false);
    }
    document.addEventListener("mousedown", away);
    return () => document.removeEventListener("mousedown", away);
  }, []);

  const shown = useMemo(() => rows.slice(0, 8), [rows]);

  return (
    <div ref={box} className={cn("relative flex flex-col gap-1.5", className)}>
      <Label htmlFor={id}>Who is recording this</Label>
      <div className="relative">
        <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-[var(--sd-quiet)]" />
        <Input
          id={id}
          value={open ? term : chosen?.label || operator}
          onChange={(e) => {
            setTerm(e.target.value);
            setOpen(true);
          }}
          onFocus={() => setOpen(true)}
          placeholder="Name or employee number…"
          autoComplete="off"
          role="combobox"
          aria-expanded={open}
          aria-controls={`${id}-list`}
          className="h-9 w-[240px] pl-9 text-[13px]"
        />
      </div>

      {open && (
        <ul
          id={`${id}-list`}
          role="listbox"
          className="absolute top-full z-20 mt-1 max-h-[240px] w-[280px] overflow-y-auto rounded-[var(--sd-radius-lg)] bg-[var(--sd-card)] p-1 shadow-[var(--sd-shadow-3)]"
        >
          {!shown.length ? (
            <li className="px-3 py-2 text-[12.5px] text-[var(--sd-muted)]">
              {term ? "Nobody by that name or number." : "Start typing a name."}
            </li>
          ) : (
            shown.map((e) => (
              <li key={e.value}>
                <button
                  type="button"
                  onClick={() => {
                    setChosen(e);
                    onChange(e.value);
                    setOpen(false);
                    setTerm("");
                  }}
                  className={cn(
                    "flex w-full items-center gap-2 rounded-[var(--sd-radius-lg)] px-3 py-2 text-left transition-colors",
                    "hover:bg-[var(--sd-bg-soft)]",
                    e.value === operator && "bg-[var(--sd-bg-soft)]",
                  )}
                >
                  <span className="flex min-w-0 flex-1 flex-col">
                    <span className="truncate text-[13px] text-[var(--sd-ink)]">{e.label}</span>
                    <span className="truncate text-[11px] text-[var(--sd-quiet)]">
                      {e.detail}
                    </span>
                  </span>
                  {e.value === operator && (
                    <Check className="h-3.5 w-3.5 shrink-0 text-[var(--sd-sev-moderate)]" />
                  )}
                </button>
              </li>
            ))
          )}
        </ul>
      )}

      <span className="text-[11px] text-[var(--sd-quiet)]">
        {operator
          ? "Remembered on this device; change it any time."
          : "Your login has no Employee linked, so an event cannot say who made it."}
      </span>
    </div>
  );
}
