"use client";

import { useState } from "react";
import { DiscoveryParam, searchDocumentText } from "../../services/schemaService";

interface SchemaDiscoveryPanelProps {
  discovery: DiscoveryParam[];
  processId: string;
  onConfirmAndExtract: (confirmed: Array<{ param_name: string; pages: number[] }>) => void;
  onBack: () => void;
  onHighlightPage?: (
    page: number,
    highlights: Array<{ page: number; bbox: { left: number; top: number; width: number; height: number }; text: string; type: string }>
  ) => void;
  loading?: boolean;
}

export default function SchemaDiscoveryPanel({
  discovery,
  processId,
  onConfirmAndExtract,
  onBack,
  onHighlightPage,
  loading = false,
}: SchemaDiscoveryPanelProps) {
  // Track selected pages per parameter
  const [selections, setSelections] = useState<Record<string, number[]>>(() => {
    const init: Record<string, number[]> = {};
    for (const d of discovery) {
      init[d.param_name] = [...d.confirmed_pages];
    }
    return init;
  });

  const togglePage = async (paramName: string, page: number) => {
    const current = selections[paramName] || [];
    const selecting = !current.includes(page);

    setSelections((prev) => ({
      ...prev,
      [paramName]: selecting
        ? [...(prev[paramName] || []), page]
        : (prev[paramName] || []).filter((p) => p !== page),
    }));

    // Show highlights on PDF when selecting
    if (selecting && onHighlightPage && processId) {
      try {
        const results = await searchDocumentText(processId, paramName);
        const pageData = results.pages.find((p) => p.page === page);
        if (pageData) {
          const highlights = pageData.matches.map((m) => ({
            page,
            bbox: { left: m.bbox.left, top: m.bbox.top, width: m.bbox.width, height: m.bbox.height },
            text: m.text,
            type: m.type,
          }));
          onHighlightPage(page, highlights);
        }
      } catch {
        // Still toggle the page, just no highlights
      }
    }
  };

  const confirmedCount = Object.values(selections).filter((pages) => pages.length > 0).length;
  const totalPages = new Set(Object.values(selections).flat()).size;

  const handleExtract = () => {
    const confirmed = Object.entries(selections)
      .filter(([, pages]) => pages.length > 0)
      .map(([param_name, pages]) => ({ param_name, pages }));
    onConfirmAndExtract(confirmed);
  };

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
        <span className="text-xs text-gray-400">Select pages per parameter</span>
      </div>

      {/* Parameter list */}
      <div className="flex-1 overflow-y-auto px-4 py-3 space-y-3">
        {discovery.map((d) => (
          <div key={d.param_name} className="border border-gray-100 rounded-lg p-3">
            <div className="flex items-center justify-between mb-1.5">
              <span className="text-sm font-medium text-gray-700">{d.param_name}</span>
              {d.auto_confirmed && (
                <span className="text-[10px] px-1.5 py-0.5 rounded bg-green-50 text-green-600">
                  {d.source === "hint" ? "From hint" : "Auto"}
                </span>
              )}
              {d.source === "not_found" && (
                <span className="text-[10px] px-1.5 py-0.5 rounded bg-amber-50 text-amber-600">
                  Not found
                </span>
              )}
            </div>

            {d.hint && (
              <div className="text-[11px] text-gray-400 mb-2 truncate">
                {d.hint}
              </div>
            )}

            {d.candidate_pages.length > 0 ? (
              <div className="flex flex-wrap gap-1.5">
                {d.candidate_pages.map((cp) => {
                  const selected = (selections[d.param_name] || []).includes(cp.page);
                  return (
                    <button
                      key={cp.page}
                      onClick={() => togglePage(d.param_name, cp.page)}
                      className={`inline-flex items-center justify-center min-w-[28px] h-7 px-2 rounded text-xs font-medium transition-all ${
                        selected
                          ? "bg-cyan-500 text-white shadow-sm"
                          : "bg-gray-100 text-gray-500 hover:bg-cyan-50 hover:text-cyan-700"
                      }`}
                      title={cp.preview}
                    >
                      {cp.page}
                    </button>
                  );
                })}
              </div>
            ) : (
              <div className="text-xs text-gray-400 italic">
                No pages found. Add a page hint to the parameter.
              </div>
            )}
          </div>
        ))}
      </div>

      {/* Extract button */}
      <div className="px-4 py-3 border-t border-gray-100">
        <button
          onClick={handleExtract}
          disabled={confirmedCount === 0 || loading}
          className={`w-full py-2 rounded-lg text-sm font-medium transition-all ${
            confirmedCount > 0 && !loading
              ? "bg-cyan-500 text-white hover:bg-cyan-600 shadow-sm"
              : "bg-gray-100 text-gray-400 cursor-not-allowed"
          }`}
        >
          {loading
            ? "Extracting..."
            : `Extract ${confirmedCount} parameter${confirmedCount !== 1 ? "s" : ""} from ${totalPages} page${totalPages !== 1 ? "s" : ""}`}
        </button>
      </div>
    </div>
  );
}
