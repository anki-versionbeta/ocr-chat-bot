"use client";
import { useState } from "react";
import React from "react";
import type { ParameterDefinition, ExtractionSchema } from "../../services/schemaService";

interface SchemaEditorProps {
  schema?: ExtractionSchema | null;
  onSave: (data: {
    name: string; description: string; document_type: string;
    parameters: ParameterDefinition[]; is_shared: boolean;
  }) => void;
  onCancel: () => void;
  saving?: boolean;
}

const PARAM_TYPES: { value: ParameterDefinition["type"]; label: string }[] = [
  { value: "string", label: "Text" },
  { value: "number", label: "Number" },
  { value: "date", label: "Date" },
  { value: "boolean", label: "Yes/No" },
];

const DOC_TYPES = ["general", "coa", "hbr", "batch_record", "specification"];

export default function SchemaEditor({ schema, onSave, onCancel, saving }: SchemaEditorProps) {
  const [name, setName] = useState(schema?.name || "");
  const [description, setDescription] = useState(schema?.description || "");
  const [documentType, setDocumentType] = useState(schema?.document_type || "general");
  const [isShared, setIsShared] = useState(schema?.is_shared || false);
  const [parameters, setParameters] = useState<ParameterDefinition[]>(
    schema?.parameters?.length ? schema.parameters : [{ name: "", type: "string", required: true, hint: "" }]
  );

  const addParameter = () => {
    setParameters([...parameters, { name: "", type: "string", required: true, hint: "" }]);
  };

  const removeParameter = (index: number) => {
    if (parameters.length > 1) setParameters(parameters.filter((_, i) => i !== index));
  };

  const updateParameter = (index: number, field: keyof ParameterDefinition, value: any) => {
    const updated = [...parameters];
    updated[index] = { ...updated[index], [field]: value };
    setParameters(updated);
  };

  const handleSubmit = () => {
    const validParams = parameters.filter((p) => p.name.trim());
    if (!name.trim() || validParams.length === 0) return;
    onSave({ name: name.trim(), description: description.trim(), document_type: documentType, parameters: validParams, is_shared: isShared });
  };

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="px-4 py-2.5 border-b border-gray-200 flex items-center gap-2">
        <button onClick={onCancel} className="p-1 text-gray-400 hover:text-gray-600 rounded hover:bg-gray-100">
          <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M15 19l-7-7 7-7" />
          </svg>
        </button>
        <h3 className="text-sm font-semibold text-gray-700">{schema ? "Edit Schema" : "New Schema"}</h3>
      </div>

      {/* Form */}
      <div className="flex-1 overflow-y-auto px-4 py-4 space-y-4">
        {/* Name */}
        <div>
          <label className="block text-xs font-medium text-gray-500 mb-1">Name</label>
          <input
            type="text" value={name} onChange={(e) => setName(e.target.value)}
            placeholder="e.g., COA Particle Size Analysis"
            className="w-full px-3 py-2 text-sm border border-gray-200 rounded-md focus:ring-2 focus:ring-cyan-400/30 focus:border-cyan-400 outline-none"
            autoFocus
          />
        </div>

        {/* Description */}
        <div>
          <label className="block text-xs font-medium text-gray-500 mb-1">Description</label>
          <textarea
            value={description} onChange={(e) => setDescription(e.target.value)}
            placeholder="What this schema extracts..."
            rows={2}
            className="w-full px-3 py-2 text-sm border border-gray-200 rounded-md focus:ring-2 focus:ring-cyan-400/30 focus:border-cyan-400 outline-none resize-none"
          />
        </div>

        {/* Document Type + Shared */}
        <div className="flex gap-3">
          <div className="flex-1">
            <label className="block text-xs font-medium text-gray-500 mb-1">Document Type</label>
            <select
              value={documentType} onChange={(e) => setDocumentType(e.target.value)}
              className="w-full px-3 py-2 text-sm border border-gray-200 rounded-md focus:ring-2 focus:ring-cyan-400/30 outline-none bg-white"
            >
              {DOC_TYPES.map((dt) => (
                <option key={dt} value={dt}>{dt.toUpperCase()}</option>
              ))}
            </select>
          </div>
          <div className="flex items-end pb-1">
            <label className="flex items-center gap-2 text-xs text-gray-500 cursor-pointer">
              <input type="checkbox" checked={isShared} onChange={(e) => setIsShared(e.target.checked)}
                className="w-3.5 h-3.5 rounded border-gray-300 text-cyan-500" />
              Share with team
            </label>
          </div>
        </div>

        {/* Separator */}
        <div className="border-t border-gray-100" />

        {/* Parameters */}
        <div>
          <div className="flex items-center justify-between mb-2">
            <label className="text-xs font-medium text-gray-500">
              Parameters <span className="text-gray-300">({parameters.filter(p => p.name.trim()).length})</span>
            </label>
            <button onClick={addParameter}
              className="text-xs text-cyan-500 hover:text-cyan-600 font-medium flex items-center gap-1"
            >
              <svg className="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M12 4v16m8-8H4" />
              </svg>
              Add
            </button>
          </div>

          <div className="space-y-2">
            {parameters.map((param, index) => (
              <div key={index} className="border border-gray-200 rounded-lg p-3 bg-white hover:border-gray-300 transition-colors">
                {/* Row 1: Name + Type + Delete */}
                <div className="flex items-center gap-2 mb-2">
                  <span className="text-[10px] text-gray-300 font-mono w-4 text-center flex-shrink-0">{index + 1}</span>
                  <input
                    type="text" value={param.name}
                    onChange={(e) => updateParameter(index, "name", e.target.value)}
                    placeholder="Parameter name"
                    className="flex-1 min-w-0 px-2.5 py-1.5 text-sm border border-gray-200 rounded focus:ring-1 focus:ring-cyan-400 outline-none"
                  />
                  <select
                    value={param.type}
                    onChange={(e) => updateParameter(index, "type", e.target.value)}
                    className="w-[85px] px-2 py-1.5 text-xs border border-gray-200 rounded focus:ring-1 focus:ring-cyan-400 outline-none bg-white flex-shrink-0"
                  >
                    {PARAM_TYPES.map((t) => (
                      <option key={t.value} value={t.value}>{t.label}</option>
                    ))}
                  </select>
                  <button
                    onClick={() => removeParameter(index)}
                    disabled={parameters.length <= 1}
                    className={`p-1 rounded flex-shrink-0 ${parameters.length <= 1 ? "text-gray-200" : "text-gray-300 hover:text-red-500"}`}
                  >
                    <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                      <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
                    </svg>
                  </button>
                </div>

                {/* Row 2: Comment */}
                <div className="pl-6">
                  <input
                    type="text" value={param.hint || ""}
                    onChange={(e) => updateParameter(index, "hint", e.target.value)}
                    placeholder="Comment for AI (e.g., 'Look in Results column, page 1')"
                    className="w-full px-2 py-1 text-[11px] text-gray-400 border-b border-gray-100 focus:border-cyan-300 outline-none bg-transparent placeholder:text-gray-300"
                  />
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Footer */}
      <div className="px-4 py-3 border-t border-gray-200 flex gap-2">
        <button onClick={onCancel}
          className="flex-1 px-3 py-2 text-sm text-gray-500 border border-gray-200 rounded-md hover:bg-gray-50 transition-colors"
        >
          Cancel
        </button>
        <button onClick={handleSubmit}
          disabled={!name.trim() || parameters.every((p) => !p.name.trim()) || saving}
          className="flex-1 px-3 py-2 text-sm font-medium text-white bg-cyan-500 rounded-md hover:bg-cyan-600 transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
        >
          {saving ? "Saving..." : schema ? "Update" : "Create"}
        </button>
      </div>
    </div>
  );
}
