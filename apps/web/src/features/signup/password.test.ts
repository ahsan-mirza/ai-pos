import {
  signupPasswordConfirmation,
  signupPasswordReady,
  signupPasswordRules,
  signupPasswordsAccepted,
  type SignupStart,
} from "@ai-pos/shared-types";
import { inputLeadingIcon } from "@ai-pos/ui";
import { describe, expect, it } from "vitest";

const VALID = "Owner-password-1";

function rule(id: string, password: string): boolean {
  return signupPasswordRules(password).find((item) => item.id === id)?.met === true;
}

describe("signup password policy", () => {
  it("rejects an empty password", () => {
    expect(signupPasswordReady("")).toBe(false);
    expect(signupPasswordRules("").every((item) => item.met === false)).toBe(true);
  });

  it("rejects fewer than 10 characters", () => {
    expect(rule("length", "Short1!")).toBe(false);
    expect(signupPasswordReady("Short1!")).toBe(false);
  });

  it("rejects a missing uppercase letter", () => {
    expect(rule("upper", "lowercase-1")).toBe(false);
    expect(signupPasswordReady("lowercase-1")).toBe(false);
  });

  it("rejects a missing number", () => {
    expect(rule("number", "No-Number-Here")).toBe(false);
    expect(signupPasswordReady("No-Number-Here")).toBe(false);
  });

  it("rejects a missing special character", () => {
    expect(rule("special", "NoSpecial11A")).toBe(false);
    expect(signupPasswordReady("NoSpecial11A")).toBe(false);
  });

  it("accepts a password that meets every backend rule", () => {
    expect(signupPasswordRules(VALID).every((item) => item.met)).toBe(true);
    expect(signupPasswordReady(VALID)).toBe(true);
  });

  it("uses the lock icon and a show/hide control for both password fields", () => {
    const passwordIcon = inputLeadingIcon({ type: "password", label: "Password", autoComplete: "new-password" });
    const confirmIcon = inputLeadingIcon({ type: "password", label: "Confirm password", autoComplete: "new-password" });
    expect(passwordIcon).toBe(confirmIcon);
    expect(passwordIcon.name || passwordIcon.displayName).toMatch(/Lock/);
  });
});

describe("signup password confirmation", () => {
  it("stays neutral while confirmation is empty", () => {
    expect(signupPasswordConfirmation(VALID, "")).toBe("empty");
    expect(signupPasswordsAccepted(VALID, "")).toBe(false);
  });

  it("rejects a confirmation that differs", () => {
    expect(signupPasswordConfirmation(VALID, "Owner-password-2")).toBe("mismatch");
    expect(signupPasswordsAccepted(VALID, "Owner-password-2")).toBe(false);
  });

  it("accepts an exact confirmation", () => {
    expect(signupPasswordConfirmation(VALID, VALID)).toBe("match");
    expect(signupPasswordsAccepted(VALID, VALID)).toBe(true);
  });

  it("rechecks confirmation when the password changes", () => {
    expect(signupPasswordConfirmation(VALID, VALID)).toBe("match");
    expect(signupPasswordConfirmation("Owner-password-2", VALID)).toBe("mismatch");
  });

  it("does not trim or rewrite either value", () => {
    expect(signupPasswordConfirmation(`${VALID} `, VALID)).toBe("mismatch");
    expect(signupPasswordConfirmation(` ${VALID}`, ` ${VALID}`)).toBe("match");
  });

  it("submits only the password field", () => {
    const confirmation = VALID;
    const body: SignupStart = {
      email: "owner@example.com",
      phone: "+971501234567",
      full_name: "Owner Name",
      password: VALID,
    };
    expect(Object.keys(body)).toEqual(["email", "phone", "full_name", "password"]);
    expect(JSON.stringify(body).includes("confirm")).toBe(false);
    expect(body.password).toBe(confirmation);
  });
});
