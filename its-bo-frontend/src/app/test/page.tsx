"use client";

import { useEffect, useState } from "react";
import { getProfiles, getSystemStatus } from "@/lib/api";
import { useSessionSSE } from "@/lib/sse";
import { STATUS_POLL_MS } from "@/lib/config";
import { formatElapsed } from "@/lib/format";
import type { UCProfile, SystemStatus, ActiveSessionInfo, SSEMetricEvent } from "@/lib/types";
import UCProfileCard from "@/components/UCProfileCard";
import StatusBadge from "@/components/StatusBadge";

export default function TestPage() {
  // ── State ──
  const [profiles, setProfiles]         = useState<UCProfile[]>([]);
  const [selectedUC, setSelectedUC]     = useState<string | null>(null);
  const [systemStatus, setSystemStatus] = useState<SystemStatus | null>(null);
  const [activeSession, setActiveSession] = useState<ActiveSessionInfo | null>(null);
  const [sessionId, setSessionId]       = useState<string | null>(null);
  const [error, setError]               = useState<string | null>(null);
  const [loading, setLoading]           = useState(true);

  // SSE for live metrics
  const { metrics, error: sseError } = useSessionSSE(sessionId);

  // ── Load profiles on mount ──
  useEffect(() => {
    async function load() {
      try {
        const p = await getProfiles();
        setProfiles(p);
        if (p.length > 0) setSelectedUC(p[0].id);
        setError(null);
      } catch (e) {
        setError(`Backend nedostupný: ${e instanceof Error ? e.message : String(e)}`);
      } finally {
        setLoading(false);
      }
    }
    load();
  }, []);

  // ── Poll system status for active sessions ──
  useEffect(() => {
    const interval = setInterval(async () => {
      try {
        const status = await getSystemStatus();
        setSystemStatus(status);

        // Find active session for selected UC
        const active = status.active_sessions?.find(s => s.uc_id === selectedUC);
        if (active) {
          setActiveSession(active);
          if (active.session_id !== sessionId) {
            setSessionId(active.session_id);
          }
        } else {
          // If we had a session and it's gone, keep showing last metrics
          if (activeSession && !active) {
            setActiveSession(null);
            // Don't clear sessionId — SSE will show terminal state
          }
        }
        setError(null);
      } catch {
        // Backend offline — show error but keep polling
      }
    }, STATUS_POLL_MS);

    return () => clearInterval(interval);
  }, [selectedUC, sessionId, activeSession]);

  // Derived
  const selectedProfile = profiles.find(p => p.id === selectedUC) ?? null;
  const backendOnline = systemStatus?.status === "online";

  return (
    <div className="h-full flex flex-col">
      {/* Header */}
      <header className="flex items-center justify-between px-6 py-4 border-b border-lab-border bg-lab-surface/50">
        <div>
          <h1 className="text-lg font-semibold text-lab-text">Test Panel</h1>
          <p className="text-xs text-lab-muted mt-0.5">Select UC profile · Monitor live session</p>
        </div>
        <div className="flex items-center gap-3">
          <span className={`status-dot ${backendOnline ? "status-dot-live" : "status-dot-error"}`} />
          <span className="text-xs text-lab-muted">
            {backendOnline ? "Backend online" : "Backend offline"}
          </span>
          {systemStatus && (
            <span className="text-xs font-mono-data text-lab-muted">
              {systemStatus.ports.active_sessions} active
            </span>
          )}
        </div>
      </header>

      {/* Error banner */}
      {error && (
        <div className="mx-6 mt-4 px-4 py-3 bg-fail/10 border border-fail/30 rounded-lg text-sm text-fail">
          {error}
        </div>
      )}

      {/* Three-panel layout */}
      <div className="flex-1 flex overflow-hidden">
        {/* ═══ LEFT PANEL: UC Selection (30%) ═══ */}
        <div className="w-[30%] border-r border-lab-border overflow-y-auto p-4 space-y-3">
          <h2 className="text-xs font-semibold text-lab-muted uppercase tracking-wider mb-3">
            UC Profiles
          </h2>

          {loading ? (
            <div className="space-y-3">
              {[1,2,3,4].map(i => (
                <div key={i} className="lab-card animate-pulse h-32" />
              ))}
            </div>
          ) : profiles.length === 0 ? (
            <div className="text-sm text-lab-muted text-center py-8">
              No profiles loaded.<br/>Check backend connection.
            </div>
          ) : (
            profiles.map(p => (
              <UCProfileCard
                key={p.id}
                profile={p}
                selected={selectedUC === p.id}
                onClick={() => setSelectedUC(p.id)}
              />
            ))
          )}

          {/* Plugin status */}
          {systemStatus && (
            <div className="mt-4 pt-4 border-t border-lab-border">
              <h3 className="text-xs text-lab-muted uppercase tracking-wider mb-2">Plugin Status</h3>
              <div className="space-y-1">
                {systemStatus.plugins.loaded.map(p => (
                  <div key={p.uc_id} className="flex items-center gap-2 text-xs">
                    <span className="text-pass">✓</span>
                    <span className="text-lab-text">{p.uc_id} – {p.name}</span>
                  </div>
                ))}
                {Object.entries(systemStatus.plugins.errors).map(([pid, err]) => (
                  <div key={pid} className="flex items-center gap-2 text-xs">
                    <span className="text-fail">✗</span>
                    <span className="text-fail">{pid}: {err}</span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>

        {/* ═══ CENTER PANEL: Configuration / Session Info (40%) ═══ */}
        <div className="w-[40%] border-r border-lab-border overflow-y-auto p-6 space-y-6">
          {selectedProfile ? (
            <>
              {/* Profile header */}
              <div>
                <div className="flex items-center gap-3 mb-2">
                  <span className="px-3 py-1 rounded-lg bg-primary/20 text-primary font-bold text-sm">
                    {selectedProfile.id}
                  </span>
                  <h2 className="text-base font-semibold text-lab-text">{selectedProfile.name}</h2>
                </div>
                <p className="text-xs font-mono-data text-lab-muted">{selectedProfile.standard_ref}</p>
                <p className="text-sm text-lab-muted mt-2">{selectedProfile.description}</p>
              </div>

              {/* Session status box */}
              <SessionStatusBox
                activeSession={activeSession}
                metrics={metrics}
              />

              {/* Configuration (readonly from session) */}
              {activeSession && metrics && (
                <div className="lab-card space-y-3">
                  <h3 className="text-xs font-semibold text-lab-muted uppercase tracking-wider">
                    Session Configuration
                  </h3>
                  <ConfigRow label="Session ID" value={activeSession.session_id} mono />
                  <ConfigRow label="Duration" value={`${metrics.elapsed_s?.toFixed(0) ?? "—"}s elapsed`} />
                  <ConfigRow label="State" value={activeSession.state} />
                </div>
              )}

              {/* Default params */}
              <div className="lab-card space-y-3">
                <h3 className="text-xs font-semibold text-lab-muted uppercase tracking-wider">
                  Default Parameters
                </h3>
                {Object.entries(selectedProfile.default_params).map(([key, value]) => (
                  <ConfigRow key={key} label={key.replace(/_/g, " ")} value={String(value)} mono />
                ))}
              </div>

              {/* Normative thresholds */}
              <div className="lab-card space-y-3">
                <h3 className="text-xs font-semibold text-lab-muted uppercase tracking-wider">
                  Normative Thresholds
                </h3>
                {Object.entries(selectedProfile.thresholds).map(([key, t]) => (
                  <div key={key} className="flex justify-between items-center text-sm">
                    <span className="text-lab-text">{key.replace(/_/g, " ")}</span>
                    <span className="font-mono-data text-lab-muted">{t.op} {t.value} <span className="text-lab-muted/60">[{t.ref}]</span></span>
                  </div>
                ))}
              </div>

              {/* Waiting indicator */}
              {!activeSession && (
                <div className="text-center py-6">
                  <div className="inline-flex items-center gap-2 px-4 py-2 rounded-full bg-lab-card border border-lab-border text-sm text-lab-muted">
                    <span className="status-dot status-dot-idle animate-pulse-live" />
                    Waiting for OBU to init session…
                  </div>
                  <p className="text-xs text-lab-muted/60 mt-2">
                    OBU app will call POST /api/v1/session/init
                  </p>
                </div>
              )}
            </>
          ) : (
            <div className="flex items-center justify-center h-full text-lab-muted text-sm">
              Select a UC profile to view details
            </div>
          )}
        </div>

        {/* ═══ RIGHT PANEL: Live SSE Metrics (30%) ═══ */}
        <div className="w-[30%] overflow-y-auto p-4 space-y-4">
          <h2 className="text-xs font-semibold text-lab-muted uppercase tracking-wider">
            Live Metrics
          </h2>

          {sseError && (
            <div className="px-3 py-2 bg-fail/10 border border-fail/30 rounded-lg text-xs text-fail">
              {sseError}
            </div>
          )}

          {!sessionId ? (
            <div className="text-sm text-lab-muted text-center py-12">
              <p className="text-2xl mb-2">📡</p>
              <p>No active session</p>
              <p className="text-xs mt-1">Metrics will appear when OBU starts a test</p>
            </div>
          ) : !metrics ? (
            <div className="text-sm text-lab-muted text-center py-12">
              <div className="status-dot status-dot-live mx-auto mb-3" />
              <p>Connecting to SSE…</p>
            </div>
          ) : (
            <>
              {/* Session header */}
              <div className="lab-card flex items-center justify-between">
                <div>
                  <p className="font-mono-data text-xs text-lab-muted truncate">{metrics.session_id}</p>
                  <p className="text-xl font-mono-data font-bold text-lab-text mt-1">
                    {formatElapsed(metrics.elapsed_s)}
                  </p>
                </div>
                <StatusBadge status={metrics.state} size="sm" />
              </div>

              {/* UL Metrics */}
              {metrics.ul && (
                <div className="lab-card space-y-2">
                  <h3 className="text-xs font-semibold text-primary uppercase tracking-wider flex items-center gap-1.5">
                    <span>↑</span> Uplink
                  </h3>
                  <LiveMetric
                    label="Throughput"
                    value={metrics.ul.throughput_mbps}
                    unit="Mbps"
                    threshold={selectedProfile?.thresholds.ul_throughput_mbps}
                  />
                  <LiveMetric
                    label="Packet Loss"
                    value={metrics.ul.packet_loss_pct}
                    unit="%"
                    decimals={3}
                  />
                  <LiveMetric
                    label="Jitter"
                    value={metrics.ul.jitter_ms}
                    unit="ms"
                  />
                  <LiveMetric
                    label="Packets RX"
                    value={metrics.ul.packets_received}
                    unit=""
                    decimals={0}
                  />
                  {metrics.ul.kernel_buffer_drops > 0 && (
                    <div className="px-2 py-1 bg-warn/10 border border-warn/30 rounded text-xs text-warn">
                      ⚠ Kernel drops: {metrics.ul.kernel_buffer_drops}
                    </div>
                  )}
                </div>
              )}

              {/* DL Metrics */}
              {metrics.dl && (
                <div className="lab-card space-y-2">
                  <h3 className="text-xs font-semibold text-primary uppercase tracking-wider flex items-center gap-1.5">
                    <span>↓</span> Downlink
                  </h3>
                  <LiveMetric
                    label="RTT avg"
                    value={metrics.dl.avg_rtt_ms}
                    unit="ms"
                    threshold={selectedProfile?.thresholds.e2e_latency_ms}
                  />
                  <LiveMetric label="RTT p50" value={metrics.dl.p50_rtt_ms} unit="ms" />
                  <LiveMetric label="RTT p95" value={metrics.dl.p95_rtt_ms} unit="ms" />
                  <LiveMetric label="RTT p99" value={metrics.dl.p99_rtt_ms} unit="ms" />
                  <LiveMetric label="Jitter" value={metrics.dl.jitter_ms} unit="ms" />
                  <LiveMetric label="Loss" value={metrics.dl.packet_loss_pct} unit="%" decimals={3} />
                  <LiveMetric label="ACKs" value={metrics.dl.acks_received} unit="" decimals={0} />
                  <LiveMetric label="Loop Hz" value={metrics.dl.control_loop_hz_actual} unit="Hz" />

                  {/* OTA specific */}
                  {metrics.dl.transfer_progress_pct !== undefined && (
                    <>
                      <LiveMetric label="Transfer" value={metrics.dl.transfer_progress_pct} unit="%" />
                      <div className="w-full h-2 bg-lab-bg rounded-full overflow-hidden">
                        <div
                          className="h-full bg-primary rounded-full transition-all duration-500"
                          style={{ width: `${metrics.dl.transfer_progress_pct ?? 0}%` }}
                        />
                      </div>
                    </>
                  )}
                </div>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  );
}

/* ── Sub-components ── */

function SessionStatusBox({
  activeSession,
  metrics,
}: {
  activeSession: ActiveSessionInfo | null;
  metrics: SSEMetricEvent | null;
}) {
  if (!activeSession) return null;

  return (
    <div className="lab-card border-primary/30">
      <div className="flex items-center justify-between mb-2">
        <h3 className="text-xs font-semibold text-lab-muted uppercase tracking-wider">
          Active Session
        </h3>
        <StatusBadge status={metrics?.state ?? activeSession.state} size="sm" />
      </div>
      <p className="font-mono-data text-sm text-lab-text">{activeSession.session_id}</p>
      {metrics && (
        <p className="text-xs text-lab-muted mt-1">
          Elapsed: {formatElapsed(metrics.elapsed_s)}
        </p>
      )}
    </div>
  );
}

function ConfigRow({ label, value, mono }: { label: string; value: string; mono?: boolean }) {
  return (
    <div className="flex justify-between items-center text-sm">
      <span className="text-lab-muted">{label}</span>
      <span className={`text-lab-text ${mono ? "font-mono-data" : ""}`}>{value}</span>
    </div>
  );
}

function LiveMetric({
  label,
  value,
  unit,
  decimals = 1,
  threshold,
}: {
  label: string;
  value: number | null | undefined;
  unit: string;
  decimals?: number;
  threshold?: { value: number; op: string };
}) {
  const formatted = value !== null && value !== undefined
    ? (decimals === 0 ? Math.round(value).toLocaleString("en-US") : value.toFixed(decimals))
    : "—";

  // Check if threshold is breached
  let breaching = false;
  if (threshold && value !== null && value !== undefined) {
    if (threshold.op === "<=" && value > threshold.value) breaching = true;
    if (threshold.op === ">=" && value < threshold.value) breaching = true;
  }

  return (
    <div className={`flex justify-between items-center text-sm px-2 py-1 rounded ${
      breaching ? "bg-fail/10" : ""
    }`}>
      <span className="text-lab-muted text-xs">{label}</span>
      <span className={`font-mono-data font-semibold ${breaching ? "text-fail" : "text-lab-text"}`}>
        {formatted}{unit ? ` ${unit}` : ""}
      </span>
    </div>
  );
}
