"use client";

import { useState, useCallback } from "react";

interface JsonViewerProps {
  data: unknown;
  title?: string;
  defaultExpanded?: boolean;
}

export default function JsonViewer({ data, title = "Raw JSON", defaultExpanded = false }: JsonViewerProps) {
  const [expanded, setExpanded] = useState(defaultExpanded);
  const [copied, setCopied]     = useState(false);

  const jsonStr = JSON.stringify(data, null, 2);

  const handleCopy = useCallback(async () => {
    try {
      await navigator.clipboard.writeText(jsonStr);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      // fallback: textarea copy
      const ta = document.createElement("textarea");
      ta.value = jsonStr;
      document.body.appendChild(ta);
      ta.select();
      document.execCommand("copy");
      document.body.removeChild(ta);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
  }, [jsonStr]);

  return (
    <div className="lab-card">
      <div className="flex items-center justify-between mb-2">
        <button
          onClick={() => setExpanded(!expanded)}
          className="flex items-center gap-2 text-sm font-medium text-lab-text hover:text-primary transition-colors"
        >
          <span className={`transform transition-transform ${expanded ? "rotate-90" : ""}`}>
            ▶
          </span>
          {title}
        </button>
        {expanded && (
          <button
            onClick={handleCopy}
            className="lab-btn lab-btn-outline text-xs !py-1 !px-2"
          >
            {copied ? "✓ Copied" : "📋 Copy"}
          </button>
        )}
      </div>
      {expanded && (
        <pre className="font-mono-data text-xs text-lab-muted bg-lab-bg rounded-lg p-4 overflow-x-auto max-h-[500px] overflow-y-auto leading-relaxed">
          {jsonStr}
        </pre>
      )}
    </div>
  );
}
