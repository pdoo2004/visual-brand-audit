type Source = "measured" | "ai";

const styles: Record<Source, { classes: string; label: string }> = {
  measured: { classes: "bg-tag-measured-bg text-tag-measured", label: "Measured" },
  ai: { classes: "bg-tag-ai-bg text-tag-ai", label: "AI judgment" },
};

export default function SourceTag({ source }: { source: Source }) {
  const { classes, label } = styles[source];
  return (
    <span className={`rounded-control px-2 py-0.5 text-xs font-medium ${classes}`}>
      {label}
    </span>
  );
}