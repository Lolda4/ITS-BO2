"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { getResultsHistory } from "@/lib/api";
import { formatDate } from "@/lib/format";
import { NETWORK_CONDITIONS } from "@/lib/config";
import type { ResultHistoryItem } from "@/lib/types";
import StatusBadge from "@/components/StatusBadge";

export default function ResultsPage() {
  const [results, setResults]   = useState<ResultHistoryItem[]>([]);
  const [loading, setLoading]   = useState(true);
  const [error, setError]       = useState<string | null>(null);

  // Filters
  const [filterUC, setFilterUC]                   = useState("");
  const [filterNetwork, setFilterNetwork]         = useState("");
  const [filterPass, setFilterPass]               = useState<"" | "pass" | "fail">("");

  useEffect(() => {
    async function load() {
      try {
        const data = await getResultsHistory();
        setResults(data);
        setError(null);
      } catch (e) {
        // 404 = no results yet, treat as empty
        const msg = e instanceof Error ? e.message : String(e);
        if (msg.includes("404")) {
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

  // Apply filters
  const filtered = results.filter(r => {
    if (filterUC && r.uc_profile !== filterUC) return false;
    if (filterNetwork && r.network_condition !== filterNetwork) return false;
    if (filterPass === "pass" && !r.overall_pass) return false;
    if (filterPass === "fail" && r.overall_pass) return false;
    return true;
  });

  const uniqueUCs      = Array.from(new Set(results.map(r => r.uc_profile)));
  const uniqueNetworks = Array.from(new Set(results.map(r => r.network_condition)));

  return (
    <div className="p-6 space-y-6 animate-fade-in">
      {/* Header */}
      <div>
        <h1 className="text-lg font-semibold text-lab-text">Test Results History</h1>
        <p className="text-xs text-lab-muted mt-0.5">
          {results.length} total results · {filtered.length} matching filters
        </p>
      </div>

      {/* Filters */}
      <div className="flex flex-wrap gap-3">
        <select
          value={filterUC}
          onChange={e => setFilterUC(e.target.value)}
          className="lab-input !w-auto min-w-[140px]"
        >
          <option value="">All UCs</option>
          {uniqueUCs.map(uc => (
            <option key={uc} value={uc}>{uc}</option>
          ))}
        </select>

        <select
          value={filterNetwork}
          onChange={e => setFilterNetwork(e.target.value)}
          className="lab-input !w-auto min-w-[180px]"
        >
          <option value="">All Networks</option>
          {uniqueNetworks.map(n => (
            <option key={n} value={n}>{NETWORK_CONDITIONS[n] ?? n}</option>
          ))}
        </select>

        <select
          value={filterPass}
          onChange={e => setFilterPass(e.target.value as "" | "pass" | "fail")}
          className="lab-input !w-auto min-w-[120px]"
        >
          <option value="">All Results</option>
          <option value="pass">PASS only</option>
          <option value="fail">FAIL only</option>
        </select>

        {(filterUC || filterNetwork || filterPass) && (
          <button
            onClick={() => { setFilterUC(""); setFilterNetwork(""); setFilterPass(""); }}
            className="lab-btn lab-btn-outline text-xs"
          >
            Clear filters
          </button>
        )}
      </div>

      {/* Error */}
      {error && (
        <div className="px-4 py-3 bg-fail/10 border border-fail/30 rounded-lg text-sm text-fail">
          {error}
        </div>
      )}

      {/* Table */}
      {loading ? (
        <div className="space-y-2">
          {[1,2,3,4,5].map(i => (
            <div key={i} className="lab-card animate-pulse h-14" />
          ))}
        </div>
      ) : filtered.length === 0 ? (
        <div className="text-center py-16">
          <p className="text-3xl mb-3">📋</p>
          <p className="text-lab-muted">Žádné výsledky</p>
          <p className="text-xs text-lab-muted/60 mt-1">
            {results.length > 0 ? "Zkuste upravit filtry" : "Spusťte test z OBU app"}
          </p>
        </div>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-lab-border">
                <th className="text-left py-3 px-4 text-xs text-lab-muted font-semibold uppercase tracking-wider">Test ID</th>
                <th className="text-left py-3 px-4 text-xs text-lab-muted font-semibold uppercase tracking-wider">UC</th>
                <th className="text-left py-3 px-4 text-xs text-lab-muted font-semibold uppercase tracking-wider">Network</th>
                <th className="text-left py-3 px-4 text-xs text-lab-muted font-semibold uppercase tracking-wider">Result</th>
                <th className="text-left py-3 px-4 text-xs text-lab-muted font-semibold uppercase tracking-wider">Status</th>
                <th className="text-left py-3 px-4 text-xs text-lab-muted font-semibold uppercase tracking-wider">Date</th>
                <th className="text-left py-3 px-4 text-xs text-lab-muted font-semibold uppercase tracking-wider">Duration</th>
                <th className="text-left py-3 px-4 text-xs text-lab-muted font-semibold uppercase tracking-wider">Label</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map(r => (
                <tr
                  key={r.test_id}
                  className="border-b border-lab-border/50 hover:bg-lab-card/50 transition-colors"
                >
                  <td className="py-3 px-4">
                    <Link
                      href={`/result/${r.test_id}`}
                      className="font-mono-data text-xs text-primary hover:underline"
                    >
                      {r.test_id}
                    </Link>
                  </td>
                  <td className="py-3 px-4">
                    <span className="inline-block px-2 py-0.5 rounded bg-primary/10 text-primary text-xs font-semibold">
                      {r.uc_profile}
                    </span>
                  </td>
                  <td className="py-3 px-4 text-xs text-lab-muted">
                    {NETWORK_CONDITIONS[r.network_condition] ?? r.network_condition}
                  </td>
                  <td className="py-3 px-4">
                    <span className={`inline-block px-2 py-0.5 rounded text-xs font-bold
                      ${r.overall_pass ? "bg-pass/20 text-pass" : "bg-fail/20 text-fail"}`}>
                      {r.overall_pass ? "PASS" : "FAIL"}
                    </span>
                  </td>
                  <td className="py-3 px-4">
                    <StatusBadge status={r.session_status} size="sm" />
                  </td>
                  <td className="py-3 px-4 text-xs text-lab-muted font-mono-data">
                    {formatDate(r.started_at)}
                  </td>
                  <td className="py-3 px-4 text-xs text-lab-muted font-mono-data">
                    {r.duration_s}s
                  </td>
                  <td className="py-3 px-4 text-xs text-lab-muted truncate max-w-[200px]">
                    {r.label || "—"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
