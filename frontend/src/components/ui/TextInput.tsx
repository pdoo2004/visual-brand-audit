import { useId } from "react";
import type { ComponentProps } from "react";

type TextInputProps = ComponentProps<"input"> & { label: string };

export default function TextInput({ label, id, className = "", ...props }: TextInputProps) {
  const autoId = useId();
  const inputId = id ?? autoId;
  return (
    <div className="flex flex-col gap-1">
      <label htmlFor={inputId} className="text-sm font-medium">
        {label}
      </label>
      <input
        id={inputId}
        className={`rounded-control border border-line bg-surface px-3 py-2 text-sm placeholder:text-text-muted focus:outline-2 focus:outline-brand-500 ${className}`}
        {...props}
      />
    </div>
  );
}