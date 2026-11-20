import metaJson from "../../../../upande_livestock/upande_livestock/doctype/livestock_settings/livestock_settings.json?raw";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

/**
 * The Settings page must show every Livestock Settings field. The expected list
 * is read from the doctype JSON itself, never typed here, so a field added to
 * the doctype (the insurance flow's, say) and not rendered fails this test.
 */

type Df = Record<string, any>;
const meta = JSON.parse(metaJson);
const byName: Record<string, Df> = Object.fromEntries(meta.fields.map((f: Df) => [f.fieldname, f]));
const LAYOUT = new Set(["Tab Break", "Section Break", "Column Break", "Fold"]);
const DISPLAY = new Set(["HTML", "Heading", "Button", "Image"]);
const TABLES = new Set(["Table", "Table MultiSelect"]);

/** The server's `layout()` and `tables()`, restated for the mock. */
function buildDoc() {
  const tabs: Df[] = [];
  let tab: Df | null = null;
  let section: Df | null = null;
  const tables: Df[] = [];
  const values: Record<string, unknown> = {};
  for (const name of meta.field_order as string[]) {
    const df = byName[name];
    if (df.fieldtype === "Tab Break") {
      tab = { fieldname: name, label: df.label, sections: [] };
      tabs.push(tab);
      section = null;
      continue;
    }
    if (df.fieldtype === "Section Break") {
      section = { fieldname: name, label: df.label, description: null, fields: [], tables: [] };
      tab!.sections.push(section);
      continue;
    }
    if (LAYOUT.has(df.fieldtype) || DISPLAY.has(df.fieldtype)) continue;
    if (TABLES.has(df.fieldtype)) {
      section!.tables.push(name);
      tables.push({ fieldname: name, fieldtype: df.fieldtype, label: df.label, description: null,
        doctype: df.options, columns: [], rows: [] });
      continue;
    }
    section!.fields.push({
      fieldname: name, label: df.label || name, fieldtype: df.fieldtype, options: df.options ?? null,
      description: df.description ?? null, default: df.default ?? null, depends_on: df.depends_on ?? null,
      reqd: !!df.reqd, read_only: !!df.read_only, hidden: !!df.hidden, zero: null, posts: false,
    });
    // Satisfy every depends_on so no field is legitimately hidden.
    values[name] = df.fieldtype === "Check" ? 1 : df.fieldtype === "Select" ? String(df.options).split("\n")[0] : null;
  }
  return { ok: true, doctype: "Livestock Settings", tabs, values, tables, can_write: true,
    writable: Object.keys(byName) };
}

const call = vi.fn(async (method?: string) => {
  if ((method || "").endsWith("livestock_settings.livestock_settings")) return buildDoc();
  return { ok: true, rules: [], item_groups: [], stores: [] };
});
vi.mock("@/lib/frappe", async () => {
  const actual = await vi.importActual<typeof import("@/lib/frappe")>("@/lib/frappe");
  return { ...actual, call, searchLink: async () => [] };
});
vi.mock("@/components/settings/LinkPicker", () => ({ LinkPicker: () => null }));
vi.mock("@/components/settings/EventsCard", () => ({ EventsCard: () => null }));
vi.mock("@/components/settings/AppreciationRun", () => ({ AppreciationRun: () => null }));

const { Settings } = await import("@/pages/Settings");
afterEach(cleanup);

describe("Settings page covers the whole doctype", () => {
  it("renders every non-layout, non-display, non-hidden field somewhere", async () => {
    const expected = (meta.field_order as string[]).filter((n) => {
      const df = byName[n];
      return !LAYOUT.has(df.fieldtype) && !DISPLAY.has(df.fieldtype) && !df.hidden;
    });
    render(<Settings />);
    await screen.findAllByRole("tab");
    const rendered = new Set<string>();
    for (const t of screen.getAllByRole("tab")) {
      fireEvent.mouseDown(t, { button: 0 });
      fireEvent.click(t);
      document.querySelectorAll("[data-fieldname]").forEach((el) =>
        rendered.add(el.getAttribute("data-fieldname")!),
      );
    }
    expect(expected.filter((n) => !rendered.has(n))).toEqual([]);
  });

  it("gives each requested area its own tab", async () => {
    render(<Settings />);
    const labels = (await screen.findAllByRole("tab")).map((t) => t.textContent);
    for (const wanted of ["Breeding", "Health", "Feeding", "Milking & Quality", "Stock",
      "Assets & Appreciation", "Accounts & Insurance", "Bulls", "Notifications", "Mobile"]) {
      expect(labels).toContain(wanted);
    }
  });

  it("every tab in the doctype holds at least one field", () => {
    for (const t of buildDoc().tabs) {
      expect(t.sections.some((s: Df) => s.fields.length || s.tables.length), t.label).toBe(true);
    }
  });

  it("waits for the page", async () => {
    render(<Settings />);
    await waitFor(() => expect(screen.getAllByRole("tab").length).toBeGreaterThan(5));
  });
});
