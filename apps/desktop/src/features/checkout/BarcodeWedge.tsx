import { useEffect } from "react";

interface BarcodeWedgeProps {
  onScan: (barcode: string) => void;
}

/**
 * Captures USB keyboard-wedge scans while focus is outside any text field. Scanners type faster than 50 ms
 * per key and finish with Enter; scans into the search field are handled by that field's own Enter key.
 */
export function BarcodeWedge({ onScan }: BarcodeWedgeProps) {
  useEffect(() => {
    let buffer = "";
    let lastAt = 0;

    const onKeyDown = (event: KeyboardEvent) => {
      const target = event.target;
      if (target instanceof HTMLElement && target.closest("input, textarea, select, [contenteditable='true']")) return;

      const now = Date.now();
      if (now - lastAt > 50) buffer = "";
      lastAt = now;

      if (event.key === "Enter") {
        if (buffer.length >= 4) {
          onScan(buffer);
          event.preventDefault();
        }
        buffer = "";
        return;
      }

      if (event.key.length === 1 && !event.metaKey && !event.ctrlKey && !event.altKey) {
        buffer += event.key;
      }
    };

    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [onScan]);

  return null;
}
