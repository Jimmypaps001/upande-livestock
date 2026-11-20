import { useEffect, useState } from "react";
import { ChevronDown, Plus, Search } from "lucide-react";
import { Notice } from "@/components/feeding/Notice";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { can } from "@/lib/can";
import { buyerSearch, createBuyer, type Buyer } from "@/lib/culling";
import { isError } from "@/lib/frappe";
import { cn } from "@/lib/utils";

const PIN = /^[AP]\d{9}[A-Z]$/i;

/**
 * Choose the Customer a culled animal is sold to.
 *
 * Searches the server as you type (there are hundreds of Customers, most of them
 * flower buyers), by name, phone or KRA PIN. "New buyer" is the manager's: the
 * same signature that approves the sale may add the person it is sold to.
 */
export function BuyerPicker({
  value,
  label,
  onChange,
}: {
  value: string;
  label?: string;
  onChange: (customer: string) => void;
}) {
  const [open, setOpen] = useState(false);
  const [term, setTerm] = useState("");
  const [rows, setRows] = useState<Buyer[]>([]);
  const [adding, setAdding] = useState(false);
  const [failure, setFailure] = useState<string | null>(null);

  useEffect(() => {
    if (!open) return;
    let live = true;
    const t = setTimeout(async () => {
      const r = await buyerSearch(term.trim());
      if (!live) return;
      if (isError(r)) return setFailure(r.error);
      setFailure(null);
      setRows(r.buyers ?? []);
    }, 200);
    return () => {
      live = false;
      clearTimeout(t);
    };
  }, [open, term]);

  function pick(name: string) {
    onChange(name);
    setOpen(false);
    setTerm("");
  }

  return (
    <div className="flex gap-2">
      <Popover open={open} onOpenChange={setOpen}>
        <PopoverTrigger asChild>
          <Button
            type="button"
            variant="outline"
            aria-label={label ?? "Buyer"}
            className="h-9 min-w-0 flex-1 justify-between gap-2 px-3 font-normal"
          >
            <span className={cn("truncate text-left", !value && "text-[var(--sd-quiet)]")}>
              {value || "Choose the buyer"}
            </span>
            <ChevronDown className="h-3.5 w-3.5 shrink-0 text-[var(--sd-quiet)]" />
          </Button>
        </PopoverTrigger>
        <PopoverContent className="w-[min(28rem,90vw)] p-2">
          <div className="flex items-center gap-2 px-1 pb-2">
            <Search className="h-3.5 w-3.5 text-[var(--sd-quiet)]" />
            <Input
              autoFocus
              value={term}
              placeholder="Name, phone or KRA PIN"
              aria-label="Search buyers"
              className="h-8"
              onChange={(e) => setTerm(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && rows[0]) {
                  e.preventDefault();
                  pick(rows[0].name);
                }
              }}
            />
          </div>
          {failure && <p className="px-2 py-1 text-[12px] text-[var(--sd-sev-critical)]">{failure}</p>}
          <ul className="max-h-64 overflow-y-auto">
            {rows.map((b) => (
              <li key={b.name}>
                <button
                  type="button"
                  className="flex w-full flex-col rounded-md px-2 py-1.5 text-left hover:bg-[var(--sd-bg-soft)]"
                  onClick={() => pick(b.name)}
                >
                  <span className="text-[13px] text-[var(--sd-ink)]">{b.customer_name || b.name}</span>
                  <span className="text-[11.5px] text-[var(--sd-muted)]">
                    {[b.mobile_no, b.tax_id, b.payment_terms].filter(Boolean).join(" · ") || "No phone or PIN on file"}
                  </span>
                </button>
              </li>
            ))}
            {!rows.length && !failure && <li className="px-2 py-2 text-[12px] text-[var(--sd-muted)]">No buyer matches.</li>}
          </ul>
        </PopoverContent>
      </Popover>
      {can.flag("cull_manager") && (
        <Button type="button" variant="outline" className="h-9 gap-1.5" onClick={() => setAdding(true)}>
          <Plus className="h-3.5 w-3.5" /> New buyer
        </Button>
      )}
      <NewBuyerDialog
        open={adding}
        initialName={term}
        onOpenChange={setAdding}
        onCreated={(name) => {
          setAdding(false);
          pick(name);
        }}
      />
    </div>
  );
}

function NewBuyerDialog({
  open,
  initialName,
  onOpenChange,
  onCreated,
}: {
  open: boolean;
  initialName: string;
  onOpenChange: (open: boolean) => void;
  onCreated: (name: string) => void;
}) {
  const [name, setName] = useState("");
  const [phone, setPhone] = useState("");
  const [pin, setPin] = useState("");
  const [email, setEmail] = useState("");
  const [kind, setKind] = useState("Individual");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!open) return;
    setName(initialName);
    setPhone("");
    setPin("");
    setEmail("");
    setKind("Individual");
    setError(null);
  }, [open, initialName]);

  async function save() {
    if (!name.trim()) return setError("Give the buyer's name.");
    if (!phone.trim()) return setError("Give a phone number so Accounts can reach the buyer.");
    if (pin.trim() && !PIN.test(pin.trim())) return setError("A KRA PIN looks like A123456789B.");
    setBusy(true);
    setError(null);
    const r = await createBuyer({
      customer_name: name.trim(),
      phone: phone.trim(),
      tax_id: pin.trim() || undefined,
      email: email.trim() || undefined,
      customer_type: kind,
    });
    setBusy(false);
    if (isError(r)) return setError(r.error);
    onCreated(r.name);
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle>New buyer</DialogTitle>
          <DialogDescription>
            Added as a Customer, with the billing currency, price list, payment terms and receivable
            account the invoice needs.
          </DialogDescription>
        </DialogHeader>
        {error && <Notice tone="error">{error}</Notice>}
        <div className="grid gap-3">
          <div className="grid gap-1">
            <Label htmlFor="nb-name">Name</Label>
            <Input id="nb-name" value={name} onChange={(e) => setName(e.target.value)} />
          </div>
          <div className="grid gap-1">
            <Label htmlFor="nb-phone">Phone</Label>
            <Input id="nb-phone" value={phone} onChange={(e) => setPhone(e.target.value)} />
          </div>
          <div className="grid gap-1">
            <Label htmlFor="nb-pin">KRA PIN (optional)</Label>
            <Input id="nb-pin" value={pin} onChange={(e) => setPin(e.target.value.toUpperCase())} />
          </div>
          <div className="grid gap-1">
            <Label htmlFor="nb-email">Email (optional)</Label>
            <Input id="nb-email" value={email} onChange={(e) => setEmail(e.target.value)} />
          </div>
          <div className="grid gap-1">
            <Label htmlFor="nb-type">Buyer is</Label>
            <select
              id="nb-type"
              className="h-9 rounded-md border border-input bg-background px-3 text-sm"
              value={kind}
              onChange={(e) => setKind(e.target.value)}
            >
              <option>Individual</option>
              <option>Company</option>
              <option>Partnership</option>
            </select>
          </div>
          <div className="flex justify-end gap-2">
            <Button variant="outline" disabled={busy} onClick={() => onOpenChange(false)}>
              Cancel
            </Button>
            <Button disabled={busy} onClick={save}>
              Add buyer
            </Button>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}
