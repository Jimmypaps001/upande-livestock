import { useState } from "react";
import { cn } from "@/lib/utils";

const TINTS = [
  "var(--sd-data-cyan)",
  "var(--sd-data-indigo)",
  "var(--sd-data-green)",
  "var(--sd-data-purple)",
  "var(--sd-data-amber)",
  "var(--sd-data-pink)",
];

/** One colour per vet, so the same person keeps it everywhere; behind initials only. */
export function tintFor(key: string): string {
  let h = 0;
  for (let i = 0; i < key.length; i++) h = (h * 31 + key.charCodeAt(i)) >>> 0;
  return TINTS[h % TINTS.length];
}

/** The vet's photo (their Employee image) or, without one, initials on a tint. */
export function VetAvatar({
  id,
  name,
  image,
  initials,
  size = 44,
  className,
}: {
  id: string;
  name: string;
  image?: string;
  initials: string;
  size?: number;
  className?: string;
}) {
  const [broken, setBroken] = useState(false);
  const showImage = !!image && !broken;
  return (
    <span
      className={cn(
        "inline-flex shrink-0 items-center justify-center overflow-hidden rounded-full ring-1 ring-[var(--sd-line)]",
        className,
      )}
      style={{ width: size, height: size }}
      title={name}
    >
      {showImage ? (
        <img
          src={image}
          alt={name}
          loading="lazy"
          className="h-full w-full object-cover"
          onError={() => setBroken(true)}
        />
      ) : (
        <span
          className="flex h-full w-full items-center justify-center font-semibold text-white"
          style={{ background: tintFor(id || name), fontSize: Math.round(size * 0.4) }}
          data-testid="vet-initials"
        >
          {initials}
        </span>
      )}
    </span>
  );
}
