/**
 * The frame every surface sits in.
 *
 * `flex-1` with padding and no max width: the workspace is whatever the
 * window leaves after the sidebar, and it reflows when the sidebar collapses
 * to its icon rail. A centred `max-w` column here would pin the content to
 * one width and leave a gutter on a wide screen — which is exactly what the
 * first slice did, and what this replaces.
 *
 * `min-w-0` matters as much as `flex-1`: without it a wide table inside a
 * flex child refuses to shrink and pushes the whole page into a horizontal
 * scroll. Wide content scrolls inside its own box instead.
 */
export function Page({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex min-w-0 flex-1 flex-col gap-6 px-4 py-4 md:px-6 md:py-6">
      {children}
    </div>
  );
}

export function PageHeading({
  eyebrow,
  title,
  children,
}: {
  eyebrow: string;
  title: string;
  children?: React.ReactNode;
}) {
  return (
    <header className="flex flex-col gap-1">
      <span className="text-[10px] font-medium uppercase tracking-[0.16em] text-[var(--sd-quiet)]">
        {eyebrow}
      </span>
      <h1 className="text-[26px] font-semibold tracking-[-0.02em] text-[var(--sd-ink)]">
        {title}
      </h1>
      {children && (
        <p className="max-w-[64rem] text-[13px] text-[var(--sd-muted)]">{children}</p>
      )}
    </header>
  );
}
