import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { useState } from "react";
import { afterEach, describe, expect, it } from "vitest";
import { AxizDatePicker, AxizDateRange } from "./AxizDatePicker";
import { formatDate, formatDateRange, formatDateTime, isValidDate, parseDate, parseDateInput } from "./dateFormat";

afterEach(() => {
  cleanup();
});

function Controlled({ initial = "2026-11-12", ...props }: { initial?: string; withTime?: boolean; min?: string; max?: string; disabledDates?: string[]; clearable?: boolean }) {
  const [value, setValue] = useState(initial);
  return (
    <div>
      <AxizDatePicker value={value} onChange={(event) => setValue(event.target.value)} {...props} />
      <output>{value}</output>
    </div>
  );
}

describe("date format", () => {
  it("keeps DD-MM-YYYY and rejects impossible or ambiguous dates", () => {
    expect(formatDate("2026-11-01")).toBe("01-11-2026");
    expect(formatDate("12-11-2026")).toBe("12-11-2026");
    expect(formatDate("2027-01-05")).toBe("05-01-2027");
    expect(formatDate("2026-12-31")).toBe("31-12-2026");
    expect(parseDate("12-11-2026")).toBe("2026-11-12");
    expect(parseDate("2026-11-12")).toBe("2026-11-12");
    expect(parseDate("11/12/2026")).toBeNull();
    expect(parseDate("31-02-2026")).toBeNull();
    expect(parseDate("31-04-2026")).toBeNull();
    expect(parseDate("29-02-2027")).toBeNull();
    expect(parseDate("29-02-2028")).toBe("2028-02-29");
    expect(parseDateInput("")).toBe("");
    expect(isValidDate("01-01-2026")).toBe(true);
    expect(isValidDate("2026-11-12T00:00:00.000Z")).toBe(false);
    expect(formatDate("2026-11-12T00:00:00.000Z")).toBe("12-11-2026");
    expect(formatDateRange("2026-11-01", "2026-11-12")).toBe("01-11-2026 – 12-11-2026");
  });

  it("formats an instant in the requested timezone without moving a date-only value", () => {
    expect(formatDateTime("2026-11-12", "Asia/Dubai")).toBe("12-11-2026");
    expect(formatDateTime("2026-01-01T00:00:00.000Z", "Asia/Dubai")).toBe("01-01-2026 04:00");
    expect(formatDateTime("2026-01-01T00:00:00.000Z", "America/New_York")).toBe("31-12-2025 19:00");
    expect(formatDateTime("2026-07-01T04:00:00.000Z", "America/New_York")).toBe("01-07-2026 00:00");
    expect(formatDateTime("2026-01-01T05:00:00.000Z", "America/New_York")).toBe("01-01-2026 00:00");
  });
});

function valueOf(element: HTMLElement): string {
  return (element as HTMLInputElement).value;
}

describe("AxizDatePicker", () => {
  it("shows DD-MM-YYYY and commits a typed date as ISO", () => {
    render(<Controlled />);
    const field = screen.getByRole("textbox");
    expect(valueOf(field)).toBe("12-11-2026");
    expect(field.getAttribute("placeholder")).toBe("DD-MM-YYYY");
    fireEvent.change(field, { target: { value: "01012026" } });
    expect(document.querySelector("output")?.textContent).toBe("2026-01-01");
  });

  it("does not commit an impossible day", () => {
    render(<Controlled />);
    const field = screen.getByRole("textbox");
    fireEvent.change(field, { target: { value: "31022026" } });
    expect(document.querySelector("output")?.textContent).toBe("2026-11-12");
    expect((field as HTMLInputElement).validationMessage).toBe("Enter the date as DD-MM-YYYY.");
  });

  it("selects a day from the calendar and moves to the next month", () => {
    render(<Controlled />);
    fireEvent.click(screen.getByRole("button", { name: "Open calendar" }));
    expect(screen.getByRole("dialog", { name: "Choose a date" })).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Next month" }));
    fireEvent.click(document.querySelector("[data-axiz-day='2026-12-31']") as HTMLButtonElement);
    expect(document.querySelector("output")?.textContent).toBe("2026-12-31");
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("disables dates outside min and max and dates on the blocked list", () => {
    render(<Controlled min="2026-11-10" max="2026-11-20" disabledDates={["2026-11-15"]} />);
    fireEvent.click(screen.getByRole("button", { name: "Open calendar" }));
    expect((document.querySelector("[data-axiz-day='2026-11-01']") as HTMLButtonElement).disabled).toBe(true);
    expect((document.querySelector("[data-axiz-day='2026-11-15']") as HTMLButtonElement).disabled).toBe(true);
    expect((document.querySelector("[data-axiz-day='2026-11-21']") as HTMLButtonElement).disabled).toBe(true);
    expect((document.querySelector("[data-axiz-day='2026-11-12']") as HTMLButtonElement).disabled).toBe(false);
  });

  it("clears an optional value and accepts a leap day", () => {
    render(<Controlled initial="2028-02-29" clearable />);
    expect(valueOf(screen.getByRole("textbox"))).toBe("29-02-2028");
    fireEvent.click(screen.getByRole("button", { name: "Open calendar" }));
    fireEvent.click(screen.getByRole("button", { name: "Clear" }));
    expect(document.querySelector("output")?.textContent).toBe("");
    expect(valueOf(screen.getByRole("textbox"))).toBe("");
  });

  it("keeps a time when the variant is datetime", () => {
    render(<Controlled initial="2026-11-12T14:30" withTime />);
    const field = screen.getByRole("textbox");
    expect(valueOf(field)).toBe("12-11-2026 14:30");
    expect(field.getAttribute("placeholder")).toBe("DD-MM-YYYY HH:mm");
    fireEvent.change(field, { target: { value: "010120260930" } });
    expect(document.querySelector("output")?.textContent).toBe("2026-01-01T09:30");
  });

  it("closes from the keyboard and follows Arabic direction", () => {
    render(
      <div dir="rtl">
        <AxizDatePicker value="2026-11-12" onChange={() => undefined} />
      </div>,
    );
    fireEvent.click(screen.getByRole("button", { name: "Open calendar" }));
    expect(screen.getByRole("dialog").getAttribute("dir")).toBe("rtl");
    act(() => {
      document.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", bubbles: true }));
    });
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("reports a range whose start is after its end", () => {
    render(<AxizDateRange from="2026-11-12" to="2026-11-01" onFromChange={() => undefined} onToChange={() => undefined} />);
    expect(screen.getByRole("alert").textContent).toBe("From is after To.");
    const fields = screen.getAllByRole("textbox");
    expect(valueOf(fields[0]!)).toBe("12-11-2026");
    expect(valueOf(fields[1]!)).toBe("01-11-2026");
  });
});
