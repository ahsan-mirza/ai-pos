import type { DemoBusinessCode } from "@ai-pos/shared-types";
import { portalUrl } from "../env";
import { EXPLORE_DEMO_LABEL, EXPLORE_DEMO_LABEL_AR, solutionDemoHref } from "../solutionDemo";
import { track } from "../track";

const SOLID = "bg-primary text-white hover:bg-primary-hover";
const OUTLINE = "border border-primary bg-transparent text-primary hover:bg-primary/10";

export function ExploreDemoButton({
  businessCode,
  label,
  variant = "solid",
  className,
}: {
  businessCode: DemoBusinessCode;
  label?: string;
  variant?: "solid" | "outline";
  className?: string;
}) {
  const href = solutionDemoHref(portalUrl, businessCode);
  if (href === null) return null;
  const arabic = typeof document !== "undefined" && document.documentElement.lang === "ar";
  const text = label ?? (arabic ? EXPLORE_DEMO_LABEL_AR : EXPLORE_DEMO_LABEL);
  return (
    <a
      href={href}
      data-explore-demo={businessCode}
      aria-describedby="explore-demo-note"
      className={[
        "inline-flex h-12 w-full items-center justify-center rounded-2xl px-5 text-sm font-semibold sm:w-auto",
        "focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary",
        variant === "outline" ? OUTLINE : SOLID,
        className,
      ]
        .filter(Boolean)
        .join(" ")}
      onClick={() => track("click_explore_demo", { business_code: businessCode, page_path: window.location.pathname })}
    >
      {text}
    </a>
  );
}
