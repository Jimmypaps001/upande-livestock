import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import {
  Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Notice } from "@/components/feeding/Notice";
import { isError } from "@/lib/frappe";
import { searchEmployees, type EmployeeChoice } from "@/lib/people";
import { addVet, vetProblem, type NewVet } from "@/lib/vets";

const EMPTY: NewVet = { vet_type: "External" };
const SELECT = "h-9 rounded-md border border-input bg-background px-3 text-sm";

/**
 * Add a vet without leaving the desk. The same fields and rules as the ERP form:
 * an internal vet is an Employee (name, phone and login come from them); an
 * external vet needs a name, a phone and a Kenya Veterinary Board registration
 * number. The server's controller is the authority and its words are shown as sent.
 */
export function AddVetDialog({
  open,
  onOpenChange,
  onAdded,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onAdded?: (vet: { value: string; label: string }) => void;
}) {
  const [v, setV] = useState<NewVet>(EMPTY);
  const [term, setTerm] = useState("");
  const [employees, setEmployees] = useState<EmployeeChoice[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (open) {
      setV(EMPTY);
      setTerm("");
      setError(null);
    }
  }, [open]);

  useEffect(() => {
    if (!open || v.vet_type !== "Internal") return;
    let live = true;
    const t = window.setTimeout(() => {
      void searchEmployees(term).then((r) => {
        if (live && !isError(r)) setEmployees(r.employees ?? []);
      });
    }, term ? 250 : 0);
    return () => {
      live = false;
      window.clearTimeout(t);
    };
  }, [open, v.vet_type, term]);

  const set = (patch: Partial<NewVet>) => setV((cur) => ({ ...cur, ...patch }));
  const external = v.vet_type === "External";

  async function submit() {
    const problem = vetProblem(v);
    if (problem) {
      setError(problem);
      return;
    }
    setBusy(true);
    setError(null);
    const r = await addVet(v);
    setBusy(false);
    if (isError(r)) {
      setError(r.error);
      return;
    }
    onAdded?.(r.vet);
    onOpenChange(false);
  }

  const field = (id: string, label: string, key: keyof NewVet, props: React.ComponentProps<typeof Input> = {}) => (
    <div className="grid gap-1">
      <Label htmlFor={id}>{label}</Label>
      <Input id={id} value={(v[key] as string) ?? ""} onChange={(e) => set({ [key]: e.target.value })} {...props} />
    </div>
  );

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[90vh] max-w-lg overflow-y-auto">
        <DialogHeader>
          <DialogTitle>Add vet</DialogTitle>
          <DialogDescription>
            Internal: a farm employee, paid through payroll. External: a contracted or visiting practitioner.
          </DialogDescription>
        </DialogHeader>
        {error && <Notice tone="error">{error}</Notice>}
        <div className="grid gap-3">
          <div className="grid gap-1">
            <Label htmlFor="vet-type">Type</Label>
            <select
              id="vet-type"
              className={SELECT}
              value={v.vet_type}
              onChange={(e) => setV({ vet_type: e.target.value as NewVet["vet_type"] })}
            >
              <option value="Internal">Internal</option>
              <option value="External">External</option>
            </select>
          </div>

          {!external && (
            <div className="grid gap-1">
              <Label htmlFor="vet-employee-find">Employee</Label>
              <Input
                id="vet-employee-find"
                placeholder="Search by name or number"
                value={term}
                onChange={(e) => setTerm(e.target.value)}
              />
              <select
                id="vet-employee"
                aria-label="Employee"
                className={SELECT}
                value={v.employee ?? ""}
                onChange={(e) => set({ employee: e.target.value })}
              >
                <option value="">Choose an employee</option>
                {employees.map((e) => (
                  <option key={e.value} value={e.value}>
                    {e.label} · {e.detail}
                  </option>
                ))}
              </select>
            </div>
          )}

          {external && (
            <>
              {field("vet-name", "Vet name", "vet_name")}
              {field("vet-phone", "Phone", "phone", { type: "tel" })}
              {field("vet-email", "Email", "email", { type: "email" })}
              {field("vet-reg", "Kenya Veterinary Board Registration No.", "registration_number")}
              {field("vet-practice", "Practice / Clinic", "practice_name")}
              {field("vet-qualification", "Qualification", "qualification")}
              {field("vet-licence", "Licence expiry", "licence_expiry", { type: "date" })}
              {field("vet-supplier", "Supplier (where fees are payable)", "supplier")}
            </>
          )}
        </div>
        <div className="flex justify-end gap-2">
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button disabled={busy} onClick={() => void submit()}>
            {busy ? "Saving…" : "Save vet"}
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}
