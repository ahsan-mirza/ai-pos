import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { goLiveSteps } from "../../features/onboarding/GoLiveModal";
import { WizardStepper, wizardStepSelectable, wizardStepStatus } from "./WizardStepper";

describe("go live steps", () => {
  it("starts on the plan and keeps billing and hardware off the free and enterprise paths", () => {
    expect(goLiveSteps(true, false)).toEqual(["plan", "data", "confirm"]);
  });

  it("includes billing and hardware only for a payable plan", () => {
    expect(goLiveSteps(true, true)).toEqual(["plan", "cycle", "extras", "data", "confirm"]);
  });

  it("starts at your data when the catalog is unavailable", () => {
    expect(goLiveSteps(false, false)).toEqual(["data", "confirm"]);
  });
});

describe("wizard step status", () => {
  const paid = ["plan", "cycle", "extras", "data", "confirm"];

  it("highlights the first step before anything is complete", () => {
    expect(paid.map((id) => wizardStepStatus(id, "plan", []))).toEqual([
      "current",
      "upcoming",
      "upcoming",
      "upcoming",
      "upcoming",
    ]);
  });

  it("marks earlier steps complete and later steps upcoming", () => {
    expect(wizardStepStatus("plan", "extras", ["plan", "cycle"])).toBe("completed");
    expect(wizardStepStatus("cycle", "extras", ["plan", "cycle"])).toBe("completed");
    expect(wizardStepStatus("extras", "extras", ["plan", "cycle"])).toBe("current");
    expect(wizardStepStatus("data", "extras", ["plan", "cycle"])).toBe("upcoming");
  });

  it("drops completion when the wizard goes back", () => {
    expect(wizardStepStatus("cycle", "plan", [])).toBe("upcoming");
    expect(wizardStepStatus("plan", "plan", [])).toBe("current");
  });

  it("does not let a click skip ahead", () => {
    expect(wizardStepSelectable("completed", true)).toBe(true);
    expect(wizardStepSelectable("current", true)).toBe(false);
    expect(wizardStepSelectable("upcoming", true)).toBe(false);
    expect(wizardStepSelectable("completed", false)).toBe(false);
  });
});

describe("wizard stepper markup", () => {
  const steps = [
    { id: "plan", label: "Plan" },
    { id: "data", label: "Your data" },
    { id: "confirm", label: "Confirm" },
  ];

  it("follows reading direction and only exposes completed steps as actions", () => {
    const html = renderToStaticMarkup(
      <WizardStepper
        steps={steps}
        currentStep="data"
        completedSteps={["plan"]}
        onNavigate={() => undefined}
        dir="rtl"
      />,
    );

    expect(html).toContain('dir="rtl"');
    expect(html).toContain('aria-current="step"');
    expect(html).toContain("Your data");
    expect(html).not.toContain("Billing");
    expect(html.match(/<button/g)).toHaveLength(1);
    expect(html).toContain('data-status="completed"');
    expect(html).toContain('data-status="upcoming"');
  });

  it("marks the current step when validation failed", () => {
    const html = renderToStaticMarkup(
      <WizardStepper steps={steps} currentStep="plan" completedSteps={[]} invalid dir="ltr" />,
    );
    expect(html).toContain('aria-invalid="true"');
    expect(html).not.toContain("<button");
  });
});
