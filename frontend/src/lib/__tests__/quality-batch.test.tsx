import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

/** Record a quality batch: the form, its live preview, and the history table. */

const LIM = { aflatoxin_limit_ppt: 50, antibiotics_fail: true, resazurin_min_score: 4 };
const state = vi.hoisted(() => ({ sent: [] as Record<string, unknown>[] }));

const row = (over: Record<string, unknown> = {}) => ({
  name: "MQT-2026-00001", sample_date: "2026-10-28", shift: "", sample_type: "Bottle sample", buyer: "BU Westwood Milk",
  milk_recording: null, quantity_l: 0.5, receiving_temp_c: 12.1, ph: 6.62, tta: 7.8, snf_percent: 8.8,
  freezing_point: -0.548, specific_gravity: 1.03, protein_percent: 3.2, butterfat_percent: 2.9,
  resazurin_score: "0", resazurin_result: "Fail", antibiotics: "Negative", hydrogen_peroxide: "Nil", frothing: "Pass",
  aflatoxin_ppt: 67, sensory_score: "+1", sensory_note: "", overall_result: "Fail", failed_tests: "Resazurin, Aflatoxin M1",
  bulk_scc: 250, scc_over_ceiling: true, aflatoxin_over_limit: true, remarks: "", lab_slip: null, recorded_by: "a@b.c",
  checks: { resazurin: "fail", antibiotics: "pass", hydrogen_peroxide: "pass", frothing: "pass", aflatoxin: "fail" },
  ...over,
});

const BATCHES = [
  { key: "2026-11-19|Morning", date: "2026-11-19", shift: "Morning", total_kg: 300, herds: ["A", "B"], tested: false, pending: true,
    milk_recording: "MR-1", recordings: [{ name: "MR-1", herd: "A", net_yield_kg: 200 }, { name: "MR-2", herd: "B", net_yield_kg: 100 }] },
  { key: "2026-11-18|Evening", date: "2026-11-18", shift: "Evening", total_kg: 90, herds: ["A"], tested: true, pending: false,
    milk_recording: "MR-3", recordings: [{ name: "MR-3", herd: "A", net_yield_kg: 90 }] },
];

const call = vi.fn(async (method?: string, args?: { payload?: Record<string, unknown> }) => {
  if (method?.endsWith("quality_test_options")) {
    return { ok: true, date: "2026-11-20", default_buyer: "BU Westwood Milk", sample_types: ["Bottle sample", "Tanker", "Can"],
      shifts: ["Morning", "Afternoon", "Evening"], limits: LIM, scc_ceiling: 200, recordings: [], can_write: true };
  }
  if (method?.endsWith("milk_batches")) return { ok: true, from: "x", to: "y", batches: BATCHES };
  if (method?.endsWith("quality_tests")) return { ok: true, tests: [row()], total: 1, limits: LIM, can_write: true };
  if (method?.endsWith("record_quality_test")) {
    state.sent.push(args?.payload ?? {});
    return { ok: true, name: "MQT-2026-00002", duplicate: false, overall_result: "Fail", failed_tests: "Aflatoxin M1", test: row() };
  }
  return { ok: true };
});

vi.mock("@/lib/frappe", async () => {
  const actual = await vi.importActual<typeof import("@/lib/frappe")>("@/lib/frappe");
  return { ...actual, call };
});

const { emptyForm, formProblem, payloadFrom, previewChecks, previewOverall } = await import("@/lib/quality");
const { QualityBatch } = await import("@/components/quality/QualityBatch");
const { ToastProvider } = await import("@/components/Toast");

const { TooltipProvider } = await import("@/components/ui/tooltip");
const draw = () => render(<TooltipProvider><ToastProvider><QualityBatch /></ToastProvider></TooltipProvider>);

beforeEach(() => {
  state.sent = [];
  call.mockClear();
});

describe("quality batch rules", () => {
  it("previews each deciding test and the overall result", () => {
    const f = { ...emptyForm("2026-10-28"), resazurin_score: "6", antibiotics: "Negative", aflatoxin_ppt: "67" };
    const c = previewChecks(f, LIM);
    expect(c.resazurin).toBe("pass");
    expect(c.aflatoxin).toBe("fail");
    expect(previewOverall(c)).toBe("Fail");
    expect(previewOverall(previewChecks(emptyForm("x"), LIM))).toBe("Not assessed");
  });

  it("an explicit resazurin result beats the score; the limit is configurable", () => {
    const f = { ...emptyForm("x"), resazurin_score: "0", resazurin_result: "Pass", aflatoxin_ppt: "60" };
    const c = previewChecks(f, { ...LIM, aflatoxin_limit_ppt: 75 });
    expect(c.resazurin).toBe("pass");
    expect(c.aflatoxin).toBe("pass");
  });

  it("refuses an empty sheet and a sensory score that is not a whole number", () => {
    expect(formProblem(emptyForm("x"))).toMatch(/at least one result/);
    expect(formProblem({ ...emptyForm("x"), sensory_score: "1.5" })).toMatch(/whole number/);
    expect(formProblem({ ...emptyForm("x"), sensory_score: "-1" })).toBeNull();
  });

  it("sends numbers with a comma decimal as numbers and leaves blanks out", () => {
    const p = payloadFrom({ ...emptyForm("2026-10-28"), ph: "6,62", freezing_point: "-0.548", frothing: "Pass" });
    expect(p).toMatchObject({ ph: 6.62, freezing_point: -0.548, frothing: "Pass", sample_type: "Bottle sample" });
    expect("tta" in p).toBe(false);
  });
});

describe("Record quality batch", () => {
  it("lists past batches with a chip per test and the overall result", async () => {
    draw();
    const history = await screen.findByLabelText("Quality batch history");
    expect(within(history).getByText("Resazurin: Fail")).toBeTruthy();
    expect(within(history).getByText("Frothing: Pass")).toBeTruthy();
    expect(within(history).getByText("Fail")).toBeTruthy();
  });

  it("shows the merged result: SCC against the ceiling beside the chips", async () => {
    draw();
    const history = await screen.findByLabelText("Quality batch history");
    expect(history.querySelector("[data-over-ceiling=true]")?.textContent).toContain("250");
    expect(within(history).getByText("over ceiling")).toBeTruthy();
  });

  it("lists the batches with the awaiting one first and no separate File-the-result form", async () => {
    draw();
    const step = await screen.findByLabelText("Step 1: pick the batch");
    const items = within(step).getAllByRole("button");
    expect(items[0].textContent).toContain("2026-11-19");
    expect(within(step).getByText("Awaiting result")).toBeTruthy();
    expect(screen.queryByText("File the result")).toBeNull();
  });

  it("warns when the bulk SCC is over the ceiling and sends it with the whole batch", async () => {
    draw();
    await screen.findByLabelText("Step 1: pick the batch");
    fireEvent.change(screen.getByLabelText("Bulk SCC (cells/ml × 1000)"), { target: { value: "250" } });
    expect(await screen.findByText(/above the farm's ceiling of 200/)).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Record batch" }));
    await waitFor(() => expect(state.sent).toHaveLength(1));
    expect(state.sent[0]).toMatchObject({
      bulk_scc: 250, sample_date: "2026-11-19", shift: "Morning", milk_recording: "MR-1", recordings: ["MR-1", "MR-2"],
    });
  });

  it("blocks an empty sheet without calling the server", async () => {
    draw();
    await screen.findByLabelText("Record quality batch");
    fireEvent.click(screen.getByRole("button", { name: "Record batch" }));
    expect(await screen.findByText("Enter at least one result.")).toBeTruthy();
    expect(state.sent).toHaveLength(0);
  });

  it("previews Fail as aflatoxin is typed, then records the sheet with the default buyer", async () => {
    draw();
    await screen.findByLabelText("Record quality batch");
    await screen.findByLabelText("Step 1: pick the batch");
    fireEvent.change(screen.getByLabelText("Aflatoxin M1 (ppt)"), { target: { value: "67" } });
    fireEvent.change(screen.getByLabelText("pH"), { target: { value: "6,62" } });
    fireEvent.change(screen.getByLabelText("Freezing point (°C)"), { target: { value: "-0.548" } });
    expect(screen.getByText("Overall: Fail")).toBeTruthy();
    await waitFor(() => expect((screen.getByLabelText("Buyer / lab") as HTMLInputElement).value).toBe("BU Westwood Milk"));
    fireEvent.click(screen.getByRole("button", { name: "Record batch" }));
    await waitFor(() => expect(state.sent).toHaveLength(1));
    expect(state.sent[0]).toMatchObject({ aflatoxin_ppt: 67, ph: 6.62, freezing_point: -0.548, buyer: "BU Westwood Milk" });
    expect(String(state.sent[0].client_ref)).toMatch(/^desk_/);
  });
});
