import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import { AlertTriangle, CheckCircle2, Info, X } from "lucide-react";
import { plainText } from "@/components/feeding/Notice";
import { cn } from "@/lib/utils";

/**
 * What just happened, said without moving the page.
 *
 * An inline notice pushed every card down the moment a button answered, so the
 * thing you had just clicked jumped out from under the pointer — and on a
 * screen you had scrolled, the answer appeared somewhere you were not looking.
 * These float instead.
 *
 * ONLY WHAT JUST HAPPENED. A toast is gone in a few seconds, so it is the wrong
 * home for anything you might need to read twice: a page that failed to load, a
 * recipe whose ingredients do not add up, the case for culling a cow. Those
 * stay inline, where they are still there when you look back. The rule is the
 * lifetime of the fact, not how it is worded.
 *
 * Hand-rolled, like the charts: this is a hundred lines against a dependency,
 * on a page a farm loads over a rural connection.
 *
 * AN ERROR DOES NOT TIME OUT. The farm's refusals carry instructions — which
 * items are short, the earliest date that would work — and a message somebody
 * has to act on must not vanish while they are reading it.
 */

export type ToastTone = "ok" | "error" | "info";

interface Toast {
  id: number;
  tone: ToastTone;
  text: string;
}

const LIFETIME: Record<ToastTone, number> = { ok: 5000, info: 7000, error: 0 };

const ToastContext = createContext<(text: string, tone?: ToastTone) => void>(() => {});

/** Say something, from anywhere. */
export function useToast() {
  return useContext(ToastContext);
}

export function ToastProvider({ children }: { children: React.ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([]);
  const next = useRef(1);
  const timers = useRef(new Map<number, ReturnType<typeof setTimeout>>());

  const dismiss = useCallback((id: number) => {
    setToasts((all) => all.filter((t) => t.id !== id));
    const timer = timers.current.get(id);
    if (timer) clearTimeout(timer);
    timers.current.delete(id);
  }, []);

  const show = useCallback(
    (text: string, tone: ToastTone = "ok") => {
      const body = String(plainText(text) ?? text);
      if (!body.trim()) return;
      const id = next.current++;
      // Three at once is a stack nobody reads; the oldest goes.
      setToasts((all) => [...all.slice(-2), { id, tone, text: body }]);
      const ms = LIFETIME[tone];
      if (ms) timers.current.set(id, setTimeout(() => dismiss(id), ms));
    },
    [dismiss],
  );

  useEffect(() => {
    const running = timers.current;
    return () => running.forEach(clearTimeout);
  }, []);

  const value = useMemo(() => show, [show]);

  return (
    <ToastContext.Provider value={value}>
      {children}
      <div
        // Bottom right on a desktop, across the bottom on a phone — where a
        // thumb already is, and clear of the header dock.
        className="pointer-events-none fixed inset-x-3 bottom-3 z-50 flex flex-col items-stretch gap-2 sm:inset-x-auto sm:right-5 sm:bottom-5 sm:w-[min(24rem,calc(100vw-2.5rem))]"
      >
        {toasts.map((t) => (
          <ToastCard key={t.id} toast={t} onDismiss={() => dismiss(t.id)} />
        ))}
      </div>
    </ToastContext.Provider>
  );
}

function ToastCard({ toast, onDismiss }: { toast: Toast; onDismiss: () => void }) {
  const Icon = toast.tone === "error" ? AlertTriangle : toast.tone === "ok" ? CheckCircle2 : Info;
  return (
    <div
      // `alert` is announced at once and interrupts; `status` waits for a pause.
      // A refusal the operator has to act on earns the interruption, a
      // confirmation does not.
      role={toast.tone === "error" ? "alert" : "status"}
      className={cn(
        "pointer-events-auto flex items-start gap-2.5 rounded-[var(--sd-radius-lg)] px-3.5 py-3",
        "text-[13px] leading-relaxed whitespace-pre-line shadow-[var(--sd-shadow-3)]",
        "animate-in slide-in-from-bottom-2 fade-in duration-200",
        toast.tone === "error" && "bg-[var(--sd-card)] text-[var(--sd-sev-critical)]",
        toast.tone === "ok" && "bg-[var(--sd-card)] text-[var(--sd-sev-moderate)]",
        toast.tone === "info" && "bg-[var(--sd-card)] text-[var(--sd-ink)]",
      )}
    >
      <Icon className="mt-0.5 h-4 w-4 shrink-0" />
      <span className="min-w-0 flex-1">{toast.text}</span>
      <button
        type="button"
        onClick={onDismiss}
        aria-label="Dismiss"
        className="-mr-1 shrink-0 text-[var(--sd-quiet)] transition-colors hover:text-[var(--sd-ink)]"
      >
        <X className="h-3.5 w-3.5" />
      </button>
    </div>
  );
}
