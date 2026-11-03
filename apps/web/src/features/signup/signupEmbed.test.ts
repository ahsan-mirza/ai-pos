import { SIGNUP_EMBED_MESSAGE, isSignupEmbedSearch } from "@ai-pos/shared-types";
import { describe, expect, it } from "vitest";

describe("signup embed flag", () => {
  it("recognises only the landing-page flag", () => {
    expect(isSignupEmbedSearch("?embed=1")).toBe(true);
    expect(isSignupEmbedSearch("")).toBe(false);
    expect(isSignupEmbedSearch("?embed=0")).toBe(false);
    expect(isSignupEmbedSearch("?email=owner@example.com")).toBe(false);
  });

  it("uses a message type that does not carry account fields", () => {
    expect(SIGNUP_EMBED_MESSAGE).toBe("ai-pos.signup-embed");
  });
});
