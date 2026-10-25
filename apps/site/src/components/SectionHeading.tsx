export function SectionHeading({
  kicker,
  title,
  children,
}: {
  kicker: string;
  title: string;
  children?: string;
}) {
  return (
    <div className="max-w-2xl">
      <p className="text-xs font-semibold uppercase tracking-[0.14em] text-primary">{kicker}</p>
      <h2 className="mt-2 text-3xl font-semibold tracking-tight text-charcoal sm:text-4xl">{title}</h2>
      {children ? <p className="mt-3 text-base leading-7 text-charcoal/70">{children}</p> : null}
    </div>
  );
}
