/**
 * Chat History Service
 * API client for chat persistence backend
 */

const API_BASE_URL = "https://aiparser.abbvienet.com"; // Local development
//const API_BASE_URL = "https://dev.aiparser.ir-bioprocess-poc.awscloud.abbvienet.com"; // Dev environment (via nginx proxy)

export interface Chat {
  chat_id: string;
  title: string;
  message_count: number;
  latest_document?: string;
  is_archived: boolean;
  updated_at: string;
  created_at: string;
}

export interface ChatDocument {
  document_id: string;
  document_name: string;
  upload_order: number;
  extraction_done: boolean;
  is_active: boolean;
  process_id?: string;  // Phase 4: Weaviate filter key for RAG search
  document_type?: string;  // e.g., 'coa', 'hbr'
}

export interface ChatMessage {
  message_id: string;
  role: "user" | "assistant" | "system";
  content: string;
  message_type: string;
  document_id?: string;
  references?: any;
  is_summarized: boolean;
  sequence_num?: number;
  created_at: string;
}

export interface ChatDetails {
  chat: {
    chat_id: string;
    title: string;
    message_count: number;
    active_document_id?: string;
    summary?: string;
    is_archived: boolean;
    created_at: string;
    updated_at: string;
  };
  documents: ChatDocument[];
  messages: ChatMessage[];
}

export async function createChat(title = "New Chat"): Promise<Chat> {
  const res = await fetch(`${API_BASE_URL}/api/chats`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    credentials: "include",
    body: JSON.stringify({ title }),
  });
  if (!res.ok) {
    const errorText = await res.text();
    throw new Error(`Failed to create chat: ${res.status} ${errorText}`);
  }
  return (await res.json()).chat;
}

export async function getUserChats(includeArchived = false): Promise<Chat[]> {
  const url = `${API_BASE_URL}/api/chats${includeArchived ? "?include_archived=true" : ""}`;
  const res = await fetch(url, { credentials: "include" });
  if (!res.ok) {
    const errorText = await res.text();
    throw new Error(`Failed to get chats: ${res.status} ${errorText}`);
  }
  return (await res.json()).chats;
}

export async function getChatDetails(chatId: string): Promise<ChatDetails> {
  const res = await fetch(`${API_BASE_URL}/api/chats/${chatId}`, { credentials: "include" });
  if (!res.ok) throw new Error(`Failed to get chat: ${res.statusText}`);
  return await res.json();
}

export async function updateChat(chatId: string, updates: { title?: string; is_archived?: boolean; active_document_id?: string }): Promise<Chat> {
  const res = await fetch(`${API_BASE_URL}/api/chats/${chatId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    credentials: "include",
    body: JSON.stringify(updates),
  });
  if (!res.ok) throw new Error(`Failed to update chat: ${res.statusText}`);
  return (await res.json()).chat;
}

export async function deleteChat(chatId: string): Promise<boolean> {
  const res = await fetch(`${API_BASE_URL}/api/chats/${chatId}`, {
    method: "DELETE",
    credentials: "include",
  });
  if (!res.ok) throw new Error(`Failed to delete chat: ${res.statusText}`);
  return true;
}

export async function sendChatMessage(chatId: string, content: string, documentId?: string) {
  const res = await fetch(`${API_BASE_URL}/api/chats/${chatId}/messages`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    credentials: "include",
    body: JSON.stringify({ content, document_id: documentId }),
  });
  if (!res.ok) throw new Error(`Failed to send message: ${res.statusText}`);
  return await res.json();
}

export async function saveAssistantMessage(
  chatId: string,
  content: string,
  documentId?: string,
  references?: Array<{
    page: number;
    bbox: { left: number; top: number; width: number; height: number };
    cell_id: string;
    text: string;
    row?: number;
    col?: number;
    type?: string;
    highlight_type?: string;  // 'error' | 'info' for Visual Audit
  }>
): Promise<{
  success: boolean;
  assistant_message: {
    message_id: string;
    role: string;
    content: string;
    sequence_num?: number;
    created_at?: string;
  };
  current_summary?: string;
}> {
  const res = await fetch(`${API_BASE_URL}/api/chats/${chatId}/messages/assistant`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    credentials: "include",
    body: JSON.stringify({
      content,
      document_id: documentId,
      references: references  // Phase 5: Pass references for PDF highlighting
    }),
  });
  if (!res.ok) throw new Error(`Failed to save assistant message: ${res.statusText}`);
  return await res.json();
}

export async function addDocumentToChat(chatId: string, doc: {
  document_id: string;
  document_name: string;
  page_count?: number;
  file_size?: number;
  weaviate_source?: string;
  process_id?: string;  // Phase 4: Weaviate filter key for RAG search
  document_type?: string;  // e.g., 'coa', 'hbr'
  processing_status?: string;  // 'pending', 'processing', 'completed', 'failed'
  extraction_done?: boolean;  // Whether extraction completed successfully
}): Promise<ChatDocument> {
  const res = await fetch(`${API_BASE_URL}/api/chats/${chatId}/documents`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    credentials: "include",
    body: JSON.stringify(doc),
  });
  if (!res.ok) throw new Error(`Failed to add document: ${res.statusText}`);
  return (await res.json()).document;
}

export function formatRelativeTime(dateString: string): string {
  const date = new Date(dateString);
  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  const diffMins = Math.floor(diffMs / 60000);
  const diffHours = Math.floor(diffMs / 3600000);
  const diffDays = Math.floor(diffMs / 86400000);

  if (diffMins < 1) return "Just now";
  if (diffMins < 60) return `${diffMins}m ago`;
  if (diffHours < 24) return `${diffHours}h ago`;
  if (diffDays < 7) return `${diffDays}d ago`;
  return date.toLocaleDateString();
}
