"use client";

import type { EvaluationEntry } from "@/lib/types";
import { formatMetric, type MetricType } from "@/lib/format";

interface MetricRowProps {
  label: string;
  entry: EvaluationEntry;
  metricType?: MetricType;
}

export default function MetricRow({ label, entry, metricType = "generic" }: MetricRowProps) {
  const passed = entry.pass;
  const borderColor = passed ? "border-pass/30" : "border-fail/30";
  const bgColor     = passed ? "bg-pass/5"      : "bg-fail/5";

  return (
    <div className={`flex items-center gap-4 px-4 py-3 rounded-lg border ${borderColor} ${bgColor} transition-colors`}>
      {/* Metric name */}
      <div className="flex-1 min-w-0">
        <p className="text-sm font-medium text-lab-text truncate">{label}</p>
        {entry.note && (
          <p className="text-xs text-lab-muted mt-0.5 truncate">{entry.note}</p>
        )}
      </div>

      {/* Measured value */}
      <div className="text-right min-w-[80px]">
        <span className={`font-mono-data text-sm font-semibold ${passed ? "text-pass" : "text-fail"}`}>
          {entry.measured !== null ? formatMetric(entry.measured, metricType) : "—"}
        </span>
      </div>

      {/* Threshold */}
      <div className="text-right min-w-[90px]">
        <span className="font-mono-data text-xs text-lab-muted">
          {entry.op} {formatMetric(entry.threshold, metricType)}
        </span>
      </div>

      {/* PASS/FAIL badge */}
      <div className="min-w-[52px] text-center">
        <span className={`inline-block px-2 py-0.5 rounded text-xs font-bold
          ${passed ? "bg-pass/20 text-pass" : "bg-fail/20 text-fail"}`}>
          {passed ? "PASS" : "FAIL"}
        </span>
      </div>

      {/* Normative ref */}
      <div className="text-right min-w-[80px]">
        <span className="text-xs text-lab-muted font-mono-data">{entry.ref}</span>
      </div>
    </div>
  );
}
