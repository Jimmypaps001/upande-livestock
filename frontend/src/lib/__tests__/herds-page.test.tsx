import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ToastProvider } from "@/components/Toast";
import { TooltipProvider } from "@/components/ui/tooltip";

/**
 * Composing a herd, rendered.
 *
 * The behaviour worth pinning: an empty herd is allowed (a pen you are about
 * to fill is still a pen), and a bought animal is announced by the FARM's
 * number rather than the seller's tag.
 */

const animals = [
  {
    name: "A039/26",
    burn_name: "APIJA",
    sex: "Female" as const,
    current_herd: "Lactating group 1",
    breed: "Ayrshire",
    date_of_birth: "2022-04-11",
    image: null,
  },
  {
    name: "A101/23",
    burn_name: "SITA",
    sex: "Female" as const,
    current_herd: "INCALF HEIFERS",
    breed: "Ayrshire",
    date_of_birth: "2023-02-02",
    image: null,
  },
];

const call = vi.fn(async (method?: string) => {
  const m = method || "";
  if (m.includes("employee_options")) {
    // No Employee linked to this login, so the screens ask — and the answer
    // has to be CHOSEN from the staff list, not typed.
    return {
      ok: true,
      mine: null,
      query: "",
      more: false,
      employees: [{ value: "HR-EMP-1", label: "JOSIAH KIPTOO", detail: "HR-EMP-1 · Herdsman" }],
    };
  }
  if (m.endsWith("create_herd")) {
    return { ok: true, herd: "Lactating group 4", heads: 1, moved: [], emptied_from: ["Lactating group 1"], ration: null };
  }
  if (m.endsWith("buy_in_animal")) {
    return {
      ok: true, animal: "A057/26", name: "NDIZI", herd: "INCALF HEIFERS",
      heads: 11, asset: "ACC-ASS-1" as string | null, purchase_value: 120000,
    };
  }
  return { ok: true, animals, cases: [], flagged: [], recent: [], open_claims: [], counts: {} };
});

vi.mock("@/lib/frappe", async () => {
  const actual = await vi.importActual<typeof import("@/lib/frappe")>("@/lib/frappe");
  return { ...actual, call };
});

const { Herds } = await import("@/pages/Herds");

function draw() {
  return render(
    <TooltipProvider>
      <ToastProvider>
      <Herds />
    </ToastProvider>
    </TooltipProvider>,
  );
}

/** Choose an operator from the searchable staff list. */
async function pickOperator(which = 0) {
  const fields = await screen.findAllByLabelText("Who is recording this");
  fireEvent.focus(fields[which]);
  const row = await screen.findByText("JOSIAH KIPTOO");
  fireEvent.click(row);
}

describe("the herds page", () => {
  beforeEach(() => call.mockClear());

  it("lists the animals that could be split off", async () => {
    draw();
    await waitFor(() => expect(screen.getByText("APIJA")).toBeTruthy());
  });

  it("offers to create an empty herd, because a pen you are about to fill is a pen", async () => {
    draw();
    await waitFor(() => expect(screen.getByText("APIJA")).toBeTruthy());
    fireEvent.change(screen.getByLabelText(/What the herd is called/), {
      target: { value: "Lactating group 4" },
    });
    expect(screen.getByRole("button", { name: /Create it empty/ })).toBeTruthy();
  });

  it("counts the animals picked and lets one be taken back out", async () => {
    draw();
    await waitFor(() => expect(screen.getByText("APIJA")).toBeTruthy());
    fireEvent.click(screen.getByText("APIJA"));
    await waitFor(() => expect(screen.getByText("1 picked")).toBeTruthy());
    fireEvent.click(screen.getByText("A039/26", { selector: "button" }));
    await waitFor(() => expect(screen.queryByText("1 picked")).toBeNull());
  });

  it("announces a bought animal by the farm's number, not the seller's tag", async () => {
    draw();
    await waitFor(() => expect(screen.getByText("APIJA")).toBeTruthy());
    // No Employee is linked to this login, so the page asks who is doing it.
    // Chosen from the list rather than typed: half-typed text is not a person,
    // and the old box let it reach the server as one.
    await pickOperator(1);
    fireEvent.change(screen.getByLabelText(/Their tag for her/), {
      target: { value: "KD-441" },
    });
    fireEvent.click(screen.getByRole("button", { name: /Bring her onto the farm/ }));
    await waitFor(() => expect(screen.getByText(/on the farm as A057\/26/)).toBeTruthy());
    expect(screen.queryByText(/on the farm as KD-441/)).toBeNull();
  });

  it("says plainly when an animal is not put on the books", async () => {
    // Keyed on the method, not on call order: the operator lookup is a call
    // too, and a `mockImplementationOnce` chain silently handed it somebody
    // else's answer.
    call.mockImplementation(async (method?: string) => {
      const m = method || "";
      if (m.includes("employee_options")) {
        return {
          ok: true, mine: null, query: "", more: false,
          employees: [{ value: "HR-EMP-1", label: "JOSIAH KIPTOO", detail: "HR-EMP-1" }],
        };
      }
      if (m.includes("buy_in_animal")) {
        return {
          ok: true, animal: "A058/26", name: "ZAWADI", herd: "INCALF HEIFERS",
          heads: 12, asset: null as string | null, purchase_value: 0,
        };
      }
      return { ok: true, animals, cases: [], flagged: [], recent: [], open_claims: [], counts: {} };
    });
    draw();
    await waitFor(() => expect(screen.getByText("APIJA")).toBeTruthy());
    await pickOperator(1);
    fireEvent.click(screen.getByRole("button", { name: /Bring her onto the farm/ }));
    await waitFor(() => expect(screen.getByText(/not capitalised/)).toBeTruthy());
  });
});
