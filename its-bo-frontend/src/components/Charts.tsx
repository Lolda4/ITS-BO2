"use client";

import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid,
  Tooltip, Legend, LineChart, Line, ResponsiveContainer,
} from "recharts";

/* ── Chart wrappers for dynamic import with SSR disabled ── */

export function PassRateChart({ data }: { data: { uc: string; pass: number; fail: number }[] }) {
  return (
    <ResponsiveContainer width="100%" height="100%">
      <BarChart data={data}>
        <CartesianGrid strokeDasharray="3 3" stroke="#252B3B" />
        <XAxis dataKey="uc" stroke="#64748B" fontSize={12} />
        <YAxis stroke="#64748B" fontSize={12} />
        <Tooltip
          contentStyle={{ background: "#1A1F2E", border: "1px solid #252B3B", borderRadius: "8px" }}
          labelStyle={{ color: "#E2E8F0" }}
        />
        <Legend />
        <Bar dataKey="pass" fill="#22C55E" name="PASS" radius={[4, 4, 0, 0]} />
        <Bar dataKey="fail" fill="#EF4444" name="FAIL" radius={[4, 4, 0, 0]} />
      </BarChart>
    </ResponsiveContainer>
  );
}

export function ThroughputChart({ data }: { data: { date: string; throughput: number }[] }) {
  return (
    <ResponsiveContainer width="100%" height="100%">
      <LineChart data={data}>
        <CartesianGrid strokeDasharray="3 3" stroke="#252B3B" />
        <XAxis dataKey="date" stroke="#64748B" fontSize={10} angle={-20} textAnchor="end" />
        <YAxis stroke="#64748B" fontSize={12} unit=" Mbps" />
        <Tooltip
          contentStyle={{ background: "#1A1F2E", border: "1px solid #252B3B", borderRadius: "8px" }}
          labelStyle={{ color: "#E2E8F0" }}
        />
        <Line type="monotone" dataKey="throughput" stroke="#3B82F6" strokeWidth={2} dot={{ r: 3 }} name="Throughput" />
      </LineChart>
    </ResponsiveContainer>
  );
}

export function RTTChart({ data }: { data: { date: string; rtt: number; p95: number }[] }) {
  return (
    <ResponsiveContainer width="100%" height="100%">
      <LineChart data={data}>
        <CartesianGrid strokeDasharray="3 3" stroke="#252B3B" />
        <XAxis dataKey="date" stroke="#64748B" fontSize={10} angle={-20} textAnchor="end" />
        <YAxis stroke="#64748B" fontSize={12} unit=" ms" />
        <Tooltip
          contentStyle={{ background: "#1A1F2E", border: "1px solid #252B3B", borderRadius: "8px" }}
          labelStyle={{ color: "#E2E8F0" }}
        />
        <Legend />
        <Line type="monotone" dataKey="rtt" stroke="#3B82F6" strokeWidth={2} dot={{ r: 3 }} name="Avg RTT" />
        <Line type="monotone" dataKey="p95" stroke="#F59E0B" strokeWidth={2} dot={{ r: 3 }} name="p95 RTT" />
      </LineChart>
    </ResponsiveContainer>
  );
}
