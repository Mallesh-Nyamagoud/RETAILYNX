const fs = require('fs');
const path = 'src/components/common/GaugeChart.jsx';

const text = import React from "react";
import clsx from "clsx";

const SEGMENTS = [
  { min: 0, max: 25, color: "#ef4444" },     // red-500
  { min: 25, max: 50, color: "#f97316" },    // orange-500
  { min: 50, max: 75, color: "#eab308" },    // yellow-500
  { min: 75, max: 90, color: "#84cc16" },    // lime-500
  { min: 90, max: 100, color: "#22c55e" },   // green-500
  { min: 100, max: 120, color: "#06b6d4" },  // cyan-500
];

const MAX_VALUE = 120;

const polarToCartesian = (centerX, centerY, radius, angleInDegrees) => {
  const angleInRadians = ((angleInDegrees - 180) * Math.PI) / 180.0;
  return {
    x: centerX + radius * Math.cos(angleInRadians),
    y: centerY + radius * Math.sin(angleInRadians),
  };
};

const describeArc = (x, y, radius, startAngle, endAngle) => {
  const start = polarToCartesian(x, y, radius, startAngle);
  const end = polarToCartesian(x, y, radius, endAngle);
  const largeArcFlag = endAngle - startAngle <= 180 ? "0" : "1";

  return [
    "M", start.x, start.y,
    "A", radius, radius, 0, largeArcFlag, 1, end.x, end.y
  ].join(" ");
};

export default function GaugeChart({
  value = 0,
  label = "Dispatch %",
  className,
}) {
  const clampedValue = Math.min(Math.max(value, 0), MAX_VALUE);
  const valueToAngle = (v) => (v / MAX_VALUE) * 180;
  
  const needleAngle = valueToAngle(clampedValue);
  
  const cx = 200;
  const cy = 160; 
  const radius = 130;
  const strokeWidth = 36;
  
  const needleTip = polarToCartesian(cx, cy, radius - 24, needleAngle);
  const needleBaseLeft = polarToCartesian(cx, cy, 10, needleAngle - 90);
  const needleBaseRight = polarToCartesian(cx, cy, 10, needleAngle + 90);

  return (
    <div className={clsx("flex flex-col items-center justify-center w-full", className)}>
      <svg viewBox="0 0 400 240" className="w-full h-auto max-w-[360px] drop-shadow-sm">
        
        {/* Draw the segments */}
        {SEGMENTS.map((seg, i) => {
          const startAngle = valueToAngle(seg.min);
          const endAngle = valueToAngle(seg.max);
          const gap = i > 0 ? 1.5 : 0;
          if (startAngle + gap >= endAngle) return null;
          return (
            <path
              key={i}
              d={describeArc(cx, cy, radius, startAngle + gap, endAngle)}
              fill="none"
              stroke={seg.color}
              strokeWidth={strokeWidth}
              className="transition-all duration-700 ease-out"
            />
          );
        })}
        
        {/* Draw segment labels (tick marks) on the outer edge */}
        {SEGMENTS.map((seg, i) => {
          if (seg.max === MAX_VALUE) return null; 
          const angle = valueToAngle(seg.max);
          const pos = polarToCartesian(cx, cy, radius + strokeWidth / 2 + 14, angle);
          return (
            <text
              key={\label-\\}
              x={pos.x}
              y={pos.y}
              textAnchor="middle"
              alignmentBaseline="middle"
              className="text-[12px] font-bold fill-text-muted/70"
            >
              {seg.max}%
            </text>
          );
        })}
        {/* 0% label */}
        <text
          x={polarToCartesian(cx, cy, radius + strokeWidth / 2 + 14, 0).x}
          y={polarToCartesian(cx, cy, radius + strokeWidth / 2 + 14, 0).y}
          textAnchor="middle"
          alignmentBaseline="middle"
          className="text-[12px] font-bold fill-text-muted/70"
        >
          0%
        </text>

        {/* Draw the Needle */}
        <polygon
          points={\\,\ \,\ \,\\}
          className="fill-text-secondary transition-all duration-1000 ease-out drop-shadow-md"
        />
        {/* Needle center pin */}
        <circle cx={cx} cy={cy} r="10" className="fill-text-secondary drop-shadow-md" />
        <circle cx={cx} cy={cy} r="4" className="fill-surface" />

        {/* Center Texts (Natively inside SVG so they scale perfectly and never overlap the needle) */}
        <text
          x={cx}
          y={cy + 42}
          textAnchor="middle"
          className="text-4xl font-black fill-text-primary tabular-nums"
        >
          {Number(value).toFixed(1)}%
        </text>
        <text
          x={cx}
          y={cy + 62}
          textAnchor="middle"
          className="text-[11px] font-bold fill-text-muted tracking-[0.2em] uppercase"
        >
          {label}
        </text>
      </svg>
    </div>
  );
};

fs.writeFileSync(path, text);
