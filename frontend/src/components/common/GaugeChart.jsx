import React from "react";
import clsx from "clsx";

const SEGMENTS = [
  { min: 0, max: 25, color: "#ef4444", label: "0-25%" },     // red-500
  { min: 25, max: 50, color: "#f97316", label: "25-50%" },    // orange-500
  { min: 50, max: 75, color: "#eab308", label: "50-75%" },    // yellow-500
  { min: 75, max: 90, color: "#84cc16", label: "75-90%" },    // lime-500
  { min: 90, max: 100, color: "#22c55e", label: "90-100%" },  // green-500
  { min: 100, max: 120, color: "#06b6d4", label: ">100%" },   // cyan-500
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
  // Clamp value between 0 and MAX_VALUE for the needle display
  const clampedValue = Math.min(Math.max(value, 0), MAX_VALUE);
  const valueToAngle = (v) => (v / MAX_VALUE) * 180;
  
  const needleAngle = valueToAngle(clampedValue);
  
  // Dimensions
  const cx = 200;
  const cy = 160; 
  const radius = 130;
  const strokeWidth = 36;
  
  // Needle math - teardrop shape pointing to arc
  const needleTip = polarToCartesian(cx, cy, radius - 15, needleAngle);
  const needleBaseLeft = polarToCartesian(cx, cy, 7, needleAngle - 90);
  const needleBaseRight = polarToCartesian(cx, cy, 7, needleAngle + 90);

  return (
    <div className={clsx("relative flex flex-col items-center justify-center w-full h-full", className)}>
      {/* 
        Increased viewBox and scaled max-w for a larger, premium chart.
        The SVG native text ensures perfect scaling without overlapping the needle.
      */}
      <svg viewBox="0 0 400 240" className="w-full h-full max-w-[400px] max-h-[280px] overflow-visible drop-shadow-md">
        {/* Draw the segments */}
        {SEGMENTS.map((seg, i) => {
          const startAngle = valueToAngle(seg.min);
          const endAngle = valueToAngle(seg.max);
          const gap = i > 0 ? 1 : 0; // slight gap between segments
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
          // Skip the >100% boundary text if it's crowded
          if (seg.max === MAX_VALUE) return null; 
          const angle = valueToAngle(seg.max);
          const pos = polarToCartesian(cx, cy, radius + strokeWidth / 2 + 16, angle);
          return (
            <text
              key={`label-${i}`}
              x={pos.x}
              y={pos.y}
              textAnchor="middle"
              alignmentBaseline="middle"
              fill="#cbd5e1" /* slate-300 bright enough against dark backgrounds */
              style={{ fontSize: "13px", fontWeight: "600" }}
            >
              {seg.max}%
            </text>
          );
        })}
        {/* 0% label */}
        <text
          x={polarToCartesian(cx, cy, radius + strokeWidth / 2 + 16, 0).x}
          y={polarToCartesian(cx, cy, radius + strokeWidth / 2 + 16, 0).y}
          textAnchor="middle"
          alignmentBaseline="middle"
          fill="#cbd5e1"
          style={{ fontSize: "13px", fontWeight: "600" }}
        >
          0%
        </text>

        {/* Draw the Needle */}
        <polygon
          points={`${needleTip.x},${needleTip.y} ${needleBaseRight.x},${needleBaseRight.y} ${needleBaseLeft.x},${needleBaseLeft.y}`}
          fill="#f8fafc" /* slate-50 bright needle */
          className="transition-all duration-1000 ease-out drop-shadow-lg"
        />
        {/* Needle center pin */}
        <circle cx={cx} cy={cy} r="12" fill="#f8fafc" className="drop-shadow-lg" />
        <circle cx={cx} cy={cy} r="4" fill="#0f172a" /> {/* slate-900 center */}

        {/* Central Label Native to SVG so it can NEVER overlap */}
        <text 
          x={cx} 
          y={cy + 40} 
          textAnchor="middle" 
          fill="#f8fafc" 
          style={{ fontSize: "36px", fontWeight: "800", letterSpacing: "-0.025em" }}
        >
          {Number(value).toFixed(1)}%
        </text>
        <text 
          x={cx} 
          y={cy + 60} 
          textAnchor="middle" 
          fill="#94a3b8" /* slate-400 */
          style={{ fontSize: "13px", fontWeight: "700", letterSpacing: "0.05em", textTransform: "uppercase" }}
        >
          {label}
        </text>
      </svg>
    </div>
  );
}

