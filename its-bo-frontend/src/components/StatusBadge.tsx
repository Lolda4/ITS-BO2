"use client";

import type { SessionState } from "@/lib/types";

const STATUS_STYLES: Record<string, string> = {
  WAITING:     "bg-lab-muted/20 text-lab-muted border-lab-muted/30",
  INIT:        "bg-primary/20 text-primary border-primary/30",
  BASELINE:    "bg-warn/20 text-warn border-warn/30",
  READY:       "bg-primary/20 text-primary border-primary/30",
  RUNNING:     "bg-primary/20 text-primary border-primary/30 animate-pulse-live",
  COMPLETED:   "bg-pass/20 text-pass border-pass/30",
  INTERRUPTED: "bg-warn/20 text-warn border-warn/30",
  ERROR:       "bg-fail/20 text-fail border-fail/30",
};

interface StatusBadgeProps {
  status: SessionState | string;
  size?: "sm" | "md" | "lg";
  pulse?: boolean;
}

export default function StatusBadge({ status, size = "md", pulse }: StatusBadgeProps) {
  const style = STATUS_STYLES[status] ?? STATUS_STYLES.WAITING;
  const sizeClass =
    size === "sm" ? "text-xs px-2 py-0.5" :
    size === "lg" ? "text-base px-4 py-1.5" :
                    "text-sm px-3 py-1";

  const showPulse = pulse ?? status === "RUNNING";

  return (
    <span className={`inline-flex items-center gap-1.5 rounded-full border font-semibold ${sizeClass} ${style}`}>
      {showPulse && (
        <span className="status-dot status-dot-live" />
      )}
      {status}
    </span>
  );
}
