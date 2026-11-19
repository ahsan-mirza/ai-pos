/** Turns [label](/path) into an anchor. Other text is escaped. Paths stay on this site. */

const LINK = /\[([^\]]+)\]\((\s*\/(?!\/)[^)\s]*)\)/g;

export function escapeHtml(value: string): string {
  return value.replaceAll("&", "&amp;").replaceAll('"', "&quot;").replaceAll("<", "&lt;");
}

export function safePath(path: string): string | null {
  const href = path.trim();
  if (!href.startsWith("/") || href.startsWith("//") || href.includes("\\") || /[\s"'<>]/.test(href)) return null;
  return href;
}

export function renderRichHtml(value: string): string {
  const parts: string[] = [];
  let last = 0;
  for (const match of value.matchAll(LINK)) {
    const index = match.index ?? 0;
    parts.push(escapeHtml(value.slice(last, index)));
    const href = safePath(match[2] ?? "");
    parts.push(href ? `<a href="${escapeHtml(href)}">${escapeHtml(match[1] ?? "")}</a>` : escapeHtml(match[0]));
    last = index + match[0].length;
  }
  parts.push(escapeHtml(value.slice(last)));
  return parts.join("");
}

export interface RichPiece {
  text?: string;
  href?: string;
  label?: string;
}

export function richPieces(value: string): RichPiece[] {
  const pieces: RichPiece[] = [];
  let last = 0;
  for (const match of value.matchAll(LINK)) {
    const index = match.index ?? 0;
    if (index > last) pieces.push({ text: value.slice(last, index) });
    const href = safePath(match[2] ?? "");
    if (href) pieces.push({ href, label: match[1] ?? "" });
    else pieces.push({ text: match[0] });
    last = index + match[0].length;
  }
  if (last < value.length) pieces.push({ text: value.slice(last) });
  return pieces;
}
