/** Visible date format for every admin and console date field. Stored values stay ISO. */
export const DATE_PLACEHOLDER = "DD-MM-YYYY";
export const DATETIME_PLACEHOLDER = "DD-MM-YYYY HH:mm";

const ISO_DATE = /^(\d{4})-(\d{2})-(\d{2})(?:[T ](\d{2}):(\d{2}))?/;

/** `YYYY-MM-DD` or `YYYY-MM-DDTHH:mm` (seconds ignored) → `DD-MM-YYYY` or `DD-MM-YYYY HH:mm`. */
export function isoToDisplay(value: string, withTime = false): string {
  const match = ISO_DATE.exec(value.trim());
  if (!match?.[1] || !match[2] || !match[3]) return "";
  const date = `${match[3]}-${match[2]}-${match[1]}`;
  if (withTime && match[4] && match[5]) return `${date} ${match[4]}:${match[5]}`;
  return date;
}

function daysInMonth(year: number, month: number): number {
  return new Date(year, month, 0).getDate();
}

function calendarIso(day: string, month: string, year: string): string | null {
  const date = Number(day);
  const monthNumber = Number(month);
  const yearNumber = Number(year);
  if (monthNumber < 1 || monthNumber > 12 || date < 1 || yearNumber < 1000 || yearNumber > 9999) return null;
  if (date > daysInMonth(yearNumber, monthNumber)) return null;
  return `${year}-${month}-${day}`;
}

/**
 * A finished display value becomes `YYYY-MM-DD` or `YYYY-MM-DDTHH:mm`.
 * `""` means cleared. `null` means the text is still incomplete or not a real date.
 */
export function displayToIso(text: string, withTime = false): string | null {
  const trimmed = text.trim();
  if (!trimmed) return "";
  const match = withTime
    ? /^(\d{2})-(\d{2})-(\d{4}) (\d{2}):(\d{2})$/.exec(trimmed)
    : /^(\d{2})-(\d{2})-(\d{4})$/.exec(trimmed);
  if (!match?.[1] || !match[2] || !match[3]) return null;
  const date = calendarIso(match[1], match[2], match[3]);
  if (!date) return null;
  if (!withTime) return date;
  const hourText = match[4];
  const minuteText = match[5];
  if (!hourText || !minuteText) return null;
  const hour = Number(hourText);
  const minute = Number(minuteText);
  if (hour > 23 || minute > 59) return null;
  return `${date}T${hourText}:${minuteText}`;
}

/** Keep dashes (and the time colon) in place while the user types or pastes. */
export function maskDateInput(raw: string, withTime = false): string {
  const trimmed = raw.trim();
  const pasted = ISO_DATE.exec(trimmed);
  if (pasted && trimmed.indexOf("-") === 4) return isoToDisplay(trimmed, withTime);
  const digits = trimmed.replace(/\D/g, "").slice(0, withTime ? 12 : 8);
  let text = digits.slice(0, 2);
  if (digits.length > 2) text += `-${digits.slice(2, 4)}`;
  if (digits.length > 4) text += `-${digits.slice(4, 8)}`;
  if (withTime && digits.length > 8) text += ` ${digits.slice(8, 10)}`;
  if (withTime && digits.length > 10) text += `:${digits.slice(10, 12)}`;
  return text;
}

/** A calendar date, with no clock and no timezone conversion. `null` when the text is empty or not a real date. */
export function parseDate(value: string): string | null {
  const trimmed = value.trim();
  if (!trimmed) return null;
  const iso = /^(\d{4})-(\d{2})-(\d{2})$/.exec(trimmed);
  if (iso?.[1] && iso[2] && iso[3]) return calendarIso(iso[3], iso[2], iso[1]);
  const display = displayToIso(trimmed, false);
  return display ? display : null;
}

/** What the user typed. `""` is cleared, `null` is incomplete or impossible. Never reads MM-DD-YYYY. */
export function parseDateInput(value: string, withTime = false): string | null {
  return displayToIso(value, withTime);
}

/** True for a real `YYYY-MM-DD` or `DD-MM-YYYY`. A timestamp is not a date-only value. */
export function isValidDate(value: string): boolean {
  return parseDate(value) !== null;
}

/**
 * `YYYY-MM-DD` or `DD-MM-YYYY` → `DD-MM-YYYY`.
 * The calendar date in the string is used as written, so a date-only value cannot shift across midnight.
 */
export function formatDate(value: string): string {
  const trimmed = value.trim();
  const parsed = parseDate(trimmed);
  if (parsed) return isoToDisplay(parsed);
  const prefix = /^(\d{4})-(\d{2})-(\d{2})T/.exec(trimmed);
  if (prefix?.[1] && prefix[2] && prefix[3] && calendarIso(prefix[3], prefix[2], prefix[1])) {
    return `${prefix[3]}-${prefix[2]}-${prefix[1]}`;
  }
  return "";
}

/**
 * An instant → `DD-MM-YYYY HH:mm` in `timeZone`.
 * Omit `timeZone` to use the viewer's timezone. Date-only strings are not converted.
 */
export function formatDateTime(value: string | Date, timeZone?: string): string {
  if (typeof value === "string" && /^\d{4}-\d{2}-\d{2}$/.test(value.trim())) return formatDate(value);
  const date = value instanceof Date ? value : new Date(value);
  if (Number.isNaN(date.getTime())) return "";
  const parts = new Intl.DateTimeFormat("en-GB", {
    timeZone,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hourCycle: "h23",
  }).formatToParts(date);
  const part = (type: Intl.DateTimeFormatPartTypes) => parts.find((item) => item.type === type)?.value ?? "";
  let hour = part("hour");
  if (hour === "24") hour = "00";
  const day = part("day");
  const month = part("month");
  const year = part("year");
  const minute = part("minute");
  if (!day || !month || !year || !hour || !minute) return "";
  return `${day}-${month}-${year} ${hour}:${minute}`;
}

/** `01-11-2026 – 12-11-2026`. Either side may be empty. */
export function formatDateRange(from: string, to: string): string {
  const start = formatDate(from);
  const end = formatDate(to);
  if (start && end) return `${start} – ${end}`;
  return start || end;
}

/** Negative when `iso` is before `bound`. Date-only bounds ignore a clock on the same day. */
export function compareIso(iso: string, bound: string): number {
  const day = iso.slice(0, 10).localeCompare(bound.slice(0, 10));
  if (day !== 0) return day;
  if (iso.length <= 10 || bound.length <= 10) return 0;
  return iso.localeCompare(bound);
}
