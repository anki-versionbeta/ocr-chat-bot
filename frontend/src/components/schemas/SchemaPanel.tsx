"use client";
import { useState, useEffect, useCallback, useRef } from "react";
import React from "react";
import SchemaList from "./SchemaList";
import SchemaEditor from "./SchemaEditor";
import DocumentSearch from "./DocumentSearch";
import SchemaDiscoveryPanel from "./SchemaDiscoveryPanel";
import SchemaExecutionProgress from "./SchemaExecutionProgress";
import SchemaResultsPanel from "./SchemaResultsPanel";
import {
  getSchemas,
  createSchema,
  updateSchema,
  deleteSchema,
  discoverPages,
  runExtraction,
  getExecutionResult,
  type ExtractionSchema,
  type ParameterDefinition,
  type DiscoveryParam,
  type ParamResult,
  type ExecutionSummary,
} from "../../services/schemaService";

function PdfIcon({ className }: { className?: string }) {
  return (
    <svg className={className || "w-3.5 h-3.5 text-red-400"} fill="currentColor" viewBox="0 0 24 24">
      <path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8l-6-6zM14 3.5L18.5 8H14V3.5zM6 20V4h7v5h5v11H6z"/>
    </svg>
  );
}

function DocSwitcherBar({ documentName, processId, chatDocuments, onSwitchDocument }: {
  documentName?: string;
  processId?: string | null;
  chatDocuments?: DocInfo[];
  onSwitchDocument?: (processId: string, documentName: string) => void;
}) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  const hasMultiple = (chatDocuments?.length || 0) > 1;

  useEffect(() => {
    if (!open) return;
    const handleClick = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, [open]);

  return (
    <div ref={ref} className="px-4 py-1.5 bg-gray-50 border-b border-gray-100 relative">
      <button
        onClick={() => hasMultiple && setOpen(!open)}
        className={`inline-flex items-center gap-2 w-full ${hasMultiple ? "cursor-pointer hover:text-cyan-700" : "cursor-default"}`}
      >
        <PdfIcon />
        {documentName ? (
          <span className="text-xs text-gray-600 truncate">{documentName}</span>
        ) : (
          <span className="text-xs text-gray-400 italic">No document loaded</span>
        )}
        {hasMultiple && (
          <svg className={`w-3 h-3 text-gray-400 ml-auto transition-transform ${open ? "rotate-180" : ""}`} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M19 9l-7 7-7-7" />
          </svg>
        )}
      </button>
      {open && hasMultiple && chatDocuments && (
        <div className="absolute left-2 right-2 top-full mt-0.5 bg-white rounded-lg shadow-lg border border-gray-200 py-1 z-50">
          {chatDocuments.map((doc) => {
            const isActive = doc.process_id === processId;
            return (
              <button
                key={doc.document_id}
                onClick={() => {
                  if (!isActive && onSwitchDocument) {
                    onSwitchDocument(doc.process_id, doc.document_name);
                  }
                  setOpen(false);
                }}
                className={`w-full flex items-center gap-2 px-3 py-2 text-xs text-left transition-colors ${
                  isActive ? "bg-cyan-50 text-cyan-700" : "hover:bg-gray-50 text-gray-600"
                }`}
              >
                <span className={`w-2 h-2 rounded-full flex-shrink-0 ${isActive ? "bg-cyan-500" : "bg-gray-300"}`} />
                <PdfIcon />
                <span className="truncate">{doc.document_name}</span>
                {isActive && <span className="ml-auto text-[10px] text-cyan-500 font-medium">active</span>}
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
}

interface DocInfo {
  document_id: string;
  document_name: string;
  process_id: string;
}

interface SchemaPanelProps {
  onClose: () => void;
  onSchemaSelect?: (schema: ExtractionSchema) => void;
  selectedSchemaId?: string;
  processId?: string | null;
  documentName?: string;
  chatDocuments?: DocInfo[];
  onSwitchDocument?: (processId: string, documentName: string) => void;
  onHighlightMatches?: (
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

type PanelView = "list" | "create" | "edit" | "discovery" | "extracting" | "results";

export default function SchemaPanel({ onClose, onSchemaSelect, selectedSchemaId, processId, documentName, chatDocuments, onSwitchDocument, onHighlightMatches, onExportTable }: SchemaPanelProps) {
  const [schemas, setSchemas] = useState<ExtractionSchema[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [view, setView] = useState<PanelView>("list");
  const [editingSchema, setEditingSchema] = useState<ExtractionSchema | null>(null);
  const [selectedId, setSelectedId] = useState<string | undefined>(selectedSchemaId);
  const panelRef = useRef<HTMLDivElement>(null);

  // Execution state
  const [executionId, setExecutionId] = useState<string | null>(null);
  const [discovery, setDiscovery] = useState<DiscoveryParam[]>([]);
  const [extractionEvents, setExtractionEvents] = useState<Array<{ type: string; data: Record<string, unknown> }>>([]);
  const [extractionResults, setExtractionResults] = useState<ParamResult[]>([]);
  const [extractionSummary, setExtractionSummary] = useState<ExecutionSummary | null>(null);
  const [isExtractionComplete, setIsExtractionComplete] = useState(false);
  const [discovering, setDiscovering] = useState(false);

  const loadSchemas = useCallback(async () => {
    try {
      setLoading(true);
      const data = await getSchemas();
      setSchemas(data);
    } catch (err) {
      console.error("Failed to load schemas:", err);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { loadSchemas(); }, [loadSchemas]);

  // Close on outside click — but ignore clicks on PDF panel
  useEffect(() => {
    const handleClick = (e: MouseEvent) => {
      if (panelRef.current && !panelRef.current.contains(e.target as Node)) {
        const target = e.target as HTMLElement;
        const clickedInPdfPanel = target.closest('[data-pdf-panel]') !== null;
        if (clickedInPdfPanel) return;
        onClose();
      }
    };
    document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, [onClose]);

  // Schema CRUD handlers
  const handleCreate = async (data: {
    name: string; description: string; document_type: string;
    parameters: ParameterDefinition[]; is_shared: boolean;
  }) => {
    try {
      setSaving(true);
      await createSchema(data.name, data.parameters, data.description, data.document_type, data.is_shared);
      await loadSchemas();
      setView("list");
    } catch (err) { console.error("Failed to create schema:", err); }
    finally { setSaving(false); }
  };

  const handleUpdate = async (data: {
    name: string; description: string; document_type: string;
    parameters: ParameterDefinition[]; is_shared: boolean;
  }) => {
    if (!editingSchema) return;
    try {
      setSaving(true);
      await updateSchema(editingSchema.schema_id, data);
      await loadSchemas();
      setView("list");
      setEditingSchema(null);
    } catch (err) { console.error("Failed to update schema:", err); }
    finally { setSaving(false); }
  };

  const handleDelete = async (schema: ExtractionSchema) => {
    if (!confirm(`Delete "${schema.name}"?`)) return;
    try {
      await deleteSchema(schema.schema_id);
      await loadSchemas();
      if (selectedId === schema.schema_id) setSelectedId(undefined);
    } catch (err) { console.error("Failed to delete schema:", err); }
  };

  // =========================================================================
  // SCHEMA EXECUTION — Run Schema button → Discovery → Extract → Results
  // =========================================================================

  const handleRunSchema = async () => {
    if (!selectedId || !processId) return;

    setDiscovering(true);
    try {
      const result = await discoverPages(selectedId, processId);
      setExecutionId(result.execution_id);
      setDiscovery(result.discovery);
      setView("discovery");
    } catch (err) {
      console.error("Discovery failed:", err);
    } finally {
      setDiscovering(false);
    }
  };

  const handleConfirmAndExtract = async (confirmed: Array<{ param_name: string; pages: number[] }>) => {
    if (!executionId || !processId) return;

    // Build confirmed params with param definitions
    const selectedSchema = schemas.find((s) => s.schema_id === selectedId);
    const confirmedParams = confirmed.map((c) => {
      const paramDef = selectedSchema?.parameters.find((p) => p.name === c.param_name);
      return {
        param_name: c.param_name,
        pages: c.pages,
        param_def: paramDef || {},
      };
    });

    setExtractionEvents([]);
    setExtractionResults([]);
    setExtractionSummary(null);
    setIsExtractionComplete(false);
    setView("extracting");

    try {
      const response = await runExtraction(executionId, processId, confirmedParams);

      if (!response.ok) {
        console.error("Extraction request failed");
        return;
      }

      // Read SSE stream
      const reader = response.body?.getReader();
      if (!reader) return;

      const decoder = new TextDecoder();
      let buffer = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop() || "";

        for (const line of lines) {
          if (line.startsWith("data: ")) {
            try {
              const event = JSON.parse(line.slice(6));
              if (event.type === "heartbeat") continue;

              setExtractionEvents((prev) => [...prev, event]);

              if (event.type === "complete") {
                setExtractionResults(event.data.results || []);
                setExtractionSummary(event.data.summary || null);
                setIsExtractionComplete(true);
                // Auto-switch to results after brief delay
                setTimeout(() => setView("results"), 1000);
              }

              if (event.type === "error") {
                setIsExtractionComplete(true);
              }
            } catch {
              // Skip malformed events
            }
          }
        }
      }
    } catch (err) {
      console.error("Extraction stream error:", err);
      setIsExtractionComplete(true);
    }
  };

  const handleViewPastExecution = async (execId: string) => {
    try {
      const exec = await getExecutionResult(execId);
      setExecutionId(execId);
      setExtractionResults(exec.results || []);
      setExtractionSummary(exec.summary || null);
      setView("results");
    } catch (err) {
      console.error("Failed to load execution:", err);
    }
  };

  const handleViewResult = (page: number, ref: string | null) => {
    if (!onHighlightMatches) return;

    // Find the result with bbox(es)
    const result = extractionResults.find(
      (r) => r.page === page && (r.ref === ref || (r.refs && ref && r.refs.includes(ref)))
    );

    if (result?.bboxes?.length) {
      // Multiple bboxes for verification results
      onHighlightMatches(page, result.bboxes.map(bbox => ({
        page,
        bbox,
        text: result.finding || result.value || "",
        type: "cell",
      })));
    } else if (result?.bbox) {
      onHighlightMatches(page, [{
        page,
        bbox: result.bbox,
        text: result.value || result.finding || "",
        type: "cell",
      }]);
    } else {
      // Navigate to page without highlights
      onHighlightMatches(page, []);
    }
  };

  // =========================================================================
  // RENDER
  // =========================================================================

  const canRun = selectedId && processId && view === "list";

  return (
    <>
      {/* Backdrop */}
      <div className="fixed inset-0 bg-black/10 z-29" />

      {/* Panel */}
      <div
        ref={panelRef}
        className="fixed right-0 top-0 h-screen w-[700px] bg-white z-30 flex flex-col border-l border-gray-200 shadow-lg"
      >
        {/* Header */}
        <div className="flex items-center justify-between px-4 py-3 border-b border-gray-200">
          <h2 className="text-sm font-semibold text-gray-700">
            {view === "discovery" ? "Select Pages" :
             view === "extracting" ? "Extracting" :
             view === "results" ? "Results" : "Extract"}
          </h2>
          <div className="flex items-center gap-2">
            {canRun && (
              <button
                onClick={handleRunSchema}
                disabled={discovering}
                className={`px-3 py-1.5 text-xs font-medium rounded-md transition-colors ${
                  discovering
                    ? "bg-gray-100 text-gray-400 cursor-not-allowed"
                    : "text-white bg-cyan-500 hover:bg-cyan-600"
                }`}
              >
                {discovering ? "Discovering..." : "Run Schema"}
              </button>
            )}
            <button onClick={onClose} className="p-1.5 text-gray-400 hover:text-gray-600 rounded-md hover:bg-gray-100">
              <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          </div>
        </div>

        {/* Active Document Indicator + Switcher */}
        <DocSwitcherBar
          documentName={documentName}
          processId={processId}
          chatDocuments={chatDocuments}
          onSwitchDocument={onSwitchDocument}
        />

        {/* Document Search — only show in list/create/edit views */}
        {(view === "list" || view === "create" || view === "edit") && (
          <div className="border-b border-gray-100">
            <DocumentSearch
              processId={processId || null}
              onHighlightMatches={onHighlightMatches || (() => {})}
              onExportTable={onExportTable}
            />
          </div>
        )}

        {/* Content */}
        <div className="flex-1 overflow-hidden">
          {view === "list" && (
            <SchemaList
              schemas={schemas} selectedId={selectedId}
              onSelect={(s) => { setSelectedId(s.schema_id); onSchemaSelect?.(s); }}
              onEdit={(s) => { setEditingSchema(s); setView("edit"); }}
              onDelete={handleDelete}
              onCreate={() => { setEditingSchema(null); setView("create"); }}
              onViewExecution={handleViewPastExecution}
              loading={loading}
            />
          )}
          {view === "create" && (
            <SchemaEditor onSave={handleCreate} onCancel={() => setView("list")} saving={saving} processId={processId} onHighlightMatches={onHighlightMatches} />
          )}
          {view === "edit" && editingSchema && (
            <SchemaEditor schema={editingSchema} onSave={handleUpdate} onCancel={() => { setView("list"); setEditingSchema(null); }} saving={saving} processId={processId} onHighlightMatches={onHighlightMatches} />
          )}
          {view === "discovery" && (
            <SchemaDiscoveryPanel
              discovery={discovery}
              processId={processId || ""}
              onConfirmAndExtract={handleConfirmAndExtract}
              onBack={() => setView("list")}
              onHighlightPage={onHighlightMatches}
            />
          )}
          {view === "extracting" && (
            <SchemaExecutionProgress
              events={extractionEvents}
              isComplete={isExtractionComplete}
            />
          )}
          {view === "results" && (
            <SchemaResultsPanel
              results={extractionResults}
              summary={extractionSummary}
              executionId={executionId}
              onViewResult={handleViewResult}
              onBack={() => setView("list")}
            />
          )}
        </div>
      </div>
    </>
  );
}
