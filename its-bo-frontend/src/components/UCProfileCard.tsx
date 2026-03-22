"use client";

import type { UCProfile } from "@/lib/types";

interface UCProfileCardProps {
  profile: UCProfile;
  selected: boolean;
  onClick: () => void;
}

const PATTERN_ICONS: Record<string, string> = {
  UL_ONLY: "↑",
  DL_ONLY: "↓",
  BIDIRECTIONAL: "↕",
  BIDIRECTIONAL_ASYMMETRIC: "⇅",
};

export default function UCProfileCard({ profile, selected, onClick }: UCProfileCardProps) {
  return (
    <button
      onClick={onClick}
      className={`lab-card w-full text-left transition-all group cursor-pointer ${
        selected ? "lab-card-selected" : ""
      }`}
    >
      {/* Header */}
      <div className="flex items-start justify-between mb-2">
        <span className={`inline-block px-2.5 py-1 rounded-md text-xs font-bold tracking-wide
          ${selected ? "bg-primary text-white" : "bg-primary/20 text-primary"}`}>
          {profile.id}
        </span>
        <span className="text-lg" title={profile.communication_pattern}>
          {PATTERN_ICONS[profile.communication_pattern] ?? "●"}
        </span>
      </div>

      {/* Name */}
      <h3 className="text-sm font-semibold text-lab-text mb-1 leading-tight">
        {profile.name}
      </h3>

      {/* Standard ref */}
      <p className="text-xs text-lab-muted font-mono-data mb-3 truncate">
        {profile.standard_ref}
      </p>

      {/* Key thresholds */}
      <div className="space-y-1">
        {Object.entries(profile.thresholds).slice(0, 3).map(([key, t]) => (
          <div key={key} className="flex justify-between text-xs">
            <span className="text-lab-muted truncate mr-2">{humanizeMetric(key)}</span>
            <span className="font-mono-data text-lab-text whitespace-nowrap">
              {t.op} {t.value}
            </span>
          </div>
        ))}
      </div>

      {/* Duration */}
      <div className="mt-3 pt-2 border-t border-lab-border flex justify-between text-xs text-lab-muted">
        <span>{profile.default_duration_s}s default</span>
        <span>×{profile.min_repetitions} min reps</span>
      </div>
    </button>
  );
}

function humanizeMetric(key: string): string {
  return key
    .replace(/_/g, " ")
    .replace("pct", "%")
    .replace("mbps", "Mbps")
    .replace("ms", "ms")
    .replace(/\b\w/g, (c) => c.toUpperCase());
}
