"use client";
import { useState, useEffect, useCallback, useRef } from "react";
import React from "react";
import SchemaList from "./SchemaList";
import SchemaEditor from "./SchemaEditor";
import {
  getSchemas,
  createSchema,
  updateSchema,
  deleteSchema,
  type ExtractionSchema,
  type ParameterDefinition,
} from "../../services/schemaService";

interface SchemaPanelProps {
  onClose: () => void;
  onSchemaSelect?: (schema: ExtractionSchema) => void;
  selectedSchemaId?: string;
}

type PanelView = "list" | "create" | "edit";

export default function SchemaPanel({ onClose, onSchemaSelect, selectedSchemaId }: SchemaPanelProps) {
  const [schemas, setSchemas] = useState<ExtractionSchema[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [view, setView] = useState<PanelView>("list");
  const [editingSchema, setEditingSchema] = useState<ExtractionSchema | null>(null);
  const [selectedId, setSelectedId] = useState<string | undefined>(selectedSchemaId);
  const panelRef = useRef<HTMLDivElement>(null);

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

  // Close on outside click
  useEffect(() => {
    const handleClick = (e: MouseEvent) => {
      if (panelRef.current && !panelRef.current.contains(e.target as Node)) {
        onClose();
      }
    };
    document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, [onClose]);

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

  return (
    <>
      {/* Backdrop */}
      <div className="fixed inset-0 bg-black/10 z-29" />

      {/* Panel */}
      <div
        ref={panelRef}
        className="fixed right-0 top-0 h-screen w-[460px] bg-white z-30 flex flex-col border-l border-gray-200 shadow-lg"
      >
        {/* Header */}
        <div className="flex items-center justify-between px-4 py-3 border-b border-gray-200">
          <h2 className="text-sm font-semibold text-gray-700">Schemas</h2>
          <div className="flex items-center gap-2">
            <button className="px-3 py-1.5 text-xs font-medium text-white bg-cyan-500 hover:bg-cyan-600 rounded-md transition-colors">
              Run Schema
            </button>
            <button onClick={onClose} className="p-1.5 text-gray-400 hover:text-gray-600 rounded-md hover:bg-gray-100">
              <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          </div>
        </div>

        {/* Content */}
        <div className="flex-1 overflow-hidden">
          {view === "list" && (
            <SchemaList
              schemas={schemas} selectedId={selectedId}
              onSelect={(s) => { setSelectedId(s.schema_id); onSchemaSelect?.(s); }}
              onEdit={(s) => { setEditingSchema(s); setView("edit"); }}
              onDelete={handleDelete}
              onCreate={() => { setEditingSchema(null); setView("create"); }}
              loading={loading}
            />
          )}
          {view === "create" && (
            <SchemaEditor onSave={handleCreate} onCancel={() => setView("list")} saving={saving} />
          )}
          {view === "edit" && editingSchema && (
            <SchemaEditor schema={editingSchema} onSave={handleUpdate} onCancel={() => { setView("list"); setEditingSchema(null); }} saving={saving} />
          )}
        </div>
      </div>
    </>
  );
}
