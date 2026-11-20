import {
  Baby, ArrowRightLeft, Bug, ClipboardPlus, Dna, Droplets, Flame, FlaskConical, Footprints,
  HeartCrack, Moon, Pill, ScanHeart, Scale, Scissors, Sparkles, Stethoscope, Syringe, Trash2,
  Utensils, type LucideIcon,
} from "lucide-react";
import catalog from "./event-catalog.json";
import type { View } from "@/lib/router";

/**
 * One order, one grouping, one icon per event type — for every place the desk
 * lists events (sidebar, Events filter, Settings > Events, the feed). The data
 * lives in event-catalog.json so the phone app can mirror it exactly.
 */
export type EventGroupKey =
  "servicing" | "health" | "quality" | "herd" | "production" | "husbandry" | "disposal";

export interface EventEntry {
  /** Livestock Event Type name; the catalog key for entries that are not one. */
  key: string;
  eventType: string | null;
  view: View | null;
  label: string;
  group: EventGroupKey;
  icon: string;
}

const ICONS: Record<string, LucideIcon> = {
  Baby, ArrowRightLeft, Bug, ClipboardPlus, Dna, Droplets, Flame, FlaskConical, Footprints,
  HeartCrack, Moon, Pill, ScanHeart, Scale, Scissors, Sparkles, Stethoscope, Syringe, Trash2,
  Utensils,
};

export const EVENT_GROUPS = catalog.groups as { key: EventGroupKey; label: string }[];
export const EVENT_CATALOG = catalog.events as EventEntry[];

const BY_KEY = new Map(EVENT_CATALOG.map((e, i) => [e.key, { e, i }]));
const BY_VIEW = new Map(
  EVENT_CATALOG.filter((e) => e.view).map((e) => [e.view as string, e]),
);

export function iconByName(name: string): LucideIcon {
  return ICONS[name] ?? Sparkles;
}

/** The entry for an event type name or a catalog key. */
export function eventEntry(eventType: string): EventEntry | undefined {
  return BY_KEY.get(eventType)?.e;
}

/** The icon of an event type; a type the catalog does not know gets a neutral one. */
export function eventIcon(eventType: string): LucideIcon {
  const e = eventEntry(eventType);
  return e ? iconByName(e.icon) : Sparkles;
}

/** The catalog entry behind a desk view (Husbandry gets the first husbandry entry's group). */
export function viewEntry(view: string): EventEntry | undefined {
  if (view === "husbandry") return { ...BY_KEY.get("Vaccination")!.e, view: "husbandry", label: "Husbandry", icon: "Scissors" };
  return BY_VIEW.get(view);
}

export function viewIcon(view: string): LucideIcon | undefined {
  const e = viewEntry(view);
  return e ? iconByName(e.icon) : undefined;
}

/** Sort event type names into the catalog order; unknown types go last, alphabetically. */
export function sortEventTypes<T>(items: T[], name: (t: T) => string = (t) => String(t)): T[] {
  const rank = (t: T) => BY_KEY.get(name(t))?.i ?? Infinity;
  return [...items].sort((a, b) => rank(a) - rank(b) || name(a).localeCompare(name(b)));
}

/** The catalog entries of one group, in order. */
export function groupEntries(group: EventGroupKey): EventEntry[] {
  return EVENT_CATALOG.filter((e) => e.group === group);
}

/** Heading label for an event type's group (for grouped pickers). */
export function groupOf(eventType: string): { key: EventGroupKey; label: string } | undefined {
  const e = eventEntry(eventType);
  return e ? EVENT_GROUPS.find((g) => g.key === e.group) : undefined;
}
