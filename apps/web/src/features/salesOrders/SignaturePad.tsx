import { actionHoverClass } from "@ai-pos/ui";
import { Eraser } from "lucide-react";
import { useEffect, useRef, useState } from "react";

/** A finger / stylus signature box. `onChange` receives a PNG data URL, or null once cleared. */
export function SignaturePad({ onChange }: { onChange: (dataUrl: string | null) => void }) {
  const canvas = useRef<HTMLCanvasElement | null>(null);
  const drawing = useRef(false);
  const [signed, setSigned] = useState(false);

  useEffect(() => {
    const element = canvas.current;
    if (!element) return;
    const ratio = window.devicePixelRatio || 1;
    const { width, height } = element.getBoundingClientRect();
    element.width = Math.round(width * ratio);
    element.height = Math.round(height * ratio);
    const context = element.getContext("2d");
    if (!context) return;
    context.scale(ratio, ratio);
    context.lineWidth = 2.2;
    context.lineCap = "round";
    context.lineJoin = "round";
    context.strokeStyle = "#222026";
  }, []);

  const point = (event: React.PointerEvent<HTMLCanvasElement>) => {
    const rect = event.currentTarget.getBoundingClientRect();
    return { x: event.clientX - rect.left, y: event.clientY - rect.top };
  };

  const start = (event: React.PointerEvent<HTMLCanvasElement>) => {
    const context = event.currentTarget.getContext("2d");
    if (!context) return;
    event.currentTarget.setPointerCapture(event.pointerId);
    drawing.current = true;
    const { x, y } = point(event);
    context.beginPath();
    context.moveTo(x, y);
  };

  const move = (event: React.PointerEvent<HTMLCanvasElement>) => {
    if (!drawing.current) return;
    const context = event.currentTarget.getContext("2d");
    if (!context) return;
    const { x, y } = point(event);
    context.lineTo(x, y);
    context.stroke();
  };

  const end = (event: React.PointerEvent<HTMLCanvasElement>) => {
    if (!drawing.current) return;
    drawing.current = false;
    setSigned(true);
    onChange(event.currentTarget.toDataURL("image/png"));
  };

  const clear = () => {
    const element = canvas.current;
    const context = element?.getContext("2d");
    if (!element || !context) return;
    context.save();
    context.setTransform(1, 0, 0, 1, 0, 0);
    context.clearRect(0, 0, element.width, element.height);
    context.restore();
    setSigned(false);
    onChange(null);
  };

  return (
    <div>
      <div className="relative">
        <canvas
          ref={canvas}
          aria-label="Signature"
          onPointerDown={start}
          onPointerMove={move}
          onPointerUp={end}
          onPointerLeave={end}
          className="h-40 w-full touch-none rounded-2xl border border-dashed border-line bg-surface"
        />
        {signed ? null : (
          <span className="pointer-events-none absolute inset-0 flex items-center justify-center text-sm text-charcoal/40">
            Sign here
          </span>
        )}
      </div>
      <button
        type="button"
        onClick={clear}
        className={`mt-2 inline-flex items-center gap-1.5 rounded-full px-2 py-1 text-xs font-medium text-charcoal/60 ${actionHoverClass("danger")}`}
      >
        <Eraser size={13} aria-hidden="true" /> Clear
      </button>
    </div>
  );
}
