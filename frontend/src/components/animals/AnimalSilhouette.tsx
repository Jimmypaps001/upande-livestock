import type { CSSProperties } from "react";
import {
  pickSilhouette,
  silhouetteClass,
  type Silhouette,
  type SilhouetteSubject,
} from "@/lib/silhouettes";
import { cn } from "@/lib/utils";

/**
 * The drawings, read from the files the desk serves
 * (upande_livestock/public/images/silhouettes/, the supplied artwork traced by
 * scripts/trace_silhouettes.py) and inlined into the bundle, so they paint in
 * the first frame and take the page's colour: every shape is `currentColor`.
 * The grazing cow with its grass is for print and the phone, not the lists.
 */
const FILES = import.meta.glob(
  ["../../../../upande_livestock/public/images/silhouettes/*.svg", "!**/*-grass.svg"],
  { query: "?raw", import: "default", eager: true },
) as Record<string, string>;

const ART: Partial<Record<Silhouette, { viewBox: string; inner: string }>> = {};
for (const [path, text] of Object.entries(FILES)) {
  const name = path.split("/").pop()!.replace(/\.svg$/, "") as Silhouette;
  const viewBox = /viewBox="([^"]+)"/.exec(text)?.[1] ?? "0 0 240 160";
  const inner = text
    .replace(/^[\s\S]*?<svg[^>]*>/, "")
    .replace(/<\/svg>\s*$/, "")
    .replace(/<!--[\s\S]*?-->/g, "");
  ART[name] = { viewBox, inner };
}

/** One drawing, in the current text colour. */
export function AnimalSilhouette({
  name,
  kind,
  label,
  className,
}: {
  name: Silhouette;
  /** Its class (cow, bull, steer…), carried as data-kind for tests and styling. */
  kind?: string;
  label?: string;
  className?: string;
}) {
  const art = ART[name] ?? ART.cow;
  return (
    <svg
      viewBox={art?.viewBox ?? "0 0 240 160"}
      className={className}
      role={label ? "img" : undefined}
      aria-label={label}
      aria-hidden={label ? undefined : true}
      data-kind={kind}
      data-pose={name}
      // Our own files, read at build time: no user content reaches this.
      dangerouslySetInnerHTML={{ __html: art?.inner ?? "" }}
    />
  );
}

/**
 * The stand-in for a photograph: a soft card tinted with the stage's colour
 * and the animal's silhouette in a deeper shade of it, like a picture in a
 * frame. The drawing is picked from the animal (see `pickSilhouette`), so the
 * same cow wears the same picture in the list, the portrait and the compare
 * dialog. `round` makes it a list avatar.
 */
export function SilhouetteFrame({
  animal,
  tone = "var(--sd-quiet)",
  round = false,
  label,
  className,
  artClassName,
}: {
  animal: SilhouetteSubject;
  tone?: string;
  round?: boolean;
  label?: string;
  className?: string;
  artClassName?: string;
}) {
  const style: CSSProperties = {
    background: `color-mix(in srgb, ${tone} 15%, var(--sd-bg-soft))`,
    color: `color-mix(in srgb, ${tone} 58%, var(--sd-ink))`,
  };
  return (
    <span
      className={cn(
        "flex items-center justify-center overflow-hidden",
        round ? "rounded-full" : "rounded-[inherit]",
        className,
      )}
      style={style}
      aria-hidden={label ? undefined : true}
    >
      <AnimalSilhouette
        name={pickSilhouette(animal)}
        kind={silhouetteClass(animal)}
        label={label}
        // the drawings differ in shape (a cow side on is wide, a calf facing us
        // is tall), so each is fitted inside the same box rather than to a width
        className={cn(round ? "h-[64%] w-[78%]" : "h-[62%] w-4/5", artClassName)}
      />
    </span>
  );
}
