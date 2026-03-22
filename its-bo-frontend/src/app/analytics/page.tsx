"use client";

import { useEffect, useState, useCallback } from "react";
import dynamic from "next/dynamic";
import { getResultsHistory, getResultById } from "@/lib/api";
import { formatDate } from "@/lib/format";
import type { TestResult, ResultHistoryItem } from "@/lib/types";

// Dynamic import chart wrappers – SSR disabled
const PassRateChart   = dynamic(() => import("@/components/Charts").then(m => m.PassRateChart),   { ssr: false });
const ThroughputChart = dynamic(() => import("@/components/Charts").then(m => m.ThroughputChart), { ssr: false });
const RTTChart        = dynamic(() => import("@/components/Charts").then(m => m.RTTChart),        { ssr: false });

export default function AnalyticsPage() {
  const [history, setHistory] = useState<ResultHistoryItem[]>([]);
  const [results, setResults] = useState<TestResult[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError]     = useState<string | null>(null);

  useEffect(() => {
    async function load() {
      try {
        const hist = await getResultsHistory();
        setHistory(hist);

        // Load full results for charts (limit to latest 50)
        const recent = hist.slice(0, 50);
        const full = await Promise.all(
          recent.map(async (h) => {
            try {
              return await getResultById(h.test_id);
            } catch {
              return null;
            }
          })
        );
        setResults(full.filter((r): r is TestResult => r !== null));
        setError(null);
      } catch (e) {
        // 404 = no results yet, treat as empty
        const msg = e instanceof Error ? e.message : String(e);
        if (msg.includes("404")) {
          setHistory([]);
          setResults([]);
          setError(null);
        } else {
          setError(`Backend nedostupný: ${msg}`);
        }
      } finally {
        setLoading(false);
      }
    }
    load();
  }, []);

  // ── Chart data builders ──
  const passRateByUC = (() => {
    const map: Record<string, { uc: string; pass: number; fail: number; total: number }> = {};
    history.forEach(r => {
      if (!map[r.uc_profile]) map[r.uc_profile] = { uc: r.uc_profile, pass: 0, fail: 0, total: 0 };
      map[r.uc_profile].total++;
      if (r.overall_pass) map[r.uc_profile].pass++;
      else map[r.uc_profile].fail++;
    });
    return Object.values(map);
  })();

  const throughputTrend = results
    .filter(r => r.measured?.ul?.throughput_mbps != null)
    .map(r => ({
      date: formatDate(r.started_at),
      uc: r.uc_profile,
      throughput: r.measured.ul!.throughput_mbps,
    }))
    .reverse();

  const rttTrend = results
    .filter(r => r.measured?.dl?.avg_rtt_ms != null)
    .map(r => ({
      date: formatDate(r.started_at),
      uc: r.uc_profile,
      rtt: r.measured.dl!.avg_rtt_ms,
      p95: r.measured.dl!.p95_rtt_ms,
    }))
    .reverse();

  // CSV export
  const handleExportCSV = useCallback(() => {
    if (results.length === 0) return;
    const headers = ["test_id", "uc_profile", "network", "overall_pass", "started_at", "duration_s"];
    const rows = results.map(r => [
      r.test_id, r.uc_profile, r.network_condition, String(r.overall_pass),
      r.started_at, String(r.duration_s),
    ]);
    const csv = [headers.join(","), ...rows.map(r => r.join(","))].join("\n");
    const blob = new Blob([csv], { type: "text/csv" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `its-bo-analytics-${new Date().toISOString().slice(0,10)}.csv`;
    a.click();
    URL.revokeObjectURL(url);
  }, [results]);

  if (loading) {
    return (
      <div className="p-6 space-y-6 animate-fade-in">
        {[1,2,3].map(i => <div key={i} className="lab-card animate-pulse h-64" />)}
      </div>
    );
  }

  return (
    <div className="p-6 space-y-8 animate-fade-in">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-lg font-semibold text-lab-text">Analytics</h1>
          <p className="text-xs text-lab-muted mt-0.5">
            Aggregated data from {history.length} test runs
          </p>
        </div>
        <button onClick={handleExportCSV} className="lab-btn lab-btn-outline text-xs">
          📥 Export CSV
        </button>
      </div>

      {error && (
        <div className="px-4 py-3 bg-fail/10 border border-fail/30 rounded-lg text-sm text-fail">
          {error}
        </div>
      )}

      {history.length === 0 ? (
        <div className="text-center py-20">
          <p className="text-3xl mb-3">📈</p>
          <p className="text-lab-muted">Žádná data pro analýzu</p>
          <p className="text-xs text-lab-muted/60 mt-1">Spusťte testy z OBU app</p>
        </div>
      ) : (
        <>
          {/* Summary cards */}
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
            <SummaryCard label="Total Tests" value={String(history.length)} />
            <SummaryCard
              label="Pass Rate"
              value={`${((history.filter(r => r.overall_pass).length / history.length) * 100).toFixed(0)}%`}
              accent
            />
            <SummaryCard
              label="Unique UCs"
              value={String(Array.from(new Set(history.map(r => r.uc_profile))).length)}
            />
            <SummaryCard
              label="Networks"
              value={String(Array.from(new Set(history.map(r => r.network_condition))).length)}
            />
          </div>

          {/* Pass/Fail by UC */}
          <div className="lab-card">
            <h3 className="text-sm font-semibold text-lab-text mb-4">Pass / Fail by UC</h3>
            <div className="h-[300px]">
              <PassRateChart data={passRateByUC} />
            </div>
          </div>

          {/* Throughput trend */}
          {throughputTrend.length > 0 && (
            <div className="lab-card">
              <h3 className="text-sm font-semibold text-lab-text mb-4">UL Throughput Trend</h3>
              <div className="h-[300px]">
                <ThroughputChart data={throughputTrend} />
              </div>
            </div>
          )}

          {/* RTT trend */}
          {rttTrend.length > 0 && (
            <div className="lab-card">
              <h3 className="text-sm font-semibold text-lab-text mb-4">RTT Trend (Avg + p95)</h3>
              <div className="h-[300px]">
                <RTTChart data={rttTrend} />
              </div>
            </div>
          )}
        </>
      )}
    </div>
  );
}

function SummaryCard({ label, value, accent }: { label: string; value: string; accent?: boolean }) {
  return (
    <div className="lab-card text-center">
      <p className="text-xs text-lab-muted mb-1">{label}</p>
      <p className={`text-2xl font-mono-data font-bold ${accent ? "text-primary" : "text-lab-text"}`}>
        {value}
      </p>
    </div>
  );
}
