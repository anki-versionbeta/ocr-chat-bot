"use client";

import { ParamResult, ExecutionSummary, getExecutionDownloadUrl } from "../../services/schemaService";

interface SchemaResultsPanelProps {
  results: ParamResult[];
  summary: ExecutionSummary | null;
  executionId: string | null;
  onViewResult: (page: number, ref: string | null) => void;
  onBack: () => void;
}

function StatusBadge({ status }: { status: string }) {
  const styles: Record<string, string> = {
    pass: "bg-green-50 text-green-700 border-green-200",
    fail: "bg-red-50 text-red-700 border-red-200",
    warning: "bg-amber-50 text-amber-700 border-amber-200",
  };
  return (
    <span className={`inline-block px-1.5 py-0.5 text-[10px] font-bold rounded border whitespace-nowrap ${styles[status] || "bg-gray-50 text-gray-500 border-gray-200"}`}>
      {status.toUpperCase()}
    </span>
  );
}

export default function SchemaResultsPanel({
  results,
  summary,
  executionId,
  onViewResult,
  onBack,
}: SchemaResultsPanelProps) {
  const hasVerify = results.some((r) => r.task_type === "verify");

  const handleDownload = () => {
    if (!executionId) return;
    window.open(getExecutionDownloadUrl(executionId), "_blank");
  };

  // Summary text
  const extractResults = results.filter((r) => (r.task_type || "extract") === "extract");
  const summaryText = hasVerify
    ? `${extractResults.filter(r => r.found).length} extracted | ${summary?.verify_pass || 0} pass / ${summary?.verify_fail || 0} fail / ${summary?.verify_warning || 0} warning`
    : `${summary?.found || 0}/${summary?.total_params || 0}`;

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-gray-100">
        <button
          onClick={onBack}
          className="flex items-center text-xs text-gray-500 hover:text-gray-700"
        >
          <svg className="w-4 h-4 mr-1" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M15 19l-7-7 7-7" />
          </svg>
          Back
        </button>
        <div className="flex items-center gap-2">
          {summary && (
            <span className="text-xs text-gray-400">{summaryText}</span>
          )}
          {executionId && (
            <button
              onClick={handleDownload}
              className="flex items-center gap-1 px-2.5 py-1 text-xs font-medium text-cyan-600 bg-cyan-50 hover:bg-cyan-100 rounded-md transition-colors"
            >
              <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M12 10v6m0 0l-3-3m3 3l3-3m2 8H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
              </svg>
              Excel
            </button>
          )}
        </div>
      </div>

      {/* Results */}
      <div className="flex-1 overflow-auto">
        {hasVerify ? (
          /* ============================================================
             VERIFICATION TABLE — separate columns for each field
             ============================================================ */
          <div className="min-w-0">
            <table className="w-full text-xs border-collapse">
              <thead className="bg-gray-50 sticky top-0 z-10">
                <tr className="text-left text-gray-500">
                  <th className="px-3 py-2 font-medium whitespace-nowrap">Parameter</th>
                  <th className="px-2 py-2 font-medium whitespace-nowrap w-14">Status</th>
                  <th className="px-2 py-2 font-medium whitespace-nowrap">Finding</th>
                  <th className="px-2 py-2 font-medium whitespace-nowrap">Correction</th>
                  <th className="px-2 py-2 font-medium whitespace-nowrap">Performed By</th>
                  <th className="px-2 py-2 font-medium whitespace-nowrap">Witnessed By</th>
                  <th className="px-2 py-2 font-medium whitespace-nowrap w-8">Pg</th>
                  <th className="px-2 py-2 font-medium w-10"></th>
                </tr>
              </thead>
              <tbody>
                {results.map((r, i) => {
                  const isVerifyRow = r.task_type === "verify";
                  return (
                    <tr
                      key={i}
                      className={`border-b border-gray-100 hover:bg-gray-50/50 ${r.found ? "" : "opacity-50"}`}
                    >
                      {/* Parameter */}
                      <td className="px-3 py-2.5 text-gray-700 font-medium align-top whitespace-nowrap">
                        {r.param_name}
                      </td>

                      {/* Status */}
                      <td className="px-2 py-2.5 align-top">
                        {isVerifyRow && r.status ? (
                          <StatusBadge status={r.status} />
                        ) : !isVerifyRow && r.found ? (
                          <span className="text-gray-800">{r.value}</span>
                        ) : (
                          <span className="text-gray-400 italic">--</span>
                        )}
                      </td>

                      {/* Finding */}
                      <td className="px-2 py-2.5 align-top max-w-[200px]">
                        {isVerifyRow && r.finding ? (
                          <span className="text-gray-600 leading-snug text-[11px] break-words">{r.finding}</span>
                        ) : (
                          <span className="text-gray-300">—</span>
                        )}
                      </td>

                      {/* Correction */}
                      <td className="px-2 py-2.5 align-top whitespace-nowrap">
                        {isVerifyRow && r.correction ? (
                          <span className="text-gray-600 font-medium">{r.correction}</span>
                        ) : (
                          <span className="text-gray-300">—</span>
                        )}
                      </td>

                      {/* Performed By */}
                      <td className="px-2 py-2.5 align-top whitespace-nowrap">
                        {isVerifyRow && r.performed_by ? (
                          <span className="text-gray-600">{r.performed_by}</span>
                        ) : (
                          <span className="text-gray-300">—</span>
                        )}
                      </td>

                      {/* Witnessed By */}
                      <td className="px-2 py-2.5 align-top whitespace-nowrap">
                        {isVerifyRow && r.witnessed_by ? (
                          <span className={r.witnessed_by === "No Witness" ? "text-red-500 font-medium" : "text-gray-600"}>
                            {r.witnessed_by}
                          </span>
                        ) : (
                          <span className="text-gray-300">—</span>
                        )}
                      </td>

                      {/* Page */}
                      <td className="px-2 py-2.5 text-gray-400 align-top">{r.page || "--"}</td>

                      {/* View */}
                      <td className="px-2 py-2.5 align-top">
                        {r.found && r.page && (r.bbox || r.bboxes?.length) && (
                          <button
                            onClick={() => onViewResult(r.page, r.ref)}
                            className="text-cyan-500 hover:text-cyan-700 text-[11px] font-medium whitespace-nowrap"
                          >
                            View
                          </button>
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        ) : (
          /* ============================================================
             EXTRACT-ONLY TABLE — compact layout (unchanged)
             ============================================================ */
          <table className="w-full text-xs">
            <thead className="bg-gray-50 sticky top-0">
              <tr className="text-left text-gray-500">
                <th className="px-4 py-2 font-medium">Parameter</th>
                <th className="px-2 py-2 font-medium">Value</th>
                <th className="px-2 py-2 font-medium w-10">Pg</th>
                <th className="px-2 py-2 font-medium w-12"></th>
              </tr>
            </thead>
            <tbody>
              {results.map((r, i) => (
                <tr
                  key={i}
                  className={`border-b border-gray-50 ${r.found ? "" : "opacity-50"}`}
                >
                  <td className="px-4 py-2 text-gray-700 font-medium">{r.param_name}</td>
                  <td className="px-2 py-2">
                    {r.found ? (
                      <span className="text-gray-800">{r.value}</span>
                    ) : (
                      <span className="text-gray-400 italic">--</span>
                    )}
                  </td>
                  <td className="px-2 py-2 text-gray-400">{r.page || "--"}</td>
                  <td className="px-2 py-2">
                    {r.found && r.page && (
                      <button
                        onClick={() => onViewResult(r.page, r.ref)}
                        className="text-cyan-500 hover:text-cyan-700 text-[11px] font-medium"
                      >
                        View
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {/* Footer */}
      {summary && (
        <div className="px-4 py-2 border-t border-gray-100 text-[11px] text-gray-400 flex justify-between">
          <span>{summary.gemini_calls} API call{summary.gemini_calls !== 1 ? "s" : ""}</span>
          <span>{summary.pages_analyzed.length} page{summary.pages_analyzed.length !== 1 ? "s" : ""}</span>
        </div>
      )}
    </div>
  );
}
