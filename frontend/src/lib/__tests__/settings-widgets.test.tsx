import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

const call = vi.fn(async () => ({ ok: true, changed: {}, unchanged: [], values: {} }));
vi.mock("@/lib/frappe", async () => {
  const actual = await vi.importActual<typeof import("@/lib/frappe")>("@/lib/frappe");
  return { ...actual, call };
});
vi.mock("@/components/settings/LinkPicker", () => ({ LinkPicker: () => null }));

const { SettingField } = await import("@/components/settings/SettingField");
const { ChildTableEditor } = await import("@/components/settings/ChildTableEditor");
const { evalCondition, isEditable, isMandatory, isVisible, saveLivestockSettings } = await import("@/lib/settings");
import type { SettingsField } from "@/lib/settings";

const f = (fieldtype: string, extra: Partial<SettingsField> = {}): SettingsField => ({
  fieldname: "x", label: "Thing", fieldtype, options: null, description: "Some help.", default: null,
  depends_on: null, reqd: false, zero: null, posts: false, ...extra,
});

describe("widgets by fieldtype", () => {
  it.each([
    ["Date", "date"],
    ["Time", "time"],
    ["Datetime", "datetime-local"],
    ["Data", "text"],
    ["Currency", "number"],
  ])("%s is a %s input", (fieldtype, type) => {
    render(<SettingField field={f(fieldtype)} stored={null} value={null} onChange={() => {}} />);
    expect((screen.getByLabelText(/Thing/) as HTMLInputElement).type).toBe(type);
  });

  it("Small Text is a textarea and reports edits", () => {
    const onChange = vi.fn();
    render(<SettingField field={f("Small Text")} stored="a" value="a" onChange={onChange} />);
    const box = screen.getByLabelText(/Thing/);
    expect(box.tagName).toBe("TEXTAREA");
    fireEvent.change(box, { target: { value: "b" } });
    expect(onChange).toHaveBeenCalledWith("b");
  });

  it("shows the description as help and a required mark", () => {
    render(<SettingField field={f("Data", { reqd: true })} stored={null} value="" onChange={() => {}} />);
    expect(screen.getByText("Some help.")).toBeTruthy();
    expect(screen.getByLabelText("required")).toBeTruthy();
  });

  it("a read-only field is disabled", () => {
    render(<SettingField field={f("Data", { read_only: true })} stored="v" value="v" onChange={() => {}} />);
    expect((screen.getByLabelText(/Thing/) as HTMLInputElement).disabled).toBe(true);
  });
});

describe("conditions and permissions", () => {
  const v = { a: 1, mode: "At milking", b: 0 };
  it("reads bare and eval depends_on", () => {
    expect(evalCondition("a", v, {})).toBe(true);
    expect(evalCondition("b", v, {})).toBe(false);
    expect(evalCondition("eval:doc.mode=='At milking'", v, {})).toBe(true);
    expect(evalCondition("eval:doc.mode=='Afterwards'", v, {})).toBe(false);
    expect(evalCondition("eval:doc.mode!='Afterwards' && doc.a", v, {})).toBe(true);
    expect(evalCondition("eval:!doc.a || doc.b", v, {})).toBe(false);
    expect(evalCondition("eval:some(weird)", v, {})).toBeNull();
  });
  it("draft overrides stored, hidden hides, unreadable shows", () => {
    expect(isVisible({ depends_on: "a" }, v, { a: 0 })).toBe(false);
    expect(isVisible({ depends_on: "eval:weird()" }, v, {})).toBe(true);
    expect(isVisible({ depends_on: null, hidden: true }, v, {})).toBe(false);
  });
  it("mandatory_depends_on and per-field write grants", () => {
    expect(isMandatory({ reqd: false, mandatory_depends_on: "a" }, v, {})).toBe(true);
    const doc = { can_write: false, writable: ["acct"] };
    expect(isEditable({ fieldname: "acct" }, doc, v, {})).toBe(true);
    expect(isEditable({ fieldname: "other" }, doc, v, {})).toBe(false);
    expect(isEditable({ fieldname: "acct", read_only: true }, doc, v, {})).toBe(false);
  });
});

describe("tables and the one save", () => {
  const table = {
    fieldname: "t", label: "Things", fieldtype: "Table", description: null, doctype: "Child",
    columns: [{ ...f("Data"), fieldname: "n", label: "Name" }],
    rows: [{ name: "r1", n: "a" }],
  };

  it("adds and removes rows through onChange", () => {
    const onChange = vi.fn();
    render(<ChildTableEditor table={table} rows={table.rows} onChange={onChange} canWrite />);
    fireEvent.click(screen.getByText("Add a row"));
    expect(onChange).toHaveBeenLastCalledWith([{ name: "r1", n: "a" }, {}]);
    fireEvent.click(screen.getByLabelText("Take this row off the list"));
    expect(onChange).toHaveBeenLastCalledWith([]);
  });

  it("sends scalars and lists in one call", async () => {
    await saveLivestockSettings({ a: 1 }, { t: [{ n: "b" }] });
    expect(call).toHaveBeenCalledTimes(1);
    expect(call).toHaveBeenCalledWith(expect.stringMatching(/save_livestock_settings$/), {
      payload: { a: 1 }, tables: { t: [{ n: "b" }] },
    });
  });
});
