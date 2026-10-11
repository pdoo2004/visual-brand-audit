import type { ComponentProps } from "react";

type Variant = "primary" | "secondary";

const variants: Record<Variant, string> = {
  primary: "bg-ink text-surface hover:bg-ink/90",
  secondary: "border border-line bg-surface text-ink hover:bg-surface-muted",
};

type ButtonProps = ComponentProps<"button"> & { variant?: Variant };

export default function Button({
  variant = "primary",
  type = "button",
  className = "",
  ...props
}: ButtonProps) {
  return (
    <button
      type={type}
      className={`rounded-control px-4 py-2 text-sm font-medium disabled:cursor-not-allowed disabled:opacity-50 ${variants[variant]} ${className}`}
      {...props}
    />
  );
}