"use client";
import { useState, useCallback, useRef, useEffect } from "react";
import React from "react";
import type { ParameterDefinition, ExtractionSchema, VerificationConfig } from "../../services/schemaService";
import { searchDocumentText, DocumentSearchResult } from "../../services/schemaService";

interface SchemaEditorProps {
  schema?: ExtractionSchema | null;
  onSave: (data: {
    name: string; description: string; document_type: string;
    parameters: ParameterDefinition[]; is_shared: boolean;
  }) => void;
  onCancel: () => void;
  saving?: boolean;
  processId?: string | null;
  onHighlightMatches?: (
    page: number,
    highlights: Array<{
      page: number;
      bbox: { left: number; top: number; width: number; height: number };
      text: string;
      type: string;
    }>
  ) => void;
}

const PARAM_TYPES: { value: ParameterDefinition["type"]; label: string }[] = [
  { value: "string", label: "Text" },
  { value: "number", label: "Number" },
  { value: "date", label: "Date" },
  { value: "boolean", label: "Yes/No" },
];

const DOC_TYPES = ["general", "coa", "hbr", "batch_record", "specification"];

const VERIFICATION_CHECK_TYPES: { value: string; label: string }[] = [
  { value: "elapsed_time", label: "Elapsed Time" },
  { value: "witness_verification", label: "Witness Check" },
  { value: "significant_figures", label: "Sig Figures" },
  { value: "correction_check", label: "Correction Audit" },
  { value: "calculation_check", label: "Calculation" },
  { value: "date_sequence", label: "Date Sequence" },
  { value: "custom", label: "Custom" },
];

// Default instruction hints shown when a check type is selected
const CHECK_TYPE_HINTS: Record<string, string> = {
  elapsed_time: "Auto: Finds time calculations on the page, verifies arithmetic visually, reports performer + witness.",
  witness_verification: "Auto: Finds corrections/strikethroughs, checks for witness initials + date nearby.",
  significant_figures: "Auto: Checks recorded values match specification sig fig requirements.",
  correction_check: "Auto: Finds ALL corrections (old→new), reports performer + witness for each.",
  calculation_check: "Auto: Verifies all math on the page, reports expected vs actual.",
  date_sequence: "Auto: Checks all dates on the page are in chronological order.",
  custom: "",
};

export default function SchemaEditor({ schema, onSave, onCancel, saving, processId, onHighlightMatches }: SchemaEditorProps) {
  const [name, setName] = useState(schema?.name || "");
  const [description, setDescription] = useState(schema?.description || "");
  const [documentType, setDocumentType] = useState(schema?.document_type || "general");
  const [isShared, setIsShared] = useState(schema?.is_shared || false);
  const [parameters, setParameters] = useState<ParameterDefinition[]>(
    schema?.parameters?.length ? schema.parameters : [{ name: "", type: "string", required: true, hint: "", page: null, task_type: "extract" }]
  );

  // Live page preview state per parameter index
  const [pagePreview, setPagePreview] = useState<Record<number, DocumentSearchResult | null>>({});
  const [previewLoading, setPreviewLoading] = useState<Record<number, boolean>>({});
  const debounceRefs = useRef<Record<number, NodeJS.Timeout>>({});

  const addExtractParameter = () => {
    setParameters([...parameters, { name: "", type: "string", required: true, hint: "", page: null, task_type: "extract" }]);
  };

  const addVerifyParameter = () => {
    setParameters([...parameters, {
      name: "", type: "string", required: true, hint: "", page: null,
      task_type: "verify",
      verification_config: { check_type: "custom", instruction: "" }
    }]);
  };

  const removeParameter = (index: number) => {
    if (parameters.length > 1) setParameters(parameters.filter((_, i) => i !== index));
  };

  const updateParameter = (index: number, field: keyof ParameterDefinition, value: any) => {
    const updated = [...parameters];
    updated[index] = { ...updated[index], [field]: value };
    setParameters(updated);
  };

  const updateVerificationConfig = (index: number, field: keyof VerificationConfig, value: string) => {
    const updated = [...parameters];
    const existing = updated[index].verification_config || { check_type: "custom" };
    updated[index] = { ...updated[index], verification_config: { ...existing, [field]: value } };
    setParameters(updated);
  };

  const toggleTaskType = (index: number, newType: "extract" | "verify") => {
    const updated = [...parameters];
    updated[index] = {
      ...updated[index],
      task_type: newType,
      ...(newType === "verify" && !updated[index].verification_config
        ? { verification_config: { check_type: "custom", instruction: "" } }
        : {}),
    };
    setParameters(updated);
  };

  // Live page preview: search document for parameter name
  const searchForParam = useCallback(async (index: number, paramName: string) => {
    if (!processId || paramName.trim().length < 2) {
      setPagePreview(prev => ({ ...prev, [index]: null }));
      return;
    }
    setPreviewLoading(prev => ({ ...prev, [index]: true }));
    try {
      const data = await searchDocumentText(processId, paramName.trim(), 50);
      setPagePreview(prev => ({ ...prev, [index]: data }));
    } catch {
      setPagePreview(prev => ({ ...prev, [index]: null }));
    } finally {
      setPreviewLoading(prev => ({ ...prev, [index]: false }));
    }
  }, [processId]);

  // Click a page badge → set page field + show highlights on PDF
  const handlePageBadgeClick = (index: number, pageNum: number) => {
    updateParameter(index, "page", pageNum);

    // Show highlights on PDF panel
    if (!onHighlightMatches || !pagePreview[index]) return;
    const pageResult = pagePreview[index]!.pages.find(p => p.page === pageNum);
    if (!pageResult) {
      onHighlightMatches(pageNum, []);
      return;
    }
    const highlights = pageResult.matches.map(m => ({
      page: pageNum,
      bbox: {
        left: m.bbox.left,
        top: m.bbox.top,
        width: m.bbox.width,
        height: m.bbox.height,
      },
      text: m.text,
      type: m.type,
    }));
    onHighlightMatches(pageNum, highlights);
  };

  const handleParamNameChange = (index: number, value: string) => {
    updateParameter(index, "name", value);
    // Debounced search
    if (debounceRefs.current[index]) clearTimeout(debounceRefs.current[index]);
    debounceRefs.current[index] = setTimeout(() => searchForParam(index, value), 600);
  };

  // Cleanup debounce timers
  useEffect(() => {
    return () => {
      Object.values(debounceRefs.current).forEach(clearTimeout);
    };
  }, []);

  const handleSubmit = () => {
    const validParams = parameters.filter((p) => p.name.trim());
    if (!name.trim() || validParams.length === 0) return;
    onSave({ name: name.trim(), description: description.trim(), document_type: documentType, parameters: validParams, is_shared: isShared });
  };

  const isVerify = (param: ParameterDefinition) => param.task_type === "verify";

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
            placeholder="What this schema extracts and verifies..."
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
            <div className="flex items-center gap-2">
              <button onClick={addExtractParameter}
                className="text-xs text-cyan-500 hover:text-cyan-600 font-medium flex items-center gap-1"
              >
                <svg className="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M12 4v16m8-8H4" />
                </svg>
                Extract
              </button>
              <span className="text-gray-200">|</span>
              <button onClick={addVerifyParameter}
                className="text-xs text-purple-500 hover:text-purple-600 font-medium flex items-center gap-1"
              >
                <svg className="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M12 4v16m8-8H4" />
                </svg>
                Verify
              </button>
            </div>
          </div>

          <div className="space-y-2">
            {parameters.map((param, index) => (
              <div key={index} className={`border rounded-lg p-3 bg-white hover:border-gray-300 transition-colors ${
                isVerify(param) ? "border-purple-200" : "border-gray-200"
              }`}>
                {/* Row 0: Task Type Toggle */}
                <div className="flex items-center gap-1 mb-2">
                  <button
                    onClick={() => toggleTaskType(index, "extract")}
                    className={`px-2 py-0.5 text-[10px] font-medium rounded-l border transition-colors ${
                      !isVerify(param)
                        ? "bg-cyan-50 text-cyan-700 border-cyan-200"
                        : "bg-white text-gray-400 border-gray-200 hover:bg-gray-50"
                    }`}
                  >
                    Extract
                  </button>
                  <button
                    onClick={() => toggleTaskType(index, "verify")}
                    className={`px-2 py-0.5 text-[10px] font-medium rounded-r border-y border-r transition-colors ${
                      isVerify(param)
                        ? "bg-purple-50 text-purple-700 border-purple-200"
                        : "bg-white text-gray-400 border-gray-200 hover:bg-gray-50"
                    }`}
                  >
                    Verify
                  </button>
                </div>

                {/* Row 1: Name + Type/CheckType + Page + Delete */}
                <div className="flex items-center gap-2 mb-2">
                  <span className="text-[10px] text-gray-300 font-mono w-4 text-center flex-shrink-0">{index + 1}</span>
                  <input
                    type="text" value={param.name}
                    onChange={(e) => handleParamNameChange(index, e.target.value)}
                    placeholder={isVerify(param) ? "Verification name" : "Parameter name"}
                    className="flex-1 min-w-0 px-2.5 py-1.5 text-sm border border-gray-200 rounded focus:ring-1 focus:ring-cyan-400 outline-none"
                  />
                  {isVerify(param) ? (
                    <select
                      value={param.verification_config?.check_type || "custom"}
                      onChange={(e) => updateVerificationConfig(index, "check_type", e.target.value)}
                      className="w-[110px] px-1.5 py-1.5 text-xs border border-purple-200 rounded focus:ring-1 focus:ring-purple-400 outline-none bg-white flex-shrink-0"
                    >
                      {VERIFICATION_CHECK_TYPES.map((t) => (
                        <option key={t.value} value={t.value}>{t.label}</option>
                      ))}
                    </select>
                  ) : (
                    <select
                      value={param.type}
                      onChange={(e) => updateParameter(index, "type", e.target.value)}
                      className="w-[75px] px-1.5 py-1.5 text-xs border border-gray-200 rounded focus:ring-1 focus:ring-cyan-400 outline-none bg-white flex-shrink-0"
                    >
                      {PARAM_TYPES.map((t) => (
                        <option key={t.value} value={t.value}>{t.label}</option>
                      ))}
                    </select>
                  )}
                  <input
                    type="number"
                    value={param.page ?? ""}
                    onChange={(e) => updateParameter(index, "page", e.target.value ? parseInt(e.target.value) : null)}
                    placeholder="Pg"
                    min={1}
                    className="w-[48px] px-1.5 py-1.5 text-xs text-center border border-gray-200 rounded focus:ring-1 focus:ring-cyan-400 outline-none flex-shrink-0 placeholder:text-gray-300"
                  />
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

                {/* Row 2: Comment (extract) or Instruction (verify) */}
                <div className="pl-6">
                  {isVerify(param) ? (
                    <>
                      {/* Show hint for the selected check type */}
                      {param.verification_config?.check_type && param.verification_config.check_type !== "custom" && (
                        <div className="text-[10px] text-purple-400 mb-1">
                          {CHECK_TYPE_HINTS[param.verification_config.check_type] || ""}
                        </div>
                      )}
                      <textarea
                        value={param.verification_config?.instruction || ""}
                        onChange={(e) => updateVerificationConfig(index, "instruction", e.target.value)}
                        placeholder={param.verification_config?.check_type === "custom"
                          ? "Write your verification instruction (e.g., 'Check all temperatures are within 20-25°C')"
                          : "Override default instruction (optional)"}
                        rows={2}
                        className="w-full px-2 py-1 text-[11px] text-gray-500 border border-purple-100 rounded focus:border-purple-300 outline-none bg-purple-50/30 placeholder:text-gray-300 resize-none"
                      />
                    </>
                  ) : (
                    <input
                      type="text" value={param.hint || ""}
                      onChange={(e) => updateParameter(index, "hint", e.target.value)}
                      placeholder="Comment for AI (e.g., 'Look in Results column, page 1')"
                      className="w-full px-2 py-1 text-[11px] text-gray-400 border-b border-gray-100 focus:border-cyan-300 outline-none bg-transparent placeholder:text-gray-300"
                    />
                  )}
                </div>

                {/* Row 3: Live Page Preview */}
                {processId && param.name.trim().length >= 2 && (
                  <div className="pl-6 mt-1.5">
                    {previewLoading[index] ? (
                      <div className="flex items-center text-[10px] text-gray-400">
                        <svg className="animate-spin w-3 h-3 mr-1 text-cyan-400" fill="none" viewBox="0 0 24 24">
                          <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                          <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                        </svg>
                        Searching...
                      </div>
                    ) : pagePreview[index] && pagePreview[index]!.total_matches > 0 ? (
                      <div className="flex flex-wrap items-center gap-1">
                        <span className="text-[10px] text-gray-400">Found on:</span>
                        {pagePreview[index]!.pages.slice(0, 10).map((pr) => (
                          <button
                            key={pr.page}
                            onClick={() => handlePageBadgeClick(index, pr.page)}
                            title={pr.preview}
                            className={`inline-flex items-center justify-center min-w-[22px] px-1.5 py-0.5 text-[10px] font-medium rounded border transition-colors ${
                              param.page === pr.page
                                ? "bg-cyan-500 text-white border-cyan-500"
                                : "bg-gray-50 text-gray-600 border-gray-200 hover:bg-cyan-50 hover:text-cyan-700 hover:border-cyan-300"
                            }`}
                          >
                            {pr.page}
                          </button>
                        ))}
                        {pagePreview[index]!.pages.length > 10 && (
                          <span className="text-[10px] text-gray-300">+{pagePreview[index]!.pages.length - 10} more</span>
                        )}
                      </div>
                    ) : pagePreview[index] && pagePreview[index]!.total_matches === 0 ? (
                      <span className="text-[10px] text-gray-300">No matches found in document</span>
                    ) : null}
                  </div>
                )}
                {!processId && param.name.trim().length >= 2 && (
                  <div className="pl-6 mt-1">
                    <span className="text-[10px] text-gray-300">Upload a document to see page matches</span>
                  </div>
                )}
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
