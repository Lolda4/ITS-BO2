"use client";

interface PassFailBadgeProps {
  pass: boolean;
  interpretation?: string;
  size?: "sm" | "lg";
}

export default function PassFailBadge({ pass, interpretation, size = "lg" }: PassFailBadgeProps) {
  const isLarge = size === "lg";

  return (
    <div className={`flex flex-col ${isLarge ? "gap-3" : "gap-1"}`}>
      <div className={`inline-flex items-center gap-2 rounded-xl font-bold
        ${isLarge ? "text-2xl px-6 py-3" : "text-sm px-3 py-1.5"}
        ${pass
          ? "bg-pass/15 text-pass border border-pass/30"
          : "bg-fail/15 text-fail border border-fail/30"
        }`}
      >
        <span>{pass ? "✅" : "❌"}</span>
        <span>{pass ? "PASS" : "FAIL"}</span>
      </div>
      {interpretation && (
        <p className={`text-lab-muted leading-relaxed ${isLarge ? "text-sm" : "text-xs"}`}>
          {interpretation}
        </p>
      )}
    </div>
  );
}
