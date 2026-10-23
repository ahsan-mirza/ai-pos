import { useEffect, useRef } from "react";

function project(x: number, y: number, z: number, yaw: number, pitch: number): [number, number] {
  const x1 = x * Math.cos(yaw) - z * Math.sin(yaw);
  const z1 = x * Math.sin(yaw) + z * Math.cos(yaw);
  const y1 = y * Math.cos(pitch) - z1 * Math.sin(pitch);
  const z2 = y * Math.sin(pitch) + z1 * Math.cos(pitch);
  const scale = 1.9 / (3.5 + z2);
  return [x1 * scale, -y1 * scale];
}

export function RegisterCanvas({ totalLabel }: { totalLabel: string }) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const labelRef = useRef(totalLabel);
  labelRef.current = totalLabel;

  useEffect(() => {
    const canvas = canvasRef.current;
    const context = canvas?.getContext("2d");
    if (!canvas || !context) return undefined;
    const ctx = context;
    const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    const target = { x: 0, y: 0 };
    const current = { x: 0, y: 0 };
    let frame = 0;
    let raf = 0;

    const draw = () => {
      const bounds = canvas.getBoundingClientRect();
      const dpr = Math.min(window.devicePixelRatio || 1, 2);
      const width = Math.max(1, bounds.width);
      const height = Math.max(1, bounds.height);
      if (canvas.width !== Math.floor(width * dpr) || canvas.height !== Math.floor(height * dpr)) {
        canvas.width = Math.floor(width * dpr);
        canvas.height = Math.floor(height * dpr);
      }
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      ctx.clearRect(0, 0, width, height);

      if (!reduce) {
        current.x += (target.x - current.x) * 0.08;
        current.y += (target.y - current.y) * 0.08;
      } else {
        current.x = target.x;
        current.y = target.y;
      }
      const yaw = current.x * 0.42;
      const pitch = -0.22 + current.y * 0.16;
      const pulse = reduce ? 0.7 : 0.55 + Math.sin(frame / 42) * 0.12;
      const wide = width >= 900;
      const unit = Math.min(width, height) * (wide ? 0.72 : 0.5);
      const originX = wide ? width * 0.74 : width * 0.62;
      const originY = wide ? height * 0.42 : height * 0.22;
      const toScreen = (x: number, y: number, z: number): [number, number] => {
        const [px, py] = project(x, y, z, yaw, pitch);
        return [originX + px * unit, originY + py * unit];
      };

      const glow = ctx.createRadialGradient(originX, originY, 20, originX, originY, unit * 0.55);
      glow.addColorStop(0, `rgba(6,182,212,${0.22 * pulse})`);
      glow.addColorStop(0.5, "rgba(16,185,129,0.06)");
      glow.addColorStop(1, "rgba(9,13,22,0)");
      ctx.fillStyle = glow;
      ctx.fillRect(0, 0, width, height);

      const face = (points: [number, number, number][], fill: string, stroke: string) => {
        ctx.beginPath();
        points.forEach(([x, y, z], index) => {
          const [sx, sy] = toScreen(x, y, z);
          if (index === 0) ctx.moveTo(sx, sy);
          else ctx.lineTo(sx, sy);
        });
        ctx.closePath();
        ctx.fillStyle = fill;
        ctx.fill();
        ctx.strokeStyle = stroke;
        ctx.lineWidth = 1.25;
        ctx.stroke();
      };

      face(
        [
          [-0.78, 0.16, -0.28],
          [0.78, 0.16, -0.28],
          [0.78, 0.26, -0.28],
          [-0.78, 0.26, -0.28],
        ],
        "rgba(8,16,28,0.96)",
        "rgba(6,182,212,0.35)",
      );
      face(
        [
          [-0.78, 0.16, 0.48],
          [0.78, 0.16, 0.48],
          [0.78, 0.16, -0.28],
          [-0.78, 0.16, -0.28],
        ],
        "rgba(16,185,129,0.12)",
        "rgba(16,185,129,0.4)",
      );
      face(
        [
          [-0.64, -0.46, -0.02],
          [0.64, -0.46, -0.02],
          [0.64, 0.1, -0.02],
          [-0.64, 0.1, -0.02],
        ],
        "rgba(12,22,36,0.94)",
        "rgba(255,255,255,0.14)",
      );

      const screen: [number, number, number][] = [
        [-0.5, -0.36, 0.08],
        [0.5, -0.36, 0.08],
        [0.5, 0.0, 0.08],
        [-0.5, 0.0, 0.08],
      ];
      const projected = screen.map(([x, y, z]) => toScreen(x, y, z));
      const topLeft = projected[0] ?? [originX, originY];
      const bottomRight = projected[2] ?? topLeft;
      ctx.beginPath();
      projected.forEach((point, index) => {
        if (!point) return;
        const [sx, sy] = point;
        if (index === 0) ctx.moveTo(sx, sy);
        else ctx.lineTo(sx, sy);
      });
      ctx.closePath();
      const shade = ctx.createLinearGradient(topLeft[0], topLeft[1], bottomRight[0], bottomRight[1]);
      shade.addColorStop(0, "rgba(6,182,212,0.38)");
      shade.addColorStop(1, "rgba(16,185,129,0.16)");
      ctx.fillStyle = shade;
      ctx.fill();
      ctx.strokeStyle = "rgba(103,232,249,0.7)";
      ctx.stroke();

      const corners = projected.filter((point): point is [number, number] => point !== undefined);
      const left = Math.min(...corners.map((point) => point[0]));
      const top = Math.min(...corners.map((point) => point[1]));
      ctx.fillStyle = "#e8fff8";
      ctx.font = "600 13px Archivo, sans-serif";
      ctx.fillText("AxizPOS", left + 16, top + 26);
      ctx.fillStyle = "#67e8f9";
      ctx.font = "600 22px Archivo, sans-serif";
      ctx.fillText(labelRef.current, left + 16, top + 52);

      frame += 1;
      if (!reduce) raf = requestAnimationFrame(draw);
    };

    const onMove = (event: PointerEvent) => {
      const bounds = canvas.getBoundingClientRect();
      if (bounds.width === 0 || bounds.height === 0) return;
      const inside =
        event.clientX >= bounds.left &&
        event.clientX <= bounds.right &&
        event.clientY >= bounds.top &&
        event.clientY <= bounds.bottom;
      target.x = inside ? ((event.clientX - bounds.left) / bounds.width) * 2 - 1 : 0;
      target.y = inside ? ((event.clientY - bounds.top) / bounds.height) * 2 - 1 : 0;
      if (reduce) draw();
    };

    window.addEventListener("pointermove", onMove);
    draw();
    return () => {
      cancelAnimationFrame(raf);
      window.removeEventListener("pointermove", onMove);
    };
  }, [totalLabel]);

  return <canvas ref={canvasRef} className="absolute inset-0 hidden h-full w-full lg:block" aria-hidden="true" />;
}
