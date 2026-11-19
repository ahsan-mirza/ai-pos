import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { GetStartedSection } from "./GetStartedSection";

afterEach(() => {
  cleanup();
  delete (window as Window & { dataLayer?: unknown[] }).dataLayer;
});

describe("signup wizard", () => {
  it("does not load the signup application until it is opened, and closing does not track again", () => {
    render(<GetStartedSection />);
    expect(document.querySelector("iframe")).toBeNull();

    fireEvent.click(screen.getByRole("button", { name: "Get Started Free" }));

    const frame = document.querySelector("iframe");
    expect(screen.getByRole("dialog")).toBeTruthy();
    expect(frame?.getAttribute("src")).toContain("embed=1");
    expect(window.dataLayer).toEqual([{ event: "click_get_started", page_path: "/" }]);

    fireEvent.click(screen.getByRole("button", { name: "Close" }));

    expect(screen.queryByRole("dialog")).toBeNull();
    expect(document.querySelector("iframe")).toBeNull();
    expect(window.dataLayer).toHaveLength(1);
  });
});
