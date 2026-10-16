import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { ToastProvider } from "@/components/Toast";

const photos = [
  { name: "f2", url: "/files/b.png", thumb: null, date: "2026-10-02 09:00:00", source: "Health case", ref_doctype: "Livestock Health Case", ref_name: "HC-1", caption: "swollen", uploaded_by: "Ann" },
  { name: "f1", url: "/files/a.png", thumb: null, date: "2026-09-01 09:00:00", source: "Birth", ref_doctype: "Livestock Event", ref_name: "EV-1", caption: "", uploaded_by: "Bob" },
];
const call = vi.fn(async (method: string) =>
  method.endsWith("animal_gallery")
    ? { ok: true, photos }
    : { error: "Health case HC-1 is Recovered; photos can only be added while it is open." },
);
vi.mock("@/lib/frappe", async () => {
  const actual = await vi.importActual<typeof import("@/lib/frappe")>("@/lib/frappe");
  return { ...actual, call, uploadFile: vi.fn(async () => ({ file_url: "/files/new.png" })) };
});

const { PhotoStrip } = await import("@/components/animals/PhotoStrip");
const draw = (ui: React.ReactElement) => render(<ToastProvider>{ui}</ToastProvider>);

describe("the photo strip", () => {
  it("lists her pictures with their source and date, and offers no upload unless asked", async () => {
    draw(<PhotoStrip animal="A1" />);
    await waitFor(() => expect(screen.getByText("Birth")).toBeTruthy());
    expect(screen.getByText("Health case")).toBeTruthy();
    expect(screen.getByText("2026-10-02")).toBeTruthy();
    expect(screen.queryByText("Add photo")).toBeNull();
  });

  it("narrows to one case and shows the server's refusal when the case has closed", async () => {
    draw(<PhotoStrip animal="A1" only="HC-1" upload={{ context: "health_case", ref: "HC-1" }} />);
    await waitFor(() => expect(screen.getByText("Health case")).toBeTruthy());
    expect(screen.queryByText("Birth")).toBeNull();
    const file = new File(["x"], "x.png", { type: "image/png" });
    fireEvent.change(screen.getByLabelText("Choose a photo"), { target: { files: [file] } });
    await waitFor(() => expect(screen.getByText(/photos can only be added while it is open/)).toBeTruthy());
  });
});
