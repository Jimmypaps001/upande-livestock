import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it } from "vitest";
import { AnimalSearch } from "@/components/animals/AnimalSearch";
import { matchesSex, type AnimalSummary } from "@/lib/animals";

const mk = (id: string, name: string, sex: "Female" | "Male", herd = "Finishing 1"): AnimalSummary => ({
  id, name, sex, herd, breed: "Boran", bornOn: "2023-01-01", status: "Active", stage: "open", photo: null,
});

const animals = [
  mk("A001/22", "ADA", "Female"),
  mk("A002/22", "ABBY", "Female", "Steamers"),
  mk("B001/22", "BRUNO", "Male"),
  mk("B002/22", "BOLT", "Male", "Steamers"),
  mk("B003/22", "BEN", "Male"),
];

const chip = (label: string) => screen.getByRole("button", { name: new RegExp(`^${label}`) });
const shown = () => screen.queryAllByText(/^[A-Z]\d{3}\/22$/).map((e) => e.textContent);

beforeEach(() => window.localStorage.clear());

describe("matchesSex", () => {
  it("All keeps everyone; Cows is female; Bulls is every male", () => {
    expect(animals.filter((a) => matchesSex(a, "all"))).toHaveLength(5);
    expect(animals.filter((a) => matchesSex(a, "cows")).map((a) => a.id)).toEqual(["A001/22", "A002/22"]);
    expect(animals.filter((a) => matchesSex(a, "bulls")).map((a) => a.id)).toEqual(["B001/22", "B002/22", "B003/22"]);
  });
});

describe("sex chips on the animal search", () => {
  it("show counts and narrow the list", () => {
    render(<AnimalSearch animals={animals} selectedId={null} onSelect={() => {}} />);
    expect(chip("All").textContent).toContain("5");
    expect(chip("Cows").textContent).toContain("2");
    expect(chip("Bulls").textContent).toContain("3");
    fireEvent.click(chip("Cows"));
    expect(shown()).toEqual(["A001/22", "A002/22"]);
    fireEvent.click(chip("Bulls"));
    expect(shown()).toEqual(["B001/22", "B002/22", "B003/22"]);
    fireEvent.click(chip("All"));
    expect(shown()).toHaveLength(5);
  });

  it("combines with the text search, and the counts follow the search", () => {
    render(<AnimalSearch animals={animals} selectedId={null} onSelect={() => {}} />);
    fireEvent.change(screen.getByLabelText("Find an animal"), { target: { value: "steamers" } });
    expect(chip("Cows").textContent).toContain("1");
    expect(chip("Bulls").textContent).toContain("1");
    fireEvent.click(chip("Bulls"));
    expect(shown()).toEqual(["B002/22"]);
  });

  it("remembers the choice for next time", () => {
    const first = render(<AnimalSearch animals={animals} selectedId={null} onSelect={() => {}} />);
    fireEvent.click(chip("Cows"));
    first.unmount();
    render(<AnimalSearch animals={animals} selectedId={null} onSelect={() => {}} />);
    expect(chip("Cows").getAttribute("aria-pressed")).toBe("true");
    expect(shown()).toEqual(["A001/22", "A002/22"]);
  });
});
