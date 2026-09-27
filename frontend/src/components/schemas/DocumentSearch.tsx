"use client";

import { useState, useCallback, useRef, useEffect } from "react";
import {
  searchDocumentText,
  DocumentSearchResult,
  SearchMatch,
} from "../../services/schemaService";

interface DocumentSearchProps {
  processId: string | null;
  onHighlightMatches: (
    page: number,
    highlights: Array<{
      page: number;
      bbox: { left: number; top: number; width: number; height: number };
      text: string;
      type: string;
    }>
  ) => void;
  onExportTable?: (chunkIndex: number) => void;
}

export default function DocumentSearch({
  processId,
  onHighlightMatches,
  onExportTable,
}: DocumentSearchProps) {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<DocumentSearchResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [activePage, setActivePage] = useState<number | null>(null);
  const debounceRef = useRef<NodeJS.Timeout | null>(null);

  const doSearch = useCallback(
    async (searchQuery: string) => {
      if (!processId || searchQuery.trim().length < 1) {
        setResults(null);
        setActivePage(null);
        return;
      }

      setLoading(true);
      setError("");

      try {
        const data = await searchDocumentText(processId, searchQuery.trim());
        setResults(data);
        setActivePage(null);
      } catch {
        setError("Search failed");
        setResults(null);
      } finally {
        setLoading(false);
      }
    },
    [processId]
  );

  const handleInputChange = (value: string) => {
    setQuery(value);

    if (debounceRef.current) {
      clearTimeout(debounceRef.current);
    }

    if (value.trim().length === 0) {
      setResults(null);
      setActivePage(null);
      return;
    }

    debounceRef.current = setTimeout(() => {
      doSearch(value);
    }, 400);
  };

  useEffect(() => {
    return () => {
      if (debounceRef.current) clearTimeout(debounceRef.current);
    };
  }, []);

  const handleViewPage = (page: number, matches: SearchMatch[]) => {
    setActivePage(page);

    const highlights = matches.map((m) => ({
      page,
      bbox: {
        left: m.bbox.left,
        top: m.bbox.top,
        width: m.bbox.width,
        height: m.bbox.height,
      },
      text: m.text,
      type: m.type,
    }));

    onHighlightMatches(page, highlights);
  };

  const handleClear = () => {
    setQuery("");
    setResults(null);
    setActivePage(null);
    setError("");
  };

  if (!processId) {
    return (
      <div className="px-3 py-2">
        <div className="relative">
          <input
            type="text"
            placeholder="Upload a document to search..."
            disabled
            className="w-full pl-8 pr-3 py-1.5 text-sm border border-gray-200 rounded-lg bg-gray-50 text-gray-400 cursor-not-allowed"
          />
          <svg
            className="absolute left-2.5 top-2 w-4 h-4 text-gray-300"
            fill="none"
            viewBox="0 0 24 24"
            stroke="currentColor"
            strokeWidth={2}
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z"
            />
          </svg>
        </div>
      </div>
    );
  }

  return (
    <div className="px-3 py-2">
      {/* Search Input */}
      <div className="relative">
        <input
          type="text"
          value={query}
          onChange={(e) => handleInputChange(e.target.value)}
          placeholder="Search document text..."
          className="w-full pl-8 pr-8 py-1.5 text-sm border border-gray-200 rounded-lg bg-white focus:outline-none focus:ring-2 focus:ring-cyan-400 focus:border-transparent transition-all"
        />
        <svg
          className="absolute left-2.5 top-2 w-4 h-4 text-gray-400"
          fill="none"
          viewBox="0 0 24 24"
          stroke="currentColor"
          strokeWidth={2}
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z"
          />
        </svg>
        {query && (
          <button
            onClick={handleClear}
            className="absolute right-2.5 top-2 text-gray-400 hover:text-gray-600"
          >
            <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        )}
      </div>

      {/* Loading */}
      {loading && (
        <div className="mt-2 flex items-center text-xs text-gray-500">
          <svg className="animate-spin w-3 h-3 mr-1.5 text-cyan-500" fill="none" viewBox="0 0 24 24">
            <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
            <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
          </svg>
          Searching...
        </div>
      )}

      {/* Error */}
      {error && <div className="mt-2 text-xs text-red-500">{error}</div>}

      {/* Results */}
      {results && !loading && (
        <div className="mt-2">
          {results.total_matches > 0 ? (
            <div className="max-h-52 overflow-y-auto space-y-1">
              {results.pages.map((pageResult) => {
                // Check if any match in this page is a table cell with chunk_index
                const tableMatch = pageResult.matches.find(
                  (m) => m.type === "cell" && m.chunk_index != null
                );

                return (
                  <div
                    key={pageResult.page}
                    className={`flex items-center gap-1 px-2 py-1.5 rounded text-xs transition-all ${
                      activePage === pageResult.page
                        ? "bg-cyan-50 text-cyan-800"
                        : "hover:bg-gray-50 text-gray-600"
                    }`}
                  >
                    <button
                      onClick={() => handleViewPage(pageResult.page, pageResult.matches)}
                      className="flex items-center gap-2 flex-1 min-w-0 text-left"
                    >
                      <span
                        className={`inline-flex items-center justify-center w-6 h-6 rounded text-xs font-medium flex-shrink-0 ${
                          activePage === pageResult.page
                            ? "bg-cyan-500 text-white"
                            : "bg-gray-100 text-gray-500"
                        }`}
                      >
                        {pageResult.page}
                      </span>
                      <span className="truncate text-gray-400">
                        {pageResult.preview}
                      </span>
                    </button>

                    {/* Export icon for table matches */}
                    {tableMatch && onExportTable && (
                      <button
                        onClick={(e) => {
                          e.stopPropagation();
                          onExportTable(tableMatch.chunk_index!);
                        }}
                        className="flex-shrink-0 p-1 rounded hover:bg-cyan-100 text-cyan-500 hover:text-cyan-700 transition-colors"
                        title="Export this table"
                      >
                        <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 10v6m0 0l-3-3m3 3l3-3m2 8H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                        </svg>
                      </button>
                    )}
                  </div>
                );
              })}
            </div>
          ) : (
            <div className="text-xs text-gray-400">
              No results for &ldquo;{results.query}&rdquo;
            </div>
          )}
        </div>
      )}
    </div>
  );
}
