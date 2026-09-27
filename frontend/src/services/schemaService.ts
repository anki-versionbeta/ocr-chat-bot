/**
 * Extraction Schema Service
 * API client for schema CRUD operations
 */

const API_BASE_URL = "http://localhost:5000";

export interface ParameterDefinition {
  name: string;
  type: "string" | "number" | "date" | "boolean";
  hint?: string;
  required: boolean;
  unit?: string;
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
