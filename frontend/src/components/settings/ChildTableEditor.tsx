import { useEffect, useMemo, useState } from "react";
import { ArrowDown, ArrowUp, Plus, RotateCcw, Save, X } from "lucide-react";
import { LinkPicker } from "@/components/settings/LinkPicker";
import { useToast } from "@/components/Toast";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Picker } from "@/components/ui/picker";
import { isError } from "@/lib/frappe";
import {
  NUMERIC_FIELDTYPES,
  saveSettingsTable,
  type SettingsTable,
  type SettingsTableRow,
} from "@/lib/settings";

/**
 * A child table, edited here rather than on the desk.
 *
 * THE LISTS WERE READ-ONLY AND THE PAGE SENT YOU TO ERPNext. Which stores hold
 * feed, which concentrates are bought in, which herd a heifer climbs into next
 * — all farm decisions, made by the person running the farm, and "open ERPNext,
 * find Livestock Settings, scroll to the grid, add a row" is not a thing that
 * person does. So in practice each list was whatever it was on the day the site
 * was set up.
 *
 * ORDER IS DATA IN THESE GRIDS, which is why the old screen would not touch
 * them: the feed warehouse order decides which store a Work Order pulls from,
 * and the ladder decides where an animal goes next. So position is moved
 * explicitly, with arrows, and saved as the position — never inferred from the
 * order rows happen to arrive in.
 *
 * A LIST SAVES WHOLE. Adds, removals and moves are one edit to the person
 * making them, and the server replaces the list in one write — rows that
 * survive keep their names, so the modification log still shows who changed the
 * feed stores and when.
 */
export function ChildTableEditor({
  table,
  canWrite,
  onSaved,
}: {
  table: SettingsTable;
  canWrite: boolean;
  onSaved?: () => void;
}) {
  const [rows, setRows] = useState<SettingsTableRow[]>(table.rows);
  const [busy, setBusy] = useState(false);
  const toast = useToast();

  // The server's answer is the truth; a reload behind this component replaces
  // what is being edited rather than merging into it.
  useEffect(() => {
    setRows(table.rows);
  }, [table.rows]);

  const dirty = useMemo(
    () => JSON.stringify(strip(rows)) !== JSON.stringify(strip(table.rows)),
    [rows, table.rows],
  );

  const missing = rows.some((r) =>
    table.columns.some((c) => c.reqd && !String(r[c.fieldname] ?? "").trim()),
  );

  function set(i: number, fieldname: string, value: unknown) {
    setRows((s) => s.map((r, j) => (j === i ? { ...r, [fieldname]: value } : r)));
  }

  function move(i: number, by: number) {
    setRows((s) => {
      const next = [...s];
      const to = i + by;
      if (to < 0 || to >= next.length) return s;
      [next[i], next[to]] = [next[to], next[i]];
      return next;
    });
  }

  async function save() {
    setBusy(true);
    const r = await saveSettingsTable(table.fieldname, rows);
    setBusy(false);
    if (isError(r)) {
      toast(r.error, "error");
      return;
    }
    setRows(r.rows);
    toast(
      r.added || r.removed
        ? `${table.label}: ${r.added} added, ${r.removed} removed.`
        : `${table.label} saved.`,
    );
    onSaved?.();
  }

  return (
    <div className="flex flex-col gap-2">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h4 className="text-[13px] font-semibold text-[var(--sd-ink)]">{table.label}</h4>
        <span className="text-[11px] text-[var(--sd-quiet)]">
          {rows.length} row{rows.length === 1 ? "" : "s"}
        </span>
      </div>

      {table.description && (
        <p className="max-w-[64rem] text-[11px] leading-relaxed text-[var(--sd-quiet)]">
          {table.description}
        </p>
      )}

      <div className="overflow-x-auto rounded-[var(--sd-radius-lg)] border border-[var(--sd-line)]">
        <table className="w-full border-collapse text-[12.5px]">
          <thead>
            <tr className="text-left text-[11px] uppercase tracking-[0.06em] text-[var(--sd-quiet)]">
              <th className="w-10 px-2 py-2 text-right font-medium">#</th>
              {table.columns.map((c) => (
                <th key={c.fieldname} className="px-2 py-2 font-medium">
                  {c.label}
                </th>
              ))}
              <th className="w-24 px-2 py-2" />
            </tr>
          </thead>
          <tbody>
            {!rows.length && (
              <tr>
                <td
                  colSpan={table.columns.length + 2}
                  className="px-3 py-4 text-[12.5px] text-[var(--sd-quiet)]"
                >
                  Nothing on this list.
                </td>
              </tr>
            )}
            {rows.map((row, i) => (
              <tr key={String(row.name ?? `new-${i}`)} className="border-t border-[var(--sd-line)]">
                <td className="px-2 py-1.5 text-right tabular-nums text-[var(--sd-quiet)]">
                  {i + 1}
                </td>
                {table.columns.map((c) => (
                  <td key={c.fieldname} className="px-2 py-1.5">
                    <Cell
                      column={c}
                      value={row[c.fieldname]}
                      disabled={!canWrite}
                      onChange={(v) => set(i, c.fieldname, v)}
                    />
                  </td>
                ))}
                <td className="px-2 py-1.5">
                  <span className="flex items-center justify-end gap-0.5">
                    <IconButton
                      label="Move up"
                      disabled={!canWrite || i === 0}
                      onClick={() => move(i, -1)}
                    >
                      <ArrowUp className="h-3.5 w-3.5" />
                    </IconButton>
                    <IconButton
                      label="Move down"
                      disabled={!canWrite || i === rows.length - 1}
                      onClick={() => move(i, 1)}
                    >
                      <ArrowDown className="h-3.5 w-3.5" />
                    </IconButton>
                    <IconButton
                      label="Take this row off the list"
                      disabled={!canWrite}
                      onClick={() => setRows((s) => s.filter((_, j) => j !== i))}
                    >
                      <X className="h-3.5 w-3.5" />
                    </IconButton>
                  </span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {canWrite && (
        <div className="flex flex-wrap items-center gap-3">
          <button
            type="button"
            onClick={() => setRows((s) => [...s, {}])}
            className="inline-flex items-center gap-1.5 text-[12.5px] font-medium text-[var(--sd-muted)] transition-colors hover:text-[var(--sd-ink)]"
          >
            <Plus className="h-3.5 w-3.5" strokeWidth={2.5} />
            Add a row
          </button>
          <Button size="sm" onClick={save} disabled={!dirty || busy || missing}>
            <Save className="mr-1.5 h-3.5 w-3.5" />
            {busy ? "Saving…" : "Save this list"}
          </Button>
          {dirty && (
            <button
              type="button"
              onClick={() => setRows(table.rows)}
              className="inline-flex items-center gap-1.5 text-[12px] text-[var(--sd-muted)] transition-colors hover:text-[var(--sd-ink)]"
            >
              <RotateCcw className="h-3.5 w-3.5" />
              Undo
            </button>
          )}
          {missing && (
            <span className="text-[11.5px] text-[var(--sd-sev-critical)]">
              A row is missing something it needs.
            </span>
          )}
        </div>
      )}
    </div>
  );
}

/** Only the parts a save actually sends, for deciding whether anything changed. */
function strip(rows: SettingsTableRow[]) {
  return rows.map((r) => {
    const { idx: _idx, ...rest } = r;
    return rest;
  });
}

function Cell({
  column,
  value,
  disabled,
  onChange,
}: {
  column: SettingsTable["columns"][number];
  value: unknown;
  disabled?: boolean;
  onChange: (next: unknown) => void;
}) {
  if (column.fieldtype === "Link") {
    return (
      <LinkPicker
        doctype={column.options || ""}
        value={value == null ? null : String(value)}
        onChange={onChange}
        disabled={disabled}
      />
    );
  }
  if (column.fieldtype === "Select") {
    return (
      <Picker
        value={value == null ? "" : String(value)}
        onChange={onChange}
        options={(column.options || "").split("\n").filter(Boolean)}
        label={column.label}
        placeholder="—"
        disabled={disabled}
      />
    );
  }
  if (column.fieldtype === "Check") {
    return (
      <input
        type="checkbox"
        aria-label={column.label}
        checked={!!Number(value ?? 0)}
        disabled={disabled}
        onChange={(e) => onChange(e.target.checked ? 1 : 0)}
        className="h-4 w-4 accent-[var(--sd-ink)]"
      />
    );
  }
  const numeric = NUMERIC_FIELDTYPES.has(column.fieldtype);
  return (
    <Input
      aria-label={column.label}
      type={numeric ? "number" : "text"}
      step={column.fieldtype === "Int" ? 1 : "any"}
      value={value == null ? "" : String(value)}
      disabled={disabled}
      onChange={(e) => onChange(e.target.value)}
      className={numeric ? "w-28 text-right tabular-nums" : "min-w-[140px]"}
    />
  );
}

function IconButton({
  label,
  disabled,
  onClick,
  children,
}: {
  label: string;
  disabled?: boolean;
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      aria-label={label}
      title={label}
      disabled={disabled}
      onClick={onClick}
      className="rounded-[var(--sd-radius-sm)] p-1 text-[var(--sd-quiet)] transition-colors enabled:hover:bg-[var(--sd-bg-soft)] enabled:hover:text-[var(--sd-ink)] disabled:opacity-30"
    >
      {children}
    </button>
  );
}
