import type { PlaceholderKind } from "@/lib/animals";

/**
 * The generic picture for an animal with no photograph, chosen by sex AND stage
 * (see `placeholderKind`): a bull has the neck hump and horns, a steer a plain
 * frame, a calf is small with a big head, a heifer is slim and a cow carries an
 * udder. Drawn in one colour so the stage's own tone shows through.
 */
export function AnimalSilhouette({
  kind,
  color,
  label,
}: {
  kind: PlaceholderKind;
  color: string;
  label: string;
}) {
  const calf = kind === "calf";
  const s = calf ? 0.62 : 1;
  const bodyRy = kind === "bull" ? 30 : kind === "heifer" ? 22 : 26;
  return (
    <svg viewBox="0 0 200 160" className="h-2/5 w-4/5" role="img" aria-label={label} data-kind={kind}>
      <g
        fill={color}
        transform={`translate(${calf ? 38 : 0} ${calf ? 52 : 0}) scale(${s})`}
      >
        {/* body */}
        <ellipse cx="100" cy="78" rx="58" ry={bodyRy} />
        {/* shoulder hump: the bull's */}
        {kind === "bull" && <ellipse cx="136" cy="56" rx="24" ry="20" />}
        {/* legs */}
        {[58, 74, 126, 142].map((x) => (
          <rect key={x} x={x} y="90" width="9" height="46" rx="3" />
        ))}
        {/* udder: the cow's */}
        {kind === "cow" && <ellipse cx="68" cy="108" rx="11" ry="9" />}
        {/* neck and head */}
        <rect x="140" y="52" width="26" height="30" rx="10" transform="rotate(-18 150 66)" />
        <ellipse cx="170" cy="82" rx={calf ? 17 : 14} ry={calf ? 15 : 12} />
        {/* horns */}
        {(kind === "bull" || kind === "steer") && (
          <path d="M160 66 q-6 -16 4 -22 M174 66 q4 -14 -2 -22" stroke={color} strokeWidth="4" fill="none" strokeLinecap="round" />
        )}
        {/* tail */}
        <path d="M44 70 q-16 8 -14 36" stroke={color} strokeWidth="4" fill="none" strokeLinecap="round" />
      </g>
    </svg>
  );
}
