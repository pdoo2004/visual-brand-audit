import type { ComponentProps } from "react";

type CheckboxProps = Omit<ComponentProps<"input">, "type"> & { label: string };

export default function Checkbox({ label, className = "", ...props }: CheckboxProps) {
  return (
    <label className={`flex items-center gap-2 text-sm ${className}`}>
      <input type="checkbox" className="size-4 accent-brand-600" {...props} />
      {label}
    </label>
  );
}