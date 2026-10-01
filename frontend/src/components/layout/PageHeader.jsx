export default function PageHeader({ eyebrow, title, description, actions }) {
  return (
    <div className="flex items-start justify-between gap-4 flex-wrap mb-6">
      <div>
        {eyebrow && (
          <p className="text-[11px] font-bold tracking-[0.18em] text-accent uppercase mb-1.5">
            {eyebrow}
          </p>
        )}
        <h1 className="font-display text-2xl font-semibold text-text-primary">{title}</h1>
        {description && (
          <p className="text-sm text-text-secondary mt-1 max-w-2xl">{description}</p>
        )}
      </div>
      {actions && <div className="flex items-center gap-2 flex-wrap">{actions}</div>}
    </div>
  );
}
