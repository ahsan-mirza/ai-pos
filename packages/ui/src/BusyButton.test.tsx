import { act, fireEvent, render, screen } from "@testing-library/react";
import { useState } from "react";
import { describe, expect, it, vi } from "vitest";
import { AsyncButton, BusyButton } from "./BusyButton";

describe("BusyButton", () => {
  it("shows the spinner label and ignores another click", () => {
    const onClick = vi.fn();
    render(
      <BusyButton loading loadingText="Saving..." onClick={onClick}>
        Save
      </BusyButton>,
    );
    const button = screen.getByRole("button", { name: "Saving..." });
    expect(button.getAttribute("aria-busy")).toBe("true");
    expect(button.hasAttribute("disabled")).toBe(true);
    expect(button.textContent).toContain("Save");
    fireEvent.click(button);
    expect(onClick).not.toHaveBeenCalled();
  });

  it("returns to the idle label after the request fails and leaves the other button alone", async () => {
    function Pair() {
      const [failed, setFailed] = useState(false);
      return (
        <>
          <AsyncButton
            loadingText="Saving..."
            onClick={async () => {
              try {
                throw new Error("The settings were not saved.");
              } catch {
                setFailed(true);
              }
            }}
          >
            Save
          </AsyncButton>
          <AsyncButton loadingText="Thinking..." onClick={async () => undefined}>
            Ask
          </AsyncButton>
          {failed ? <p role="alert">The settings were not saved.</p> : null}
        </>
      );
    }
    render(<Pair />);
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "Save" }));
    });
    expect(screen.getByRole("alert").textContent).toContain("The settings were not saved.");
    expect(screen.getByRole("button", { name: "Save" }).hasAttribute("disabled")).toBe(false);
    expect(screen.getByRole("button", { name: "Save" }).hasAttribute("aria-busy")).toBe(false);
    expect(screen.getByRole("button", { name: "Ask" }).hasAttribute("disabled")).toBe(false);
  });

  it("runs one request until it settles", async () => {
    let release: () => void = () => undefined;
    const gate = new Promise<void>((resolve) => {
      release = resolve;
    });
    const work = vi.fn(() => gate);
    render(
      <AsyncButton loadingText="Adding FAQ..." onClick={work}>
        Add FAQ
      </AsyncButton>,
    );
    const button = screen.getByRole("button", { name: "Add FAQ" });
    fireEvent.click(button);
    fireEvent.click(button);
    expect(work).toHaveBeenCalledTimes(1);
    expect(screen.getByRole("button", { name: "Adding FAQ..." }).getAttribute("aria-busy")).toBe("true");
    await act(async () => {
      release();
      await gate;
    });
    expect(screen.getByRole("button", { name: "Add FAQ" }).hasAttribute("disabled")).toBe(false);
  });
});