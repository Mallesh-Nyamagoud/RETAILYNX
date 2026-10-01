import { AlertTriangle, Inbox, RefreshCw } from "lucide-react";
import Button from "./Button";

export function LoadingState({ label = "Loading data…", rows = 5 }) {
  return (
    <div className="space-y-2 py-2" role="status" aria-live="polite">
      <span className="sr-only">{label}</span>
      {Array.from({ length: rows }).map((_, i) => (
        <div
          key={i}
          className="h-10 rounded-lg shimmer-bg animate-shimmer border border-border/60"
          style={{ animationDelay: `${i * 40}ms` }}
        />
      ))}
    </div>
  );
}

export function KpiSkeleton({ count = 4 }) {
  return (
    <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
      {Array.from({ length: count }).map((_, i) => (
        <div
          key={i}
          className="h-24 rounded-xl2 shimmer-bg animate-shimmer border border-border/60"
        />
      ))}
    </div>
  );
}

export function EmptyState({
  title = "Nothing to show yet",
  description = "Adjust your filters or dimensions to see results here.",
  icon: Icon = Inbox,
}) {
  return (
    <div className="flex flex-col items-center justify-center text-center py-16 px-6 gap-3 animate-fadeIn">
      <div className="w-12 h-12 rounded-full bg-border/50 flex items-center justify-center text-text-muted">
        <Icon size={22} />
      </div>
      <div>
        <p className="font-display font-medium text-text-primary">{title}</p>
        <p className="text-sm text-text-secondary mt-1 max-w-sm">{description}</p>
      </div>
    </div>
  );
}

export function ErrorState({ message = "Something went wrong.", onRetry }) {
  return (
    <div className="flex flex-col items-center justify-center text-center py-16 px-6 gap-3 animate-fadeIn">
      <div className="w-12 h-12 rounded-full bg-negative-soft flex items-center justify-center text-negative">
        <AlertTriangle size={22} />
      </div>
      <div>
        <p className="font-display font-medium text-text-primary">Couldn't load this</p>
        <p className="text-sm text-text-secondary mt-1 max-w-md">{message}</p>
      </div>
      {onRetry && (
        <Button size="sm" variant="secondary" icon={RefreshCw} onClick={onRetry}>
          Try again
        </Button>
      )}
    </div>
  );
}
