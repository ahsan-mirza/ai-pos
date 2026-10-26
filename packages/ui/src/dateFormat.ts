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

/** Negative when `iso` is before `bound`. Date-only bounds ignore a clock on the same day. */
export function compareIso(iso: string, bound: string): number {
  const day = iso.slice(0, 10).localeCompare(bound.slice(0, 10));
  if (day !== 0) return day;
  if (iso.length <= 10 || bound.length <= 10) return 0;
  return iso.localeCompare(bound);
}
