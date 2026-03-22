"use client";

import { useParams } from "next/navigation";
import { useSessionSSE } from "@/lib/sse";
import { formatMetric, formatElapsed } from "@/lib/format";
import StatusBadge from "@/components/StatusBadge";

export default function SessionMonitorPage() {
  const params = useParams();
  const sessionId = params.id as string;
  const { metrics, connected, error } = useSessionSSE(sessionId);

  return (
    <div className="p-6 space-y-6 animate-fade-in">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-lg font-semibold text-lab-text">Live Session Monitor</h1>
          <p className="font-mono-data text-xs text-lab-muted mt-0.5">{sessionId}</p>
        </div>
        <div className="flex items-center gap-3">
          <span className={`status-dot ${connected ? "status-dot-live" : "status-dot-error"}`} />
          <span className="text-xs text-lab-muted">
            {connected ? "SSE Connected" : "Disconnected"}
          </span>
        </div>
      </div>

      {/* Error */}
      {error && (
        <div className="px-4 py-3 bg-fail/10 border border-fail/30 rounded-lg text-sm text-fail">
          {error}
        </div>
      )}

      {!metrics ? (
        <div className="text-center py-20">
          <div className="status-dot status-dot-live mx-auto mb-4 w-4 h-4" />
          <p className="text-lab-muted">Connecting to session…</p>
          <p className="text-xs text-lab-muted/60 mt-1">Waiting for data from SSE stream</p>
        </div>
      ) : (
        <>
          {/* Big status + timer */}
          <div className="flex items-center justify-center gap-8 py-6">
            <StatusBadge status={metrics.state} size="lg" />
            <div className="text-center">
              <p className="text-5xl font-mono-data font-bold text-lab-text">
                {formatElapsed(metrics.elapsed_s)}
              </p>
              <p className="text-xs text-lab-muted mt-1">Elapsed</p>
            </div>
          </div>

          {/* Metric cards grid */}
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
            {/* UL metrics */}
            {metrics.ul && (
              <>
                <BigMetricCard
                  label="UL Throughput"
                  value={metrics.ul.throughput_mbps}
                  unit="Mbps"
                  decimals={1}
                  icon="↑"
                />
                <BigMetricCard
                  label="UL Packet Loss"
                  value={metrics.ul.packet_loss_pct}
                  unit="%"
                  decimals={3}
                  icon="↑"
                  warn={metrics.ul.packet_loss_pct > 0.01}
                />
                <BigMetricCard
                  label="UL Jitter"
                  value={metrics.ul.jitter_ms}
                  unit="ms"
                  decimals={2}
                  icon="↑"
                />
                <BigMetricCard
                  label="Packets RX"
                  value={metrics.ul.packets_received}
                  unit=""
                  decimals={0}
                  icon="📦"
                />
              </>
            )}

            {/* DL metrics */}
            {metrics.dl && (
              <>
                <BigMetricCard
                  label="RTT Avg"
                  value={metrics.dl.avg_rtt_ms}
                  unit="ms"
                  decimals={1}
                  icon="↓"
                />
                <BigMetricCard
                  label="RTT p95"
                  value={metrics.dl.p95_rtt_ms}
                  unit="ms"
                  decimals={1}
                  icon="↓"
                />
                <BigMetricCard
                  label="DL Loss"
                  value={metrics.dl.packet_loss_pct}
                  unit="%"
                  decimals={3}
                  icon="↓"
                  warn={metrics.dl.packet_loss_pct > 0.01}
                />
                <BigMetricCard
                  label="Control Hz"
                  value={metrics.dl.control_loop_hz_actual}
                  unit="Hz"
                  decimals={1}
                  icon="🔄"
                />
              </>
            )}
          </div>

          {/* Kernel drops warning */}
          {metrics.ul && metrics.ul.kernel_buffer_drops > 0 && (
            <div className="px-4 py-3 bg-warn/10 border border-warn/30 rounded-lg text-sm text-warn flex items-center gap-2">
              <span>⚠️</span>
              <span>Kernel buffer drops detected: {metrics.ul.kernel_buffer_drops}</span>
              <span className="text-xs text-warn/70 ml-auto">Consider increasing net.core.rmem_max</span>
            </div>
          )}

          {/* OTA progress bar */}
          {metrics.dl?.transfer_progress_pct !== undefined && (
            <div className="lab-card">
              <div className="flex justify-between items-center mb-2">
                <h3 className="text-xs font-semibold text-lab-muted uppercase">OTA Transfer</h3>
                <span className="font-mono-data text-sm text-lab-text">
                  {formatMetric(metrics.dl.transfer_progress_pct, "percent")}
                </span>
              </div>
              <div className="w-full h-3 bg-lab-bg rounded-full overflow-hidden">
                <div
                  className="h-full bg-gradient-to-r from-primary to-pass rounded-full transition-all duration-500"
                  style={{ width: `${metrics.dl.transfer_progress_pct}%` }}
                />
              </div>
              <p className="text-xs text-lab-muted mt-1">
                {metrics.dl.chunks_acked ?? 0} / {metrics.dl.chunks_sent ?? 0} chunks
              </p>
            </div>
          )}

          {/* Detailed DL stats table */}
          {metrics.dl && metrics.dl.rtt_sample_count !== undefined && (
            <div className="lab-card">
              <h3 className="text-xs font-semibold text-lab-muted uppercase tracking-wider mb-3">
                RTT Distribution
              </h3>
              <div className="grid grid-cols-3 lg:grid-cols-6 gap-3">
                <MiniStat label="Min" value={metrics.dl.min_rtt_ms} unit="ms" />
                <MiniStat label="Avg" value={metrics.dl.avg_rtt_ms} unit="ms" />
                <MiniStat label="p50" value={metrics.dl.p50_rtt_ms} unit="ms" />
                <MiniStat label="p95" value={metrics.dl.p95_rtt_ms} unit="ms" />
                <MiniStat label="p99" value={metrics.dl.p99_rtt_ms} unit="ms" />
                <MiniStat label="Max" value={metrics.dl.max_rtt_ms} unit="ms" />
              </div>
              <p className="text-xs text-lab-muted mt-2">
                Samples: {metrics.dl.rtt_sample_count.toLocaleString("en-US")} ·
                Sent: {metrics.dl.packets_sent.toLocaleString("en-US")}
              </p>
            </div>
          )}
        </>
      )}
    </div>
  );
}

function BigMetricCard({
  label, value, unit, decimals = 1, icon, warn,
}: {
  label: string;
  value: number | null | undefined;
  unit: string;
  decimals?: number;
  icon: string;
  warn?: boolean;
}) {
  const formatted = value !== null && value !== undefined
    ? (decimals === 0 ? Math.round(value).toLocaleString("en-US") : value.toFixed(decimals))
    : "—";

  return (
    <div className={`lab-card text-center ${warn ? "border-warn/50" : ""}`}>
      <p className="text-xs text-lab-muted mb-1">{icon} {label}</p>
      <p className={`text-2xl font-mono-data font-bold ${warn ? "text-warn" : "text-lab-text"}`}>
        {formatted}
      </p>
      {unit && <p className="text-xs text-lab-muted">{unit}</p>}
    </div>
  );
}

function MiniStat({ label, value, unit }: { label: string; value: number | null | undefined; unit: string }) {
  return (
    <div className="text-center">
      <p className="text-xs text-lab-muted">{label}</p>
      <p className="font-mono-data text-sm font-semibold text-lab-text">
        {value !== null && value !== undefined ? value.toFixed(1) : "—"}
      </p>
      <p className="text-[10px] text-lab-muted">{unit}</p>
    </div>
  );
}
