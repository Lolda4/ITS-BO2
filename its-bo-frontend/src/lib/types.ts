/* ══════════════════════════════════════════
   ITS-BO TypeScript types – mirrors backend JSON schema
   ══════════════════════════════════════════ */

// ── UC Profile ──
export interface UCProfile {
  id: string;                        // "UC-A"
  name: string;                      // "Extended Sensors / SDSM"
  standard_ref: string;              // "3GPP TS 22.186 …"
  description: string;
  communication_pattern: "UL_ONLY" | "DL_ONLY" | "BIDIRECTIONAL" | "BIDIRECTIONAL_ASYMMETRIC";
  ul_transport: string;
  dl_transport: string;
  thresholds: Record<string, ThresholdDef>;
  default_params: Record<string, number | string>;
  baseline_required: boolean;
  min_repetitions: number;
  default_duration_s: number;
}

export interface ThresholdDef {
  value: number;
  op: "<=" | ">=" | "==";
  ref: string;
}

// ── Session ──
export interface SessionInitResponse {
  session_id: string;
  server_ready: boolean;
  allocated_ports: { burst_port: number; control_port: number };
  effective_params: Record<string, number | string>;
  duration_s: number;
  preflight_warnings: PreflightWarning[];
}

export interface PreflightWarning {
  level: "warning" | "error";
  msg: string;
}

export type SessionState =
  | "INIT" | "BASELINE" | "READY" | "RUNNING"
  | "COMPLETED" | "INTERRUPTED" | "ERROR"
  | "WAITING";

// ── System Status ──
export interface SystemStatus {
  status: "online" | "offline";
  plugins: {
    loaded: { uc_id: string; name: string }[];
    errors: Record<string, string>;
  };
  ports: {
    free_burst: number;
    free_control: number;
    active_sessions: number;
  };
  active_sessions?: ActiveSessionInfo[];
}

export interface ActiveSessionInfo {
  session_id: string;
  uc_id: string;
  state: SessionState;
  started_at?: string;
  elapsed_s?: number;
}

// ── SSE Metric Event ──
export interface SSEMetricEvent {
  session_id: string;
  state: SessionState;
  elapsed_s: number;
  ul?: {
    throughput_mbps: number;
    packet_loss_pct: number;
    jitter_ms: number;
    packets_received: number;
    bytes_received: number;
    kernel_buffer_drops: number;
  };
  dl?: {
    avg_rtt_ms: number | null;
    min_rtt_ms: number | null;
    max_rtt_ms: number | null;
    p50_rtt_ms: number | null;
    p95_rtt_ms: number | null;
    p99_rtt_ms: number | null;
    jitter_ms: number;
    packet_loss_pct: number;
    packets_sent: number;
    acks_received: number;
    control_loop_hz_actual: number;
    rtt_sample_count: number;
    // OTA specific
    chunks_sent?: number;
    chunks_acked?: number;
    bytes_transferred?: number;
    transfer_progress_pct?: number;
  };
}

// ── Test Result ──
export interface TestResult {
  test_id: string;
  uc_profile: string;
  uc_name: string;
  standard_reference: string;
  session_status: SessionState;
  network_condition: string;
  lab_config?: Record<string, unknown>;
  label: string;
  started_at: string;
  duration_s: number;
  duration_actual_s: number;
  obu_ip: string;
  effective_params: Record<string, number | string>;
  baseline?: {
    status: string;
    ping_rtt_avg_ms?: number;
    ping_rtt_min_ms?: number;
    ping_rtt_max_ms?: number;
    ping_rtt_mdev_ms?: number;
  };
  measured: {
    ul?: Record<string, number>;
    dl?: Record<string, number>;
  };
  obu_reported_stats?: {
    packets_sent: number;
    send_jitter_ms: number;
    gc_pause_detected: boolean;
    platform_overhead?: Record<string, number>;
  };
  packet_delivery_ratio_pct?: number;
  normative_thresholds: Record<string, ThresholdDef>;
  evaluation: Record<string, EvaluationEntry>;
  overall_pass: boolean;
  interpretation: string;
}

export interface EvaluationEntry {
  measured: number | null;
  threshold: number;
  op: string;
  pass: boolean;
  ref: string;
  note?: string;
}

// ── Results History ──
export interface ResultHistoryItem {
  test_id: string;
  uc_profile: string;
  uc_name: string;
  network_condition: string;
  overall_pass: boolean;
  started_at: string;
  duration_s: number;
  label: string;
  session_status: SessionState;
}
