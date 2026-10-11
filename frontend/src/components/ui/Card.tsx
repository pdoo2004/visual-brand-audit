import type { ComponentProps } from "react";

export default function Card({ className = "", ...props }: ComponentProps<"div">) {
  return (
    <div
      className={`rounded-card border border-line bg-surface p-4 ${className}`}
      {...props}
    />
  );
}