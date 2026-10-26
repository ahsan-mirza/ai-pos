import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { GhostButton, PrimaryButton } from "../components/ui";
import { MailPage } from "./MailPage";

const mailbox = {
  enabled: true,
  host: "mail.spacemail.com",
  port: 465,
  security: "ssl" as const,
  username: "info@axizpos.com",
  password_set: true,
  from_address: "info@axizpos.com",
  from_name: "AxizPos",
};

const { get, patch, post } = vi.hoisted(() => ({
  get: vi.fn(),
  patch: vi.fn(),
  post: vi.fn(),
}));

vi.mock("../lib/api", () => {
  class ConsoleError extends Error {
    readonly status: number;
    readonly code: string | null;
    readonly details: unknown;
    constructor(message: string, status: number, code: string | null = null, details: unknown = null) {
      super(message);
      this.status = status;
      this.code = code;
      this.details = details;
    }
  }
  return {
    ConsoleError,
    api: {
      get: (...args: unknown[]) => get(...args),
      patch: (...args: unknown[]) => patch(...args),
      post: (...args: unknown[]) => post(...args),
    },
    errorText: (caught: unknown, fallback: string) =>
      caught instanceof Error && caught.message ? caught.message : fallback,
  };
});

vi.mock("../lib/session", () => ({
  useSession: () => ({
    operator: {
      id: "op",
      email: "admin@axizpos.com",
      full_name: "Admin",
      role: "ADMIN",
      is_active: true,
      last_login_at: null,
    },
    status: "signed-in",
    signIn: vi.fn(),
    signOut: vi.fn(),
  }),
}));

function deferred<T>() {
  let resolve: (value: T) => void = () => undefined;
  let reject: (reason?: unknown) => void = () => undefined;
  const promise = new Promise<T>((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { promise, resolve, reject };
}

async function openMailbox() {
  render(<MailPage />);
  expect(await screen.findByDisplayValue("mail.spacemail.com")).toBeTruthy();
  fireEvent.change(screen.getByLabelText(/Reason/), { target: { value: "Updated mailbox" } });
}

function saveButton() {
  return screen.getByRole("button", { name: "Save" });
}

function testButton() {
  return screen.getByRole("button", { name: "Send test" });
}

describe("email settings actions", () => {
  beforeEach(() => {
    get.mockReset();
    patch.mockReset();
    post.mockReset();
    get.mockResolvedValue(mailbox);
    patch.mockResolvedValue(mailbox);
    post.mockResolvedValue({ sent: true });
  });

  afterEach(() => {
    cleanup();
  });

  it("shows Saving... until the mailbox request succeeds", async () => {
    const pending = deferred<typeof mailbox>();
    patch.mockReturnValue(pending.promise);
    await openMailbox();

    fireEvent.click(saveButton());

    const saving = screen.getByRole("button", { name: "Saving..." });
    expect(saving.getAttribute("aria-busy")).toBe("true");
    expect(saving.querySelector(".animate-spin")).toBeTruthy();
    expect(saving.hasAttribute("disabled")).toBe(true);
    expect(patch).toHaveBeenCalledTimes(1);
    expect(screen.queryByText("Saved.")).toBeNull();

    pending.resolve(mailbox);
    await waitFor(() => expect(screen.getByRole("button", { name: "Save" }).getAttribute("aria-busy")).toBeNull());
    expect(screen.getByRole("button", { name: "Save" }).querySelector(".animate-spin")).toBeNull();
    expect(screen.getByRole("status").textContent).toBe("Saved.");
  });

  it("restores Save after the mailbox request fails", async () => {
    const pending = deferred<typeof mailbox>();
    patch.mockReturnValue(pending.promise);
    await openMailbox();
    fireEvent.click(saveButton());
    pending.reject(new Error("The mail server rejected the mailbox."));
    await waitFor(() => expect(screen.getByRole("button", { name: "Save" }).getAttribute("aria-busy")).toBeNull());
    expect(screen.getByRole("alert").textContent).toContain("The mail server rejected the mailbox.");
    expect(screen.queryByText("Saved.")).toBeNull();
  });

  it("shows Sending test... until the test request finishes", async () => {
    const pending = deferred<{ sent: boolean }>();
    post.mockReturnValue(pending.promise);
    await openMailbox();

    fireEvent.click(testButton());

    const sending = screen.getByRole("button", { name: "Sending test..." });
    expect(sending.getAttribute("aria-busy")).toBe("true");
    expect(sending.querySelector(".animate-spin")).toBeTruthy();
    expect(post).toHaveBeenCalledTimes(1);
    expect(screen.queryByText("Test sent.")).toBeNull();

    pending.resolve({ sent: true });
    await waitFor(() => expect(screen.getByRole("button", { name: "Send test" }).getAttribute("aria-busy")).toBeNull());
    expect(screen.getByRole("status").textContent).toBe("Test sent.");
  });

  it("restores Send test after the test request fails", async () => {
    const pending = deferred<{ sent: boolean }>();
    post.mockReturnValue(pending.promise);
    await openMailbox();
    fireEvent.click(testButton());
    pending.reject(new Error("The mail server rejected the test."));
    await waitFor(() => expect(screen.getByRole("button", { name: "Send test" }).getAttribute("aria-busy")).toBeNull());
    expect(screen.getByRole("alert").textContent).toContain("The mail server rejected the test.");
    expect(screen.queryByText("Test sent.")).toBeNull();
  });

  it("ignores a second click while the same request is still running", async () => {
    const pending = deferred<typeof mailbox>();
    patch.mockReturnValue(pending.promise);
    await openMailbox();
    const button = saveButton();
    fireEvent.click(button);
    fireEvent.click(button);
    expect(patch).toHaveBeenCalledTimes(1);
    pending.resolve(mailbox);
    await waitFor(() => expect(saveButton().getAttribute("aria-busy")).toBeNull());
  });

  it("keeps Save and Send test on separate loading states", async () => {
    const saving = deferred<typeof mailbox>();
    const sending = deferred<{ sent: boolean }>();
    patch.mockReturnValue(saving.promise);
    post.mockReturnValue(sending.promise);
    await openMailbox();

    fireEvent.click(saveButton());
    expect(screen.getByRole("button", { name: "Saving..." }).getAttribute("aria-busy")).toBe("true");
    expect(testButton().getAttribute("aria-busy")).toBeNull();
    expect(screen.getByLabelText("Outgoing server").hasAttribute("disabled")).toBe(false);

    fireEvent.click(testButton());
    expect(post).toHaveBeenCalledTimes(1);
    expect(screen.getByRole("button", { name: "Sending test..." }).getAttribute("aria-busy")).toBe("true");
    expect(screen.getByRole("button", { name: "Saving..." }).getAttribute("aria-busy")).toBe("true");

    saving.resolve(mailbox);
    sending.resolve({ sent: true });
    await waitFor(() => expect(saveButton().getAttribute("aria-busy")).toBeNull());
    expect(screen.getByRole("button", { name: "Send test" }).getAttribute("aria-busy")).toBeNull();
  });

  it("keeps Save disabled until the reason is long enough and does not send an invalid test", async () => {
    await openMailbox();
    fireEvent.change(screen.getByLabelText(/Reason/), { target: { value: "no" } });
    expect(saveButton().hasAttribute("disabled")).toBe(true);
    fireEvent.click(saveButton());
    expect(patch).not.toHaveBeenCalled();

    fireEvent.change(screen.getByLabelText("Send a test to"), { target: { value: "not-an-email" } });
    fireEvent.click(testButton());
    expect(post).not.toHaveBeenCalled();
    expect(testButton().getAttribute("aria-busy")).toBeNull();
    expect(screen.getByText("Enter an email address to send the test to.")).toBeTruthy();
  });

  it("exposes a busy button to the keyboard and ignores activation while loading", async () => {
    const pending = deferred<typeof mailbox>();
    patch.mockReturnValue(pending.promise);
    await openMailbox();
    const button = saveButton();
    button.focus();
    expect(document.activeElement).toBe(button);
    expect(button.className).toContain("focus-visible:ring-2");
    fireEvent.keyDown(button, { key: "Enter" });
    fireEvent.click(button);
    expect(button.getAttribute("aria-busy")).toBe("true");
    expect(button.hasAttribute("disabled")).toBe(true);
    fireEvent.click(button);
    expect(patch).toHaveBeenCalledTimes(1);
    pending.resolve(mailbox);
    await waitFor(() => expect(saveButton().getAttribute("aria-busy")).toBeNull());
  });

  it("does not announce success when the test response says it was not sent", async () => {
    post.mockResolvedValue({ sent: false });
    await openMailbox();
    fireEvent.click(testButton());
    await waitFor(() => expect(testButton().getAttribute("aria-busy")).toBeNull());
    expect(screen.getByRole("alert").textContent).toContain("The test email was not sent.");
    expect(screen.queryByText("Test sent.")).toBeNull();
  });
});

describe("shared buttons", () => {
  afterEach(() => cleanup());

  it("keeps the existing labels when loading is not used", () => {
    render(
      <>
        <PrimaryButton>Save</PrimaryButton>
        <GhostButton>Cancel</GhostButton>
      </>,
    );
    expect(screen.getByRole("button", { name: "Save" }).getAttribute("aria-busy")).toBeNull();
    expect(screen.getByRole("button", { name: "Cancel" }).textContent).toBe("Cancel");
    expect(screen.getByRole("button", { name: "Save" }).querySelector(".animate-spin")).toBeNull();
  });

  it("places the spinner before or after the loading label", () => {
    const { rerender } = render(
      <PrimaryButton loading loadingText="Saving...">
        Save
      </PrimaryButton>,
    );
    const leading = screen.getByRole("button", { name: "Saving..." });
    const leadingSpinner = leading.querySelector(".animate-spin");
    expect(leadingSpinner).toBeTruthy();
    expect(leading.innerHTML.indexOf("animate-spin")).toBeLessThan(leading.innerHTML.indexOf("Saving..."));

    rerender(
      <GhostButton loading loadingText="Working..." spinnerPosition="trailing">
        Work
      </GhostButton>,
    );
    const trailing = screen.getByRole("button", { name: "Working..." });
    expect(trailing.innerHTML.indexOf("Working...")).toBeLessThan(trailing.innerHTML.lastIndexOf("animate-spin"));
    fireEvent.click(trailing);
  });
});
