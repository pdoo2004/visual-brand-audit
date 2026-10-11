type ResultStatus = "pass" | "review" | "fail";

const styles: Record<ResultStatus, { classes: string; label: string }> = {
  pass: { classes: "bg-status-pass-bg text-status-pass", label: "Pass" },
  review: { classes: "bg-status-review-bg text-status-review", label: "Needs review" },
  fail: { classes: "bg-status-fail-bg text-status-fail", label: "Fail" },
};

export default function StatusBadge({ status }: { status: ResultStatus }) {
  const { classes, label } = styles[status];
  return (
    <span className={`rounded-full px-3 py-1 text-xs font-medium ${classes}`}>
      {label}
    </span>
  );
}