/**
 * Consistent metric formatting helpers.
 *
 * throughput: 1 decimal  (23.4 Mbps)
 * rtt:        1 decimal  (12.4 ms)
 * loss:       3 decimals (0.001 %)
 * packets:    grouped    (98,450)
 * percent:    2 decimals (99.99 %)
 * bytes:      auto unit  (14.7 GB)
 */

export type MetricType =
  | "throughput" | "rtt" | "loss" | "packets"
  | "percent" | "bytes" | "duration" | "hz" | "generic";

export function formatMetric(value: number | null | undefined, type: MetricType): string {
  if (value === null || value === undefined) return "—";

  switch (type) {
    case "throughput":
      return `${value.toFixed(1)} Mbps`;
    case "rtt":
      return `${value.toFixed(1)} ms`;
    case "loss":
      return `${value.toFixed(3)} %`;
    case "packets":
      return value.toLocaleString("en-US");
    case "percent":
      return `${value.toFixed(2)} %`;
    case "bytes":
      return formatBytes(value);
    case "duration":
      return `${value.toFixed(1)} s`;
    case "hz":
      return `${value.toFixed(1)} Hz`;
    case "generic":
    default:
      return Number.isInteger(value) ? value.toLocaleString("en-US") : value.toFixed(2);
  }
}

/** Raw number format without unit, used in tables */
export function formatValue(value: number | null | undefined, decimals = 2): string {
  if (value === null || value === undefined) return "—";
  return value.toFixed(decimals);
}

function formatBytes(bytes: number): string {
  if (bytes === 0) return "0 B";
  const k = 1024;
  const units = ["B", "KB", "MB", "GB", "TB"];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return `${(bytes / Math.pow(k, i)).toFixed(1)} ${units[i]}`;
}

/** Format ISO date string to local short format */
export function formatDate(iso: string): string {
  try {
    const d = new Date(iso);
    return d.toLocaleString("cs-CZ", {
      day: "2-digit", month: "2-digit", year: "numeric",
      hour: "2-digit", minute: "2-digit",
    });
  } catch {
    return iso;
  }
}

/** Format elapsed seconds to mm:ss */
export function formatElapsed(seconds: number): string {
  const m = Math.floor(seconds / 60);
  const s = Math.floor(seconds % 60);
  return `${m.toString().padStart(2, "0")}:${s.toString().padStart(2, "0")}`;
}
