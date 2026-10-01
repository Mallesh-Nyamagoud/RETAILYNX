import clsx from "clsx";

export default function Card({ className, children, padded = true, ...rest }) {
  return (
    <div
      className={clsx(
        "bg-card border border-border rounded-xl shadow-panel group transition-all duration-300 ease-in-out",
        "hover:border-border-strong hover:shadow-panel-lg",
        padded && "p-5",
        className
      )}
      {...rest}
    >
      {children}
    </div>
  );
}
