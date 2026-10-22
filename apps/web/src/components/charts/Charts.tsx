import { chartColors } from "@ai-pos/design-tokens";

function smoothPath(points: [number, number][]): string {
  const [first, ...rest] = points;
  if (first === undefined) return "";
  let path = `M${first[0]},${first[1]}`;
  let previous = first;
  for (const point of rest) {
    const midX = (previous[0] + point[0]) / 2;
    path += ` C${midX},${previous[1]} ${midX},${point[1]} ${point[0]},${point[1]}`;
    previous = point;
  }
  return path;
}

export function Sparkline({ values, stroke }: { values: number[]; stroke: string }) {
  if (values.length === 0) return null;
  const width = 300;
  const height = 72;
  const inset = 4;
  const max = Math.max(...values, 1);
  const min = Math.min(...values);
  const span = Math.max(max - min, 1);
  const points = values.map((value, index): [number, number] => {
    const x = values.length === 1 ? width / 2 : (index / (values.length - 1)) * width;
    const y = height - inset - ((value - min) / span) * (height - inset * 2);
    return [x, y];
  });
  const line = smoothPath(points);
  const last = points[points.length - 1] ?? [width, height];
  const area = `${line} L${last[0]},${height} L${points[0]?.[0] ?? 0},${height} Z`;

  return (
    <svg
      viewBox={`0 0 ${width} ${height}`}
      preserveAspectRatio="none"
      className="h-[72px] w-full overflow-visible"
      role="img"
      aria-label="Revenue trend"
    >
      <defs>
        <linearGradient id="sparkline-fill" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" style={{ stopColor: stroke }} stopOpacity="0.18" />
          <stop offset="100%" style={{ stopColor: stroke }} stopOpacity="0" />
        </linearGradient>
      </defs>
      <path d={area} fill="url(#sparkline-fill)" />
      <path
        d={line}
        fill="none"
        style={{ stroke }}
        strokeWidth="2.5"
        strokeLinecap="round"
        vectorEffect="non-scaling-stroke"
      />
    </svg>
  );
}

export function SplitBar({ segments }: { segments: { label: string; amount: number; color: string }[] }) {
  const total = segments.reduce((sum, segment) => sum + segment.amount, 0);
  const share = (amount: number) => (total === 0 ? 0 : Math.round((amount / total) * 100));
  return (
    <div>
      <div className="mb-2.5 flex items-center justify-between text-xs font-semibold capitalize text-white">
        {segments.map((segment) => (
          <span key={segment.label} className="flex items-center gap-1.5">
            <span className="h-2 w-2 rounded-full" style={{ background: segment.color }} />
            {segment.label}
            <span className="tabular-nums text-white/75">{share(segment.amount)}%</span>
          </span>
        ))}
      </div>
      <div className="flex h-3 gap-1">
        {total === 0 ? (
          <div className="h-full w-full rounded-full bg-white/30" />
        ) : (
          segments.map((segment) => (
            <div
              key={segment.label}
              className="h-full rounded-full"
              style={{ width: `${(segment.amount / total) * 100}%`, background: segment.color }}
            />
          ))
        )}
      </div>
    </div>
  );
}

export function BarSeries({ values }: { values: number[] }) {
  const max = Math.max(...values, 1);
  const peak = values.indexOf(Math.max(...values));
  return (
    <div className="flex h-[72px] items-end justify-between gap-2" aria-hidden="true">
      {values.map((value, index) => (
        <div
          key={`${index}-${value}`}
          className={`max-w-7 flex-1 rounded-lg ${index === peak ? "bg-charcoal" : "bg-canvas"}`}
          style={{ height: `${Math.max(14, (value / max) * 100)}%` }}
        />
      ))}
    </div>
  );
}

export function CategoryDonut({
  slices,
}: {
  slices: { label: string; value: number }[];
}) {
  const total = slices.reduce((sum, slice) => sum + slice.value, 0);
  const radius = 54;
  const stroke = 18;
  const circumference = 2 * Math.PI * radius;
  let offset = 0;

  return (
    <div className="flex flex-col items-center gap-6 sm:flex-row sm:gap-8">
      <div className="relative h-40 w-40 shrink-0">
        <svg viewBox="0 0 140 140" className="h-full w-full -rotate-90" role="img" aria-label="Category distribution">
          <circle cx="70" cy="70" r={radius} fill="none" stroke="#F3F4F6" strokeWidth={stroke} />
          {total > 0 &&
            slices.map((slice, index) => {
              const length = (slice.value / total) * circumference;
              const color = chartColors[index % chartColors.length] ?? "#222026";
              const element = (
                <circle
                  key={slice.label}
                  cx="70"
                  cy="70"
                  r={radius}
                  fill="none"
                  style={{ stroke: color }}
                  strokeWidth={stroke}
                  strokeDasharray={`${length} ${circumference - length}`}
                  strokeDashoffset={-offset}
                />
              );
              offset += length;
              return element;
            })}
        </svg>
        <div className="absolute inset-0 flex flex-col items-center justify-center">
          <span className="font-sans text-[28px] font-semibold leading-none tabular-nums">
            {total.toLocaleString()}
          </span>
          <span className="mt-1 text-xs font-medium text-charcoal/50">Units</span>
        </div>
      </div>
      <ul className="w-full flex-1 space-y-3">
        {slices.map((slice, index) => {
          const color = chartColors[index % chartColors.length] ?? "#222026";
          const share = total === 0 ? 0 : Math.round((slice.value / total) * 100);
          return (
            <li key={slice.label} className="flex items-center justify-between gap-4 text-sm">
              <span className="flex min-w-0 items-center gap-2.5 font-medium">
                <span className="h-3 w-3 shrink-0 rounded-full" style={{ background: color }} />
                <span className="truncate">{slice.label}</span>
                <span className="tabular-nums text-charcoal/50">{slice.value.toLocaleString()}</span>
              </span>
              <span className="min-w-[52px] rounded-full bg-surface px-2.5 py-1 text-center text-xs font-semibold tabular-nums">
                {share}%
              </span>
            </li>
          );
        })}
      </ul>
    </div>
  );
}

export function HorizontalBars({
  rows,
}: {
  rows: { label: string; value: number; display: string }[];
}) {
  const max = Math.max(...rows.map((row) => row.value), 1);
  return (
    <ul className="space-y-5">
      {rows.map((row, index) => (
        <li key={row.label}>
          <div className="mb-2 flex items-center justify-between gap-4 text-sm">
            <span className="font-medium">{row.label}</span>
            <span className="font-semibold tabular-nums">{row.display}</span>
          </div>
          <div className="h-3 rounded-full bg-surface">
            <div
              className={`h-3 rounded-full ${index === 0 ? "bg-accent" : "bg-charcoal"}`}
              style={{ width: `${(row.value / max) * 100}%` }}
            />
          </div>
        </li>
      ))}
    </ul>
  );
}
