"use client";

import { useEffect, useRef, useState } from "react";

interface ProgressEvent {
  type: string;
  data: Record<string, unknown>;
}

interface SchemaExecutionProgressProps {
  events: ProgressEvent[];
  isComplete: boolean;
}

export default function SchemaExecutionProgress({
  events,
  isComplete,
}: SchemaExecutionProgressProps) {
  const logsRef = useRef<HTMLDivElement>(null);
  const [displayProgress, setDisplayProgress] = useState(0);
  const animFrameRef = useRef<number | null>(null);

  useEffect(() => {
    if (logsRef.current) {
      logsRef.current.scrollTop = logsRef.current.scrollHeight;
    }
  }, [events]);

  const startEvent = events.find((e) => e.type === "schema_start");
  const totalParams = (startEvent?.data?.total_params as number) || 0;
  const totalPages = (startEvent?.data?.total_pages as number) || 0;
  const resultEvents = events.filter((e) => e.type === "param_result");
  const pageStartEvents = events.filter((e) => e.type === "page_start");
  const foundCount = resultEvents.filter((e) => e.data.found).length;
  const realProgress = totalParams > 0 ? Math.round((resultEvents.length / totalParams) * 100) : 0;

  // Count verify results
  const verifyResults = resultEvents.filter((e) => e.data.task_type === "verify");
  const passCount = verifyResults.filter((e) => e.data.status === "pass").length;
  const failCount = verifyResults.filter((e) => e.data.status === "fail").length;
  const warnCount = verifyResults.filter((e) => e.data.status === "warning").length;
  const extractResults = resultEvents.filter((e) => (e.data.task_type || "extract") === "extract");
  const hasVerify = verifyResults.length > 0;

  // Intelligent animated progress:
  // - Starts at 2% when processing begins (so user sees movement immediately)
  // - Crawls slowly between events (page_start bumps it forward)
  // - Jumps to real progress when param_result arrives
  // - Smoothly fills to 100% on complete
  const targetProgress = isComplete
    ? 100
    : events.length === 0
      ? 0
      : Math.max(
          // At least 2% once started
          startEvent ? 2 : 0,
          // page_start events contribute partial progress (each page = a fraction of work)
          totalPages > 0 ? Math.round((pageStartEvents.length / totalPages) * 40) : 0,
          // Real result progress mapped to 40-95% range
          totalParams > 0 ? 40 + Math.round((resultEvents.length / totalParams) * 55) : 0,
          realProgress
        );

  // Smooth animation: crawl displayProgress toward targetProgress
  useEffect(() => {
    if (animFrameRef.current) cancelAnimationFrame(animFrameRef.current);

    const animate = () => {
      setDisplayProgress((prev) => {
        if (isComplete) {
          // Fast fill to 100%
          const next = prev + Math.max(2, (100 - prev) * 0.15);
          return next >= 99.5 ? 100 : next;
        }
        if (prev >= targetProgress) return prev;
        // Slow crawl: move 8% of the remaining gap each frame
        const gap = targetProgress - prev;
        const step = Math.max(0.1, gap * 0.08);
        return Math.min(prev + step, targetProgress);
      });
      animFrameRef.current = requestAnimationFrame(animate);
    };
    animFrameRef.current = requestAnimationFrame(animate);

    return () => {
      if (animFrameRef.current) cancelAnimationFrame(animFrameRef.current);
    };
  }, [targetProgress, isComplete]);

  // Slow background crawl: even when no events arrive, nudge progress slightly
  useEffect(() => {
    if (isComplete || !startEvent) return;
    const interval = setInterval(() => {
      setDisplayProgress((prev) => {
        // Don't crawl past 90% without real events
        if (prev >= 90 || prev >= targetProgress) return prev;
        return prev + 0.3;
      });
    }, 1000);
    return () => clearInterval(interval);
  }, [isComplete, startEvent, targetProgress]);

  const displayPct = Math.round(displayProgress);

  const statusLabel = isComplete
    ? hasVerify
      ? `Done: ${extractResults.filter(e => e.data.found).length} extracted | ${passCount} pass / ${failCount} fail / ${warnCount} warning`
      : `Done: ${foundCount} of ${totalParams} extracted`
    : startEvent
      ? `Processing: ${resultEvents.length} of ${totalParams}`
      : "Preparing...";

  return (
    <div className="flex flex-col h-full">
      {/* Progress header */}
      <div className="px-4 py-3 border-b border-gray-100">
        <div className="flex items-center justify-between mb-1.5">
          <span className="text-xs text-gray-500">{statusLabel}</span>
          <span className={`text-xs font-medium ${isComplete ? "text-green-600" : "text-cyan-600"}`}>{displayPct}%</span>
        </div>
        <div className="h-1.5 bg-gray-100 rounded-full overflow-hidden">
          <div
            className={`h-full rounded-full ${
              isComplete ? "bg-green-500" : "bg-gradient-to-r from-cyan-400 to-cyan-600"
            }`}
            style={{
              width: `${displayPct}%`,
              transition: isComplete ? "width 0.5s ease-out" : "none",
            }}
          />
        </div>
        {totalPages > 0 && !isComplete && (
          <div className="text-[11px] text-gray-400 mt-1">
            Analyzing {pageStartEvents.length > 0 ? `page ${pageStartEvents.length} of ` : ""}{totalPages} page{totalPages !== 1 ? "s" : ""}
          </div>
        )}
      </div>

      {/* Log output */}
      <div ref={logsRef} className="flex-1 overflow-y-auto px-4 py-3 space-y-0.5">
        {events.map((event, i) => {
          if (event.type === "page_start") {
            const d = event.data;
            const params = d.params as string[];
            return (
              <div key={i} className="text-xs text-gray-500 mt-2 mb-1">
                Page {d.page as number} ({params.length} param{params.length !== 1 ? "s" : ""})
              </div>
            );
          }
          if (event.type === "param_result") {
            const d = event.data;
            const found = d.found as boolean;
            const taskType = d.task_type as string;

            if (taskType === "verify") {
              const status = d.status as string;
              const finding = d.finding as string;
              const statusColor = status === "pass" ? "text-green-600" : status === "fail" ? "text-red-600" : "text-amber-600";
              const statusBg = status === "pass" ? "bg-green-50" : status === "fail" ? "bg-red-50" : "bg-amber-50";
              const statusBorder = status === "pass" ? "border-green-200" : status === "fail" ? "border-red-200" : "border-amber-200";
              return (
                <div key={i} className="text-xs flex items-start gap-1.5 py-0.5">
                  <span className={`px-1 py-0.5 text-[9px] font-bold rounded border flex-shrink-0 ${statusColor} ${statusBg} ${statusBorder}`}>
                    {(status || "?").toUpperCase()}
                  </span>
                  <span className="font-medium text-gray-700">{d.param_name as string}</span>
                  {finding && (
                    <span className="text-gray-400 truncate">{String(finding).substring(0, 60)}</span>
                  )}
                </div>
              );
            }

            // Extract result (default)
            return (
              <div key={i} className={`text-xs flex items-center gap-1.5 py-0.5 ${found ? "text-gray-700" : "text-gray-400"}`}>
                <span className={`w-3.5 text-center ${found ? "text-green-500" : "text-gray-300"}`}>
                  {found ? "\u2713" : "\u2717"}
                </span>
                <span className="font-medium">{d.param_name as string}</span>
                {found && !!(d as Record<string, unknown>).value && (
                  <span className="text-gray-400">= {String((d as Record<string, unknown>).value).substring(0, 40)}</span>
                )}
              </div>
            );
          }
          if (event.type === "error") {
            return (
              <div key={i} className="text-xs text-red-500 mt-1">
                Error: {event.data.error as string}
              </div>
            );
          }
          return null;
        })}
      </div>
    </div>
  );
}
