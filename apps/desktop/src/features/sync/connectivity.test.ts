import { describe, expect, it } from "vitest";
import { endpointKind, linkMessage, linkState, mayProbe, NO_CACHED_PIN, OFFLINE_NOTICE, unlockFailureMessage } from "./connectivity";

describe("server connectivity", () => {
  it("allows localhost only as an explicit development endpoint and never rewrites a remote URL", () => {
    expect(endpointKind("http://localhost:8000", false)).toBe("development");
    expect(endpointKind("http://localhost:8000", true)).toBe("insecure");
    expect(endpointKind("https://pos.example.com", true)).toBe("https");
    expect(endpointKind("http://pos.example.com", false)).toBe("insecure");
    expect(endpointKind("http://not-activated.invalid", false)).toBe("unactivated");
    expect(mayProbe("development")).toBe(true);
    expect(mayProbe("https")).toBe(true);
    expect(mayProbe("insecure")).toBe(false);
    expect(linkState({ reachable: false, syncing: false, activated: true })).toBe("offline");
    expect(linkState({ reachable: false, syncing: true, activated: true })).toBe("reconnecting");
    expect(linkState({ reachable: true, syncing: false, activated: false })).toBe("not_activated");
    expect(linkMessage("offline", "https")).toBe(OFFLINE_NOTICE);
    expect(OFFLINE_NOTICE).not.toContain("localhost:8000");
    expect(unlockFailureMessage(new Error("Cannot reach the API at http://localhost:8000. Check that the backend is running."))).toBe(NO_CACHED_PIN);
    expect(unlockFailureMessage(new Error("Invalid username or credentials."))).toBe("Invalid username or credentials.");
    expect(linkMessage("offline", "insecure")).toContain("not HTTPS");
  });
});
