import clsx from "clsx";

const TONE_CLASSES = {
  neutral: "bg-border/60 text-text-secondary",
  accent: "bg-accent-soft text-accent",
  teal: "bg-teal-soft text-teal",
  positive: "bg-positive-soft text-positive",
  negative: "bg-negative-soft text-negative",
  warn: "bg-warn-soft text-warn",
};

export default function Badge({ tone = "neutral", children, className }) {
  return (
    <span
      className={clsx(
        "inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium whitespace-nowrap",
        TONE_CLASSES[tone] || TONE_CLASSES.neutral,
        className
      )}
    >
      {children}
    </span>
  );
}

export function statusTone(status) {
  switch (status) {
    case "L2L":
      return "accent";
    case "Annualized":
      return "teal";
    case "New":
      return "warn";
    case "Closed":
      return "negative";
    default:
      return "neutral";
  }
}
