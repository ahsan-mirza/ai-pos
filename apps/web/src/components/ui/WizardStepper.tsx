import { useLocale } from "@ai-pos/ui";
import { AnimatePresence, motion, useReducedMotion } from "framer-motion";
import { Check } from "lucide-react";

export interface WizardStepItem {
  id: string;
  /** English source label. The stepper translates it. */
  label: string;
}

export type WizardStepStatus = "completed" | "current" | "upcoming";

export interface WizardStepperProps {
  steps: readonly WizardStepItem[];
  currentStep: string;
  completedSteps: readonly string[];
  /** Called for a completed step when the wizard allows going back. */
  onNavigate?: (stepId: string) => void;
  /** Completed steps stay inert when this returns false. Defaults to allowing them. */
  canNavigate?: (stepId: string) => boolean;
  /** Page direction. Defaults to the active locale. */
  dir?: "ltr" | "rtl";
  /** The current step is blocked by a validation error. */
  invalid?: boolean;
  /** English source name for the navigation landmark. */
  label?: string;
  className?: string;
}

const ease = "easeOut" as const;

/** Linear wizards treat earlier steps as completed. Current wins over a stale completed id. */
export function wizardStepStatus(
  stepId: string,
  currentStep: string,
  completedSteps: readonly string[],
): WizardStepStatus {
  if (stepId === currentStep) return "current";
  if (completedSteps.includes(stepId)) return "completed";
  return "upcoming";
}

/** Only a finished step can be revisited, and only when the wizard offers navigation. */
export function wizardStepSelectable(status: WizardStepStatus, navigate: boolean): boolean {
  return navigate && status === "completed";
}

function circleClass(status: WizardStepStatus, invalid: boolean): string {
  if (status === "completed") return "border-accent bg-accent text-white";
  if (status === "current") {
    return invalid ? "border-danger bg-danger/5 text-danger" : "border-accent bg-accent/10 text-accent";
  }
  return "border-line bg-surface text-charcoal/55";
}

function labelClass(status: WizardStepStatus): string {
  if (status === "current") return "font-semibold text-accent";
  if (status === "completed") return "font-medium text-accent";
  return "font-medium text-charcoal/60";
}

function StepConnector({ active, hidden, reduce }: { active: boolean; hidden: boolean; reduce: boolean }) {
  return (
    <span aria-hidden="true" className={`relative h-0.5 min-w-0 flex-1 ${hidden ? "invisible" : ""}`}>
      <span className="absolute inset-0 bg-line" />
      <motion.span
        className="absolute inset-y-0 start-0 bg-accent"
        initial={false}
        animate={{ width: !hidden && active ? "100%" : "0%" }}
        transition={{ duration: reduce ? 0 : 0.28, ease }}
      />
    </span>
  );
}

function StepMarker({
  status,
  index,
  invalid,
  reduce,
}: {
  status: WizardStepStatus;
  index: number;
  invalid: boolean;
  reduce: boolean;
}) {
  const done = status === "completed";
  return (
    <span
      aria-hidden="true"
      className={`wizard-step-circle relative mx-1 flex shrink-0 items-center justify-center rounded-full border-2 text-[11px] font-semibold tabular-nums transition-colors duration-200 motion-reduce:transition-none ${circleClass(status, invalid)}`}
    >
      <AnimatePresence initial={false}>
        <motion.span
          key={done ? "done" : "num"}
          className="absolute inset-0 flex items-center justify-center"
          initial={reduce ? false : { opacity: 0, scale: 0.92 }}
          animate={{ opacity: 1, scale: 1 }}
          exit={{ opacity: 0, transition: { duration: reduce ? 0 : 0.12 } }}
          transition={{ duration: reduce ? 0 : 0.18, ease }}
        >
          {done ? <Check size={13} strokeWidth={2.5} /> : index + 1}
        </motion.span>
      </AnimatePresence>
    </span>
  );
}

/** Horizontal wizard progress. Step state comes from the caller; this does not advance a step on its own. */
export function WizardStepper({
  steps,
  currentStep,
  completedSteps,
  onNavigate,
  canNavigate,
  dir,
  invalid = false,
  label = "Go live steps",
  className = "",
}: WizardStepperProps) {
  const { locale, t } = useLocale();
  const direction = dir ?? (locale === "ar" ? "rtl" : "ltr");
  const reduce = useReducedMotion() === true;
  const currentIndex = steps.findIndex((step) => step.id === currentStep);
  const safeIndex = currentIndex < 0 ? 0 : currentIndex;
  const current = steps[safeIndex];
  const progress = t("Step {current} of {total}: {label}", {
    current: safeIndex + 1,
    total: steps.length,
    label: current ? t(current.label) : "",
  });

  return (
    <nav aria-label={t(label)} dir={direction} className={`wizard-stepper relative w-full min-w-0 self-stretch ${className}`}>
      <p className="sr-only" aria-live="polite">
        {progress}
      </p>
      <p className="wizard-stepper-summary mb-2.5 w-full items-baseline justify-between gap-3" aria-hidden="true">
        <span className={`min-w-0 truncate text-sm font-semibold ${invalid ? "text-danger" : "text-accent"}`}>
          {current ? t(current.label) : ""}
        </span>
        <span className="shrink-0 whitespace-nowrap text-xs font-medium tabular-nums text-charcoal/60">
          {t("Step {current} of {total}", { current: safeIndex + 1, total: steps.length })}
        </span>
      </p>
      <ol className="flex w-full min-w-0 items-start">
        {steps.map((step, index) => {
          const status = wizardStepStatus(step.id, currentStep, completedSteps);
          const previousId = steps[index - 1]?.id;
          const lineBefore = previousId != null && completedSteps.includes(previousId) && previousId !== currentStep;
          const selectable = wizardStepSelectable(status, onNavigate != null && (canNavigate?.(step.id) ?? true));
          const name = t(step.label);
          const state =
            status === "completed" ? t("Completed") : status === "current" ? t("Current step") : t("Upcoming");
          const body = (
            <>
              <span className="flex w-full items-center">
                <StepConnector active={lineBefore} hidden={index === 0} reduce={reduce} />
                <StepMarker status={status} index={index} invalid={invalid && status === "current"} reduce={reduce} />
                <StepConnector
                  active={status === "completed"}
                  hidden={index === steps.length - 1}
                  reduce={reduce}
                />
              </span>
              <span className={`wizard-step-label px-0.5 text-center ${labelClass(status)}`} title={name}>
                {name}
              </span>
              <span className="sr-only">{state}</span>
            </>
          );
          const itemClass = "relative flex w-full min-w-0 flex-col items-center rounded-lg py-1 text-center";

          return (
            <li
              key={step.id}
              className="flex min-w-0 flex-1"
              data-step-id={step.id}
              data-status={status}
              aria-current={status === "current" ? "step" : undefined}
              aria-invalid={status === "current" && invalid ? true : undefined}
            >
              {selectable ? (
                <button type="button" className={`${itemClass} cursor-pointer`} onClick={() => onNavigate?.(step.id)}>
                  {body}
                </button>
              ) : (
                <div className={itemClass}>{body}</div>
              )}
            </li>
          );
        })}
      </ol>
    </nav>
  );
}
