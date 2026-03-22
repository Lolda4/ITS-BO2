"use client";

import { useEffect, useState, useCallback } from "react";
import { useParams } from "next/navigation";
import { getResultById } from "@/lib/api";
import { formatMetric, formatDate, type MetricType } from "@/lib/format";
import { NETWORK_CONDITIONS } from "@/lib/config";
import type { TestResult } from "@/lib/types";
import PassFailBadge from "@/components/PassFailBadge";
import StatusBadge from "@/components/StatusBadge";
import MetricRow from "@/components/MetricRow";
import JsonViewer from "@/components/JsonViewer";

/** Map metric keys to format types */
function metricTypeFor(key: string): MetricType {
  if (key.includes("throughput")) return "throughput";
  if (key.includes("latency") || key.includes("rtt")) return "rtt";
  if (key.includes("reliability") || key.includes("pct")) return "percent";
  if (key.includes("loss")) return "loss";
  return "generic";
}

export default function ResultDetailPage() {
  const params = useParams();
  const testId = params.id as string;
  const [result, setResult]   = useState<TestResult | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError]     = useState<string | null>(null);

  useEffect(() => {
    if (!testId) return;
    async function load() {
      try {
        const data = await getResultById(testId);
        setResult(data);
        setError(null);
      } catch (e) {
        setError(`Výsledek nenalezen: ${e instanceof Error ? e.message : String(e)}`);
      } finally {
        setLoading(false);
      }
    }
    load();
  }, [testId]);

  const handleExportJSON = useCallback(() => {
    if (!result) return;
    const blob = new Blob([JSON.stringify(result, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `${result.test_id}.json`;
    a.click();
    URL.revokeObjectURL(url);
  }, [result]);

  const handleExportCSV = useCallback(() => {
    if (!result) return;
    const rows: string[][] = [["Metric", "Measured", "Threshold", "Operator", "Pass", "Reference"]];
    for (const [key, ev] of Object.entries(result.evaluation)) {
      rows.push([
        key,
        ev.measured !== null ? String(ev.measured) : "",
        String(ev.threshold),
        ev.op,
        ev.pass ? "PASS" : "FAIL",
        ev.ref,
      ]);
    }
    const csv = rows.map(r => r.join(",")).join("\n");
    const blob = new Blob([csv], { type: "text/csv" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `${result.test_id}.csv`;
    a.click();
    URL.revokeObjectURL(url);
  }, [result]);

  if (loading) {
    return (
      <div className="p-6 space-y-4 animate-fade-in">
        <div className="lab-card animate-pulse h-20" />
        <div className="lab-card animate-pulse h-40" />
      </div>
    );
  }

  if (error || !result) {
    return (
      <div className="p-6 animate-fade-in">
        <div className="text-center py-16">
          <p className="text-3xl mb-3">🔍</p>
          <p className="text-fail text-sm">{error ?? "Session nenalezena"}</p>
          <p className="text-xs text-lab-muted mt-2 font-mono-data">{testId}</p>
        </div>
      </div>
    );
  }

  return (
    <div className="p-6 space-y-6 animate-fade-in max-w-5xl">
      {/* Header */}
      <div className="flex items-start justify-between">
        <div>
          <div className="flex items-center gap-3 mb-2">
            <span className="px-3 py-1 rounded-lg bg-primary/20 text-primary font-bold text-sm">
              {result.uc_profile}
            </span>
            <StatusBadge status={result.session_status} />
          </div>
          <h1 className="text-lg font-semibold text-lab-text">{result.uc_name}</h1>
          <p className="text-xs font-mono-data text-lab-muted mt-1">{result.test_id}</p>
        </div>
        <div className="flex gap-2">
          <button onClick={handleExportJSON} className="lab-btn lab-btn-outline text-xs">
            📥 JSON
          </button>
          <button onClick={handleExportCSV} className="lab-btn lab-btn-outline text-xs">
            📥 CSV
          </button>
        </div>
      </div>

      {/* PASS / FAIL */}
      <PassFailBadge pass={result.overall_pass} interpretation={result.interpretation} />

      {/* Metadata grid */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <MetaCard label="Network" value={NETWORK_CONDITIONS[result.network_condition] ?? result.network_condition} />
        <MetaCard label="Date" value={formatDate(result.started_at)} />
        <MetaCard label="Duration" value={`${result.duration_actual_s}s / ${result.duration_s}s`} mono />
        <MetaCard label="OBU IP" value={result.obu_ip} mono />
      </div>

      {/* Standard reference */}
      <div className="lab-card">
        <p className="text-xs text-lab-muted">Standard Reference</p>
        <p className="text-sm font-mono-data text-lab-text mt-1">{result.standard_reference}</p>
      </div>

      {/* Baseline */}
      {result.baseline && (
        <div className="lab-card">
          <h3 className="text-xs font-semibold text-lab-muted uppercase tracking-wider mb-3">
            Baseline
          </h3>
          <div className="flex gap-6 text-sm">
            <span className="text-lab-muted">Status: <span className="text-lab-text">{result.baseline.status}</span></span>
            {result.baseline.ping_rtt_avg_ms != null && (
              <>
                <span className="text-lab-muted">Avg RTT: <span className="font-mono-data text-lab-text">{result.baseline.ping_rtt_avg_ms} ms</span></span>
                <span className="text-lab-muted">Min: <span className="font-mono-data text-lab-text">{result.baseline.ping_rtt_min_ms} ms</span></span>
                <span className="text-lab-muted">Max: <span className="font-mono-data text-lab-text">{result.baseline.ping_rtt_max_ms} ms</span></span>
              </>
            )}
          </div>
        </div>
      )}

      {/* Evaluation table */}
      <div className="space-y-2">
        <h3 className="text-xs font-semibold text-lab-muted uppercase tracking-wider">
          Metric Evaluation
        </h3>
        {Object.entries(result.evaluation).map(([key, entry]) => (
          <MetricRow key={key} label={key} entry={entry} metricType={metricTypeFor(key)} />
        ))}
      </div>

      {/* Packet delivery ratio */}
      {result.packet_delivery_ratio_pct != null && (
        <div className="lab-card">
          <h3 className="text-xs font-semibold text-lab-muted uppercase tracking-wider mb-2">
            Packet Delivery Ratio
          </h3>
          <p className="text-2xl font-mono-data font-bold text-lab-text">
            {formatMetric(result.packet_delivery_ratio_pct, "percent")}
          </p>
          {result.obu_reported_stats && (
            <p className="text-xs text-lab-muted mt-1">
              OBU sent: {result.obu_reported_stats.packets_sent.toLocaleString("en-US")} packets
            </p>
          )}
        </div>
      )}

      {/* Lab config */}
      {result.lab_config && Object.keys(result.lab_config).length > 0 && (
        <div className="lab-card">
          <h3 className="text-xs font-semibold text-lab-muted uppercase tracking-wider mb-3">
            Lab Configuration
          </h3>
          <div className="space-y-1">
            {Object.entries(result.lab_config).map(([k, v]) => (
              <div key={k} className="flex justify-between text-sm">
                <span className="text-lab-muted">{k}</span>
                <span className="font-mono-data text-lab-text">{String(v)}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Effective params */}
      <div className="lab-card">
        <h3 className="text-xs font-semibold text-lab-muted uppercase tracking-wider mb-3">
          Effective Parameters
        </h3>
        <div className="space-y-1">
          {Object.entries(result.effective_params).map(([k, v]) => (
            <div key={k} className="flex justify-between text-sm">
              <span className="text-lab-muted">{k.replace(/_/g, " ")}</span>
              <span className="font-mono-data text-lab-text">{String(v)}</span>
            </div>
          ))}
        </div>
      </div>

      {/* Label */}
      {result.label && (
        <div className="lab-card">
          <p className="text-xs text-lab-muted">Label</p>
          <p className="text-sm text-lab-text mt-1">{result.label}</p>
        </div>
      )}

      {/* Raw JSON */}
      <JsonViewer data={result} title="Raw JSON Result" />
    </div>
  );
}

function MetaCard({ label, value, mono }: { label: string; value: string; mono?: boolean }) {
  return (
    <div className="lab-card">
      <p className="text-xs text-lab-muted mb-1">{label}</p>
      <p className={`text-sm text-lab-text ${mono ? "font-mono-data" : ""}`}>{value}</p>
    </div>
  );
}
