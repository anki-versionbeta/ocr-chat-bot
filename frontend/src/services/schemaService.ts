/**
 * Extraction Schema Service
 * API client for schema CRUD operations
 */

const API_BASE_URL = "https://aiparser.abbvienet.com"; // Local development
//const API_BASE_URL = "https://dev.aiparser.ir-bioprocess-poc.awscloud.abbvienet.com"; // Dev environment

export interface VerificationConfig {
  check_type: string; // "elapsed_time" | "witness_verification" | "significant_figures" | "correction_check" | "calculation_check" | "date_sequence" | "custom"
  instruction?: string;
}

export interface ParameterDefinition {
  name: string;
  type: "string" | "number" | "date" | "boolean";
  hint?: string;
  required: boolean;
  unit?: string;
  page?: number | null;
  task_type?: "extract" | "verify";
  verification_config?: VerificationConfig;
}

export interface ExtractionSchema {
  schema_id: string;
  user_id: string;
  name: string;
  description?: string;
  document_type: string;
  parameters: ParameterDefinition[];
  is_shared: boolean;
  created_at: string;
  updated_at: string;
}

export async function getSchemas(): Promise<ExtractionSchema[]> {
  const res = await fetch(`${API_BASE_URL}/api/schemas`, {
    credentials: "include",
  });
  if (!res.ok) throw new Error("Failed to fetch schemas");
  const data = await res.json();
  return data.schemas;
}

export async function createSchema(
  name: string,
  parameters: ParameterDefinition[],
  description?: string,
  documentType: string = "general",
  isShared: boolean = false
): Promise<ExtractionSchema> {
  const res = await fetch(`${API_BASE_URL}/api/schemas`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    credentials: "include",
    body: JSON.stringify({
      name,
      parameters,
      description,
      document_type: documentType,
      is_shared: isShared,
    }),
  });
  if (!res.ok) throw new Error("Failed to create schema");
  return res.json();
}

export async function updateSchema(
  schemaId: string,
  updates: Partial<{
    name: string;
    description: string;
    document_type: string;
    parameters: ParameterDefinition[];
    is_shared: boolean;
  }>
): Promise<ExtractionSchema> {
  const res = await fetch(`${API_BASE_URL}/api/schemas/${schemaId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    credentials: "include",
    body: JSON.stringify(updates),
  });
  if (!res.ok) throw new Error("Failed to update schema");
  return res.json();
}

export async function deleteSchema(schemaId: string): Promise<void> {
  const res = await fetch(`${API_BASE_URL}/api/schemas/${schemaId}`, {
    method: "DELETE",
    credentials: "include",
  });
  if (!res.ok) throw new Error("Failed to delete schema");
}


// ============================================================================
// DOCUMENT SEARCH (Neo4j Ctrl+F)
// ============================================================================

export interface SearchMatch {
  type: "cell" | "section" | "line";
  key: string;
  text: string;
  bbox: {
    left: number;
    top: number;
    right: number;
    bottom: number;
    width: number;
    height: number;
  };
  row?: number;
  col?: number;
  chunk_index?: number;
}

export interface SearchPageResult {
  page: number;
  match_count: number;
  matches: SearchMatch[];
  preview: string;
}

export interface DocumentSearchResult {
  query: string;
  total_matches: number;
  total_pages: number;
  pages: SearchPageResult[];
}

export async function searchDocumentText(
  processId: string,
  query: string,
  limit: number = 200
): Promise<DocumentSearchResult> {
  const params = new URLSearchParams({ q: query, limit: limit.toString() });
  const res = await fetch(
    `${API_BASE_URL}/api/documents/${processId}/search?${params}`,
    { credentials: "include" }
  );
  if (!res.ok) throw new Error("Search failed");
  return res.json();
}


// ============================================================================
// SCHEMA EXECUTION — Discovery + Extraction
// ============================================================================

export interface DiscoveryPageCandidate {
  page: number;
  preview: string;
}

export interface DiscoveryParam {
  param_name: string;
  hint: string;
  candidate_pages: DiscoveryPageCandidate[];
  confirmed_pages: number[];
  auto_confirmed: boolean;
  source: "neo4j" | "hint" | "not_found";
}

export interface DiscoveryResponse {
  execution_id: string;
  schema_id: string;
  process_id: string;
  discovery: DiscoveryParam[];
  status: string;
}

export interface ParamResult {
  param_name: string;
  task_type?: "extract" | "verify";
  // Extract fields:
  value: string | null;
  confidence: number;
  ref: string | null;
  bbox: { left: number; top: number; width: number; height: number } | null;
  // Verify fields:
  status?: "pass" | "fail" | "warning" | null;
  finding?: string | null;
  correction?: string | null;
  expected?: string | null;
  actual?: string | null;
  performed_by?: string | null;
  witnessed_by?: string | null;
  refs?: string[] | null;
  bboxes?: Array<{ left: number; top: number; width: number; height: number }> | null;
  // Common:
  found: boolean;
  page: number;
  error?: string;
}

export interface ExecutionSummary {
  total_params: number;
  found: number;
  not_found: number;
  pages_analyzed: number[];
  gemini_calls: number;
  extract_count?: number;
  verify_count?: number;
  verify_pass?: number;
  verify_fail?: number;
  verify_warning?: number;
}

export interface ExecutionResult {
  execution_id: string;
  status: string;
  discovery: DiscoveryParam[];
  results: ParamResult[];
  summary: ExecutionSummary;
}

export async function discoverPages(
  schemaId: string,
  processId: string
): Promise<DiscoveryResponse> {
  const res = await fetch(`${API_BASE_URL}/api/schemas/${schemaId}/discover`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    credentials: "include",
    body: JSON.stringify({ process_id: processId }),
  });
  if (!res.ok) throw new Error("Discovery failed");
  return res.json();
}

export interface ConfirmedParam {
  param_name: string;
  pages: number[];
  param_def?: Record<string, unknown>;
}

export async function runExtraction(
  executionId: string,
  processId: string,
  confirmedParams: ConfirmedParam[]
): Promise<Response> {
  // Returns raw Response for SSE streaming
  return fetch(
    `${API_BASE_URL}/api/schemas/executions/${executionId}/run`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      credentials: "include",
      body: JSON.stringify({
        process_id: processId,
        confirmed_params: confirmedParams,
      }),
    }
  );
}

export async function getExecutionResult(
  executionId: string
): Promise<ExecutionResult> {
  const res = await fetch(
    `${API_BASE_URL}/api/schemas/executions/${executionId}`,
    { credentials: "include" }
  );
  if (!res.ok) throw new Error("Failed to get execution");
  return res.json();
}

export interface ExecutionListItem {
  execution_id: string;
  schema_id: string;
  process_id: string;
  status: string;
  summary: ExecutionSummary | null;
  started_at: string;
  completed_at: string | null;
}

export async function getSchemaExecutions(
  schemaId: string
): Promise<ExecutionListItem[]> {
  const res = await fetch(
    `${API_BASE_URL}/api/schemas/${schemaId}/executions`,
    { credentials: "include" }
  );
  if (!res.ok) throw new Error("Failed to get executions");
  const data = await res.json();
  return data.executions;
}

export function getExecutionDownloadUrl(executionId: string): string {
  return `${API_BASE_URL}/api/schemas/executions/${executionId}/download`;
}
