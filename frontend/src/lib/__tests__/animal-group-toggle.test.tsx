import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it } from "vitest";
import { AnimalSearch } from "@/components/animals/AnimalSearch";
import type { AnimalSummary } from "@/lib/animals";

const mk = (id: string, herd: string): AnimalSummary => ({
  id, name: `Cow ${id}`, sex: "Female", herd, breed: null, bornOn: "2023-01-01", status: "Active", stage: "open", photo: null,
});
const animals = [mk("A1", "Steamers"), mk("A2", "Steamers"), mk("A3", "Calves")];

const grouped = () => {
  render(<AnimalSearch animals={animals} selectedId={null} onSelect={() => {}} />);
  fireEvent.click(screen.getByLabelText("Group the list"));
  fireEvent.click(screen.getByRole("option", { name: "By herd" }));
};
const rows = () => screen.queryAllByText(/^A\d$/).length;

describe("Expand all / Collapse all on the grouped list", () => {
  beforeEach(() => window.localStorage.clear());

  it("is absent on a flat list", () => {
    render(<AnimalSearch animals={animals} selectedId={null} onSelect={() => {}} />);
    expect(screen.queryByLabelText(/all$/)).toBeNull();
  });

  it("collapses every herd, then expands them again", () => {
    grouped();
    expect(rows()).toBe(3);
    fireEvent.click(screen.getByLabelText("Collapse all"));
    expect(rows()).toBe(0);
    fireEvent.click(screen.getByLabelText("Expand all"));
    expect(rows()).toBe(3);
  });

  it("offers Expand all as soon as one herd is shut", () => {
    grouped();
    fireEvent.click(screen.getByRole("button", { name: /^Calves\s*1/ }));
    expect(screen.getByLabelText("Expand all")).toBeTruthy();
  });
});
