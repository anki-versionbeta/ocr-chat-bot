"use client";
import React, { useState, useEffect } from "react";
import type { ExtractionSchema } from "../../services/schemaService";
import { getSchemaExecutions, type ExecutionListItem } from "../../services/schemaService";

interface SchemaListProps {
  schemas: ExtractionSchema[];
  selectedId?: string;
  onSelect: (schema: ExtractionSchema) => void;
  onEdit: (schema: ExtractionSchema) => void;
  onDelete: (schema: ExtractionSchema) => void;
  onCreate: () => void;
  onViewExecution?: (executionId: string) => void;
  loading?: boolean;
}

export default function SchemaList({ schemas, selectedId, onSelect, onEdit, onDelete, onCreate, onViewExecution, loading }: SchemaListProps) {
  const [executions, setExecutions] = useState<Record<string, ExecutionListItem | null>>({});
  const [allExecs, setAllExecs] = useState<Record<string, ExecutionListItem[]>>({});

  // Load executions for each schema
  useEffect(() => {
    schemas.forEach(async (schema) => {
      try {
        const execs = await getSchemaExecutions(schema.schema_id);
        const latest = execs.find((e) => e.status === "completed") || null;
        setExecutions((prev) => ({ ...prev, [schema.schema_id]: latest }));
        setAllExecs((prev) => ({ ...prev, [schema.schema_id]: execs }));
      } catch {
        // Ignore
      }
    });
  }, [schemas]);

  if (loading) {
    return (
      <div className="flex items-center justify-center h-32">
        <div className="w-6 h-6 border-2 border-cyan-200 border-t-cyan-500 rounded-full animate-spin" />
      </div>
    );
  }

  return (
    <div className="flex flex-col h-full">
      {/* Top bar */}
      <div className="px-4 py-2.5 flex items-center justify-between border-b border-gray-100">
        <span className="text-xs text-gray-400">{schemas.length} schema{schemas.length !== 1 ? "s" : ""}</span>
        <button
          onClick={onCreate}
          className="inline-flex items-center gap-1 px-2.5 py-1.5 text-xs font-medium text-white bg-cyan-500 hover:bg-cyan-600 rounded-md transition-colors"
        >
          <svg className="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={3}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M12 4v16m8-8H4" />
          </svg>
          New
        </button>
      </div>

      <div className="flex-1 overflow-y-auto p-3">
        {schemas.length === 0 ? (
          <div className="text-center py-10">
            <svg className="w-10 h-10 mx-auto mb-3 text-gray-200" viewBox="0 0 24 24" fill="none" stroke="currentColor">
              <rect x="3" y="3" width="18" height="18" rx="2" strokeWidth="1.5"/>
              <path d="M3 9h18M3 15h18M9 3v18M15 3v18" strokeWidth="1" opacity="0.3"/>
            </svg>
            <p className="text-sm text-gray-400 mb-2">No schemas yet</p>
            <button onClick={onCreate} className="text-xs text-cyan-500 hover:text-cyan-600 font-medium">
              Create your first schema
            </button>
          </div>
        ) : (
          <div className="space-y-1.5">
            {schemas.map((schema) => {
              const active = selectedId === schema.schema_id;
              const latestExec = executions[schema.schema_id];
              const allExecutions = (allExecs[schema.schema_id] || []).filter((e) => e.status === "completed");
              return (
                <div
                  key={schema.schema_id}
                  onClick={() => onSelect(schema)}
                  className={`px-3 py-2.5 rounded-lg cursor-pointer group transition-colors ${
                    active ? "bg-cyan-50 border border-cyan-200" : "hover:bg-gray-50 border border-transparent"
                  }`}
                >
                  <div className="flex items-start justify-between">
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-2">
                        <h4 className={`text-sm font-medium truncate ${active ? "text-cyan-700" : "text-gray-700"}`}>
                          {schema.name}
                        </h4>
                        {schema.is_shared && (
                          <span className="px-1.5 py-0.5 text-[10px] bg-blue-50 text-blue-500 rounded">Shared</span>
                        )}
                      </div>
                      <div className="flex items-center gap-2 mt-0.5">
                        <span className="text-[10px] text-gray-400 uppercase">{schema.document_type}</span>
                        <span className="text-[10px] text-gray-300">|</span>
                        <span className="text-[10px] text-gray-400">{schema.parameters?.length || 0} params</span>
                        {latestExec && (
                          <>
                            <span className="text-[10px] text-gray-300">|</span>
                            <button
                              onClick={(e) => {
                                e.stopPropagation();
                                onViewExecution?.(latestExec.execution_id);
                              }}
                              className="text-[10px] text-green-500 hover:text-green-600 font-medium"
                              title="View latest results"
                            >
                              {latestExec.summary?.found || 0}/{latestExec.summary?.total_params || 0} results
                            </button>
                          </>
                        )}
                      </div>
                      {/* Show all executions when schema is selected */}
                      {active && allExecutions.length > 0 && (
                        <div className="mt-1.5 space-y-0.5">
                          {allExecutions.map((exec) => (
                            <button
                              key={exec.execution_id}
                              onClick={(e) => {
                                e.stopPropagation();
                                onViewExecution?.(exec.execution_id);
                              }}
                              className="w-full flex items-center justify-between px-2 py-1 rounded text-[10px] hover:bg-cyan-50 transition-colors"
                            >
                              <span className="text-gray-400">
                                {new Date(exec.started_at).toLocaleDateString()} {new Date(exec.started_at).toLocaleTimeString([], {hour: '2-digit', minute: '2-digit'})}
                              </span>
                              <span className={`font-medium ${exec.status === 'completed' ? 'text-green-500' : 'text-gray-400'}`}>
                                {exec.summary ? `${exec.summary.found}/${exec.summary.total_params}` : exec.status}
                              </span>
                            </button>
                          ))}
                        </div>
                      )}
                      {schema.description && (
                        <p className="text-[11px] text-gray-400 mt-1 truncate">{schema.description}</p>
                      )}
                    </div>
                    <div className="flex gap-0.5 opacity-0 group-hover:opacity-100 transition-opacity ml-2">
                      <button
                        onClick={(e) => { e.stopPropagation(); onEdit(schema); }}
                        className="p-1 text-gray-400 hover:text-cyan-500 rounded"
                        title="Edit"
                      >
                        <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                          <path strokeLinecap="round" strokeLinejoin="round" d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z" />
                        </svg>
                      </button>
                      <button
                        onClick={(e) => { e.stopPropagation(); onDelete(schema); }}
                        className="p-1 text-gray-400 hover:text-red-500 rounded"
                        title="Delete"
                      >
                        <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                          <path strokeLinecap="round" strokeLinejoin="round" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                        </svg>
                      </button>
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}
