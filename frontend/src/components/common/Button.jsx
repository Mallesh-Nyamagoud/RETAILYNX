import clsx from "clsx";
import { Loader2 } from "lucide-react";

const VARIANTS = {
  primary: "bg-accent text-white hover:bg-accent-hover shadow-sm",
  secondary: "bg-card border border-border-strong text-text-primary hover:bg-card-hover",
  ghost: "text-text-secondary hover:text-text-primary hover:bg-card-hover",
  danger: "bg-negative/10 text-negative hover:bg-negative/20 border border-negative/30",
};

const SIZES = {
  sm: "text-xs px-2.5 py-1.5 gap-1.5",
  md: "text-sm px-3.5 py-2 gap-2",
  lg: "text-sm px-5 py-2.5 gap-2",
};

export default function Button({
  variant = "secondary",
  size = "md",
  className,
  children,
  loading = false,
  disabled,
  icon: Icon,
  ...rest
}) {
  return (
    <button
      className={clsx(
        "inline-flex items-center justify-center rounded-lg font-medium transition-colors",
        "disabled:opacity-50 disabled:cursor-not-allowed",
        VARIANTS[variant],
        SIZES[size],
        className
      )}
      disabled={disabled || loading}
      {...rest}
    >
      {loading ? (
        <Loader2 size={14} className="animate-spin" />
      ) : (
        Icon && <Icon size={14} />
      )}
      {children}
    </button>
  );
}
