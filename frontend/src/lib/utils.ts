import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

/** Two decimals with thousands separators — the desk block's `fmt()`, so the
 *  same number reads the same in both UIs while they run side by side. */
export function fmt(n: unknown): string {
  const v = Number(n);
  return (Number.isFinite(v) ? v : 0).toLocaleString(undefined, {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
}

export function num(v: unknown): number {
  const n = parseFloat(String(v));
  return Number.isNaN(n) ? 0 : n;
}

/** Today in the farm's wall clock as YYYY-MM-DD.
 *  Not toISOString(): east of UTC that returns yesterday for the first hours
 *  of the morning, and a feed run posted on the wrong day is a real stock
 *  movement on the wrong day. */
export function todayISO(): string {
  const d = new Date();
  const p = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`;
}
