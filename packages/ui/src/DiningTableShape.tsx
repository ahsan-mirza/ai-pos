import type { CSSProperties, ReactNode } from "react";

export type TableShape = "square" | "round" | "rect";

export interface DiningTableShapeProps {
  shape: TableShape;
  seats: number;
  /** Footprint in pixels, chairs included. */
  width: number;
  height: number;
  /** Chairs drawn as taken (guests seated), filled from the first chair. */
  occupied?: number;
  topClassName?: string;
  chairClassName?: string;
  occupiedChairClassName?: string;
  /** Label and status, centred on the tabletop. */
  children?: ReactNode;
}

interface Chair {
  left: number;
  top: number;
  width: number;
  height: number;
  rotate: number;
}

type Side = "top" | "bottom" | "left" | "right";
const SIDES: Side[] = ["top", "bottom", "left", "right"];

/** Grid cells (width x depth) that fit this many chairs comfortably around a table of this shape. */
export function tableFootprint(shape: TableShape, seats: number): { w: number; h: number } {
  if (shape === "rect") return { w: Math.max(3, Math.ceil(Math.max(seats - 2, 2) / 2) + 1), h: 2 };
  if (seats <= 4) return { w: 2, h: 2 };
  if (seats <= 8) return { w: 3, h: 3 };
  return { w: 4, h: 4 };
}

/** Seats per side: each chair goes to the side with the most room left, long sides first. */
export function chairsPerSide(seats: number, topWidth: number, topHeight: number): Record<Side, number> {
  const counts: Record<Side, number> = { top: 0, bottom: 0, left: 0, right: 0 };
  const length = (side: Side) => (side === "top" || side === "bottom" ? topWidth : topHeight);
  for (let seat = 0; seat < seats; seat += 1) {
    let best: Side = "top";
    let room = -1;
    for (const side of SIDES) {
      const free = length(side) / (counts[side] + 1);
      if (free > room + 0.001) {
        best = side;
        room = free;
      }
    }
    counts[best] += 1;
  }
  return counts;
}

function squareChairs(seats: number, width: number, height: number, depth: number, inset: number): Chair[] {
  const topWidth = width - inset * 2;
  const topHeight = height - inset * 2;
  const counts = chairsPerSide(seats, topWidth, topHeight);
  const chairs: Chair[] = [];
  for (const side of SIDES) {
    const count = counts[side];
    if (count === 0) continue;
    const horizontal = side === "top" || side === "bottom";
    const span = horizontal ? topWidth : topHeight;
    const length = Math.max(6, Math.min(depth * 1.7, span / count - 4));
    for (let index = 0; index < count; index += 1) {
      const centre = inset + (span * (index + 1)) / (count + 1);
      if (horizontal) {
        chairs.push({
          left: centre - length / 2,
          top: side === "top" ? inset - depth - 2 : height - inset + 2,
          width: length,
          height: depth,
          rotate: 0,
        });
      } else {
        chairs.push({
          left: side === "left" ? inset - depth - 2 : width - inset + 2,
          top: centre - length / 2,
          width: depth,
          height: length,
          rotate: 0,
        });
      }
    }
  }
  return chairs;
}

function roundChairs(seats: number, width: number, height: number, depth: number, radius: number): Chair[] {
  const centreX = width / 2;
  const centreY = height / 2;
  const orbit = radius + 2 + depth / 2;
  const length = Math.max(6, Math.min(depth * 1.7, ((2 * Math.PI * orbit) / Math.max(seats, 1)) * 0.75));
  return Array.from({ length: seats }, (_, index) => {
    const angle = -Math.PI / 2 + (index * 2 * Math.PI) / seats;
    return {
      left: centreX + orbit * Math.cos(angle) - length / 2,
      top: centreY + orbit * Math.sin(angle) - depth / 2,
      width: length,
      height: depth,
      rotate: (angle * 180) / Math.PI + 90,
    };
  });
}

/** A dining table seen from above: the tabletop in its shape with one chair per seat around it. */
export function DiningTableShape({
  shape,
  seats,
  width,
  height,
  occupied = 0,
  topClassName = "",
  chairClassName = "",
  occupiedChairClassName = chairClassName,
  children,
}: DiningTableShapeProps) {
  const shortest = Math.min(width, height);
  const depth = Math.max(6, Math.min(12, Math.round(shortest * 0.13)));
  const inset = depth + 4;
  const count = Math.max(0, Math.min(seats, 24));
  const round = shape === "round";
  const radius = shortest / 2 - inset;
  const chairs = round ? roundChairs(count, width, height, depth, radius) : squareChairs(count, width, height, depth, inset);
  const top: CSSProperties = round
    ? { left: width / 2 - radius, top: height / 2 - radius, width: radius * 2, height: radius * 2, borderRadius: "9999px" }
    : { left: inset, top: inset, width: width - inset * 2, height: height - inset * 2, borderRadius: Math.min(14, shortest / 6) };

  return (
    <span className="pointer-events-none absolute inset-0 block">
      {chairs.map((chair, index) => (
        <span
          key={index}
          aria-hidden="true"
          className={`absolute block ${index < occupied ? occupiedChairClassName : chairClassName}`}
          style={{
            left: chair.left,
            top: chair.top,
            width: chair.width,
            height: chair.height,
            borderRadius: Math.min(chair.width, chair.height) / 2.2,
            transform: chair.rotate ? `rotate(${chair.rotate}deg)` : undefined,
          }}
        />
      ))}
      <span className={`absolute flex flex-col items-center justify-center text-center ${topClassName}`} style={top}>
        {children}
      </span>
    </span>
  );
}
