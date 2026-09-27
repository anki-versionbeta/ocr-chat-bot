"use client";

import React, { useState, useEffect, useRef, useImperativeHandle, forwardRef, useMemo } from "react";
import { createPortal } from "react-dom";
import { useVirtualizer } from "@tanstack/react-virtual";
import {
  Chat,
  getUserChats,
  createChat,
  updateChat,
  deleteChat,
} from "../services/chatHistory";

interface ChatSidebarProps {
  isOpen: boolean;
  onToggle: () => void;
  currentChatId?: string;
  onSelectChat: (chatId: string) => void;
  onNewChat: (chatId: string) => void;
}

// Expose refresh method to parent component
export interface ChatSidebarRef {
  refreshChats: () => Promise<void>;
}

const ChatSidebar = forwardRef<ChatSidebarRef, ChatSidebarProps>(({
  isOpen,
  onToggle,
  currentChatId,
  onSelectChat,
  onNewChat,
}, ref) => {
  const [chats, setChats] = useState<Chat[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editTitle, setEditTitle] = useState("");
  const [menuOpenId, setMenuOpenId] = useState<string | null>(null);
  const [menuPosition, setMenuPosition] = useState<{ top: number; left: number } | null>(null);
  const [deleteConfirmId, setDeleteConfirmId] = useState<string | null>(null);
  const [searchQuery, setSearchQuery] = useState("");
  const [showArchived, setShowArchived] = useState(false);
  const editInputRef = useRef<HTMLInputElement>(null);
  const menuRef = useRef<HTMLDivElement>(null);
  const scrollContainerRef = useRef<HTMLDivElement>(null);

  // Load chats on mount
  useEffect(() => {
    loadChats();
  }, []);

  // Focus edit input when editing
  useEffect(() => {
    if (editingId && editInputRef.current) {
      editInputRef.current.focus();
      editInputRef.current.select();
    }
  }, [editingId]);

  // Close menu when clicking outside
  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
        setMenuOpenId(null);
        setMenuPosition(null);
      }
    };
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  const loadChats = async (showLoading = true) => {
    try {
      if (showLoading) setLoading(true);
      setError(null);
      const data = await getUserChats();
      setChats(data);
    } catch (err) {
      setError("Failed to load chats");
      console.error(err);
    } finally {
      if (showLoading) setLoading(false);
    }
  };

  // Expose refreshChats to parent component via ref
  useImperativeHandle(ref, () => ({
    refreshChats: async () => {
      await loadChats(false); // Don't show loading spinner for refresh
    }
  }));

  const handleNewChat = () => {
    // Don't create chat yet - just signal to parent to show fresh page
    // Chat will be created when user sends first message (like ChatGPT/Claude)
    onNewChat("");  // Empty string signals "new chat mode"
  };

  const handleRename = async (chatId: string) => {
    if (!editTitle.trim()) {
      setEditingId(null);
      return;
    }
    try {
      const updated = await updateChat(chatId, { title: editTitle.trim() });
      setChats((prev) =>
        prev.map((c) => (c.chat_id === chatId ? { ...c, title: updated.title } : c))
      );
      setEditingId(null);
    } catch (err) {
      console.error("Failed to rename chat:", err);
    }
  };

  const handleDelete = async (chatId: string) => {
    try {
      await deleteChat(chatId);
      setChats((prev) => prev.filter((c) => c.chat_id !== chatId));
      setDeleteConfirmId(null);
      if (currentChatId === chatId) {
        // Select next available chat or create new
        const remaining = chats.filter((c) => c.chat_id !== chatId && !c.is_archived);
        if (remaining.length > 0) {
          onSelectChat(remaining[0].chat_id);
        } else {
          handleNewChat();
        }
      }
    } catch (err) {
      console.error("Failed to delete chat:", err);
    }
  };

  const handleArchive = async (chatId: string, archive: boolean) => {
    try {
      await updateChat(chatId, { is_archived: archive });
      setChats((prev) =>
        prev.map((c) => (c.chat_id === chatId ? { ...c, is_archived: archive } : c))
      );
      setMenuOpenId(null);
      setMenuPosition(null);
      // If archiving the current chat, switch to another chat
      if (archive && currentChatId === chatId) {
        const remaining = chats.filter((c) => c.chat_id !== chatId && !c.is_archived);
        if (remaining.length > 0) {
          onSelectChat(remaining[0].chat_id);
        } else {
          handleNewChat();
        }
      }
    } catch (err) {
      console.error("Failed to archive chat:", err);
    }
  };

  const startEditing = (chat: Chat) => {
    setEditingId(chat.chat_id);
    setEditTitle(chat.title);
    setMenuOpenId(null);
    setMenuPosition(null);
  };

  // Filter chats: exclude archived unless showArchived is true, and apply search
  const activeChats = chats.filter((chat) =>
    !chat.is_archived && chat.title.toLowerCase().includes(searchQuery.toLowerCase())
  );
  const archivedChats = chats.filter((chat) =>
    chat.is_archived && chat.title.toLowerCase().includes(searchQuery.toLowerCase())
  );

  // Helper function to safely parse date from backend
  // Backend sends UTC timestamps WITHOUT timezone suffix (e.g., "2026-02-05T01:11:10.580412")
  // We need to explicitly treat them as UTC by appending 'Z'
  const parseDate = (dateStr: string | undefined | null): Date => {
    // Handle undefined/null - return current time (new chats go to "Today")
    if (!dateStr) {
      return new Date();
    }

    // Normalize the date string:
    // 1. Replace space with 'T' if needed (for "2026-02-05 01:11:10" format)
    // 2. Append 'Z' if no timezone info to treat as UTC
    let normalized = dateStr.replace(" ", "T");

    // Check if it already has timezone info (Z, +XX:XX, or -XX:XX)
    const hasTimezone = /[Zz]$/.test(normalized) || /[+-]\d{2}:\d{2}$/.test(normalized);
    if (!hasTimezone) {
      normalized += "Z"; // Treat as UTC
    }

    const date = new Date(normalized);

    // If invalid, return current time (will go to "Today")
    if (isNaN(date.getTime())) {
      console.warn("Could not parse date:", dateStr, "-> normalized:", normalized);
      return new Date();
    }

    return date;
  };

  // Group chats by time
  const groupedChats = {
    today: [] as Chat[],
    yesterday: [] as Chat[],
    thisWeek: [] as Chat[],
    older: [] as Chat[],
  };

  const now = new Date();
  const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  const yesterday = new Date(today.getTime() - 86400000);
  const weekAgo = new Date(today.getTime() - 7 * 86400000);

  activeChats.forEach((chat) => {
    const chatDate = parseDate(chat.updated_at);

    if (chatDate >= today) {
      groupedChats.today.push(chat);
    } else if (chatDate >= yesterday) {
      groupedChats.yesterday.push(chat);
    } else if (chatDate >= weekAgo) {
      groupedChats.thisWeek.push(chat);
    } else {
      groupedChats.older.push(chat);
    }
  });

  // Flatten grouped chats for virtualization
  type FlatItem = { type: "header"; title: string } | { type: "chat"; chat: Chat };

  const flattenedItems = useMemo<FlatItem[]>(() => {
    const items: FlatItem[] = [];

    if (groupedChats.today.length > 0) {
      items.push({ type: "header", title: "Today" });
      groupedChats.today.forEach(chat => items.push({ type: "chat", chat }));
    }
    if (groupedChats.yesterday.length > 0) {
      items.push({ type: "header", title: "Yesterday" });
      groupedChats.yesterday.forEach(chat => items.push({ type: "chat", chat }));
    }
    if (groupedChats.thisWeek.length > 0) {
      items.push({ type: "header", title: "This Week" });
      groupedChats.thisWeek.forEach(chat => items.push({ type: "chat", chat }));
    }
    if (groupedChats.older.length > 0) {
      items.push({ type: "header", title: "Older" });
      groupedChats.older.forEach(chat => items.push({ type: "chat", chat }));
    }

    return items;
  }, [groupedChats.today, groupedChats.yesterday, groupedChats.thisWeek, groupedChats.older]);

  // Virtualizer for the chat list
  const rowVirtualizer = useVirtualizer({
    count: flattenedItems.length,
    getScrollElement: () => scrollContainerRef.current,
    estimateSize: (index) => {
      // Headers are smaller than chat items
      return flattenedItems[index]?.type === "header" ? 32 : 48;
    },
    overscan: 5, // Render 5 extra items above/below viewport
  });

  const renderChatItem = (chat: Chat) => {
    const isActive = chat.chat_id === currentChatId;
    const isEditing = editingId === chat.chat_id;

    return (
      <div
        key={chat.chat_id}
        className={`group relative flex items-center gap-2 px-3 py-2.5 rounded-xl cursor-pointer transition-all duration-200 ${
          isActive
            ? "bg-gradient-to-r from-cyan-500/15 to-blue-500/10 border border-cyan-400/30 shadow-sm"
            : "hover:bg-gray-100/80 border border-transparent"
        }`}
        onClick={() => !isEditing && onSelectChat(chat.chat_id)}
      >
        {/* Content */}
        <div className="flex-1 min-w-0">
          {isEditing ? (
            <input
              ref={editInputRef}
              type="text"
              value={editTitle}
              onChange={(e) => setEditTitle(e.target.value)}
              onBlur={() => handleRename(chat.chat_id)}
              onKeyDown={(e) => {
                if (e.key === "Enter") handleRename(chat.chat_id);
                if (e.key === "Escape") setEditingId(null);
              }}
              onClick={(e) => e.stopPropagation()}
              className="w-full px-2 py-1 text-sm bg-white border border-cyan-300 rounded-md focus:outline-none focus:ring-2 focus:ring-cyan-400"
            />
          ) : (
            <p
              className={`text-sm font-medium truncate ${
                isActive ? "text-cyan-700" : "text-gray-700"
              }`}
            >
              {chat.title}
            </p>
          )}
        </div>

        {/* Menu button */}
        {!isEditing && (
          <button
            onClick={(e) => {
              e.stopPropagation();
              if (menuOpenId === chat.chat_id) {
                setMenuOpenId(null);
                setMenuPosition(null);
              } else {
                const rect = (e.currentTarget as HTMLElement).getBoundingClientRect();
                setMenuPosition({ top: rect.bottom + 4, left: rect.right - 144 });
                setMenuOpenId(chat.chat_id);
              }
            }}
            className={`flex-shrink-0 p-1 rounded-md opacity-0 group-hover:opacity-100 transition-opacity ${
              isActive ? "hover:bg-cyan-200/50" : "hover:bg-gray-200"
            }`}
          >
            <svg className="w-4 h-4 text-gray-500" fill="currentColor" viewBox="0 0 20 20">
              <path d="M10 6a2 2 0 110-4 2 2 0 010 4zM10 12a2 2 0 110-4 2 2 0 010 4zM10 18a2 2 0 110-4 2 2 0 010 4z" />
            </svg>
          </button>
        )}

        {/* Dropdown Menu — rendered via Portal to escape transform/overflow parents */}
        {menuOpenId === chat.chat_id && menuPosition && typeof document !== "undefined" &&
          createPortal(
            <div
              ref={menuRef}
              className="w-36 bg-white rounded-lg shadow-lg border border-gray-200 py-1"
              style={{
                position: "fixed",
                top: menuPosition.top,
                left: menuPosition.left,
                zIndex: 99999,
              }}
            >
              <button
                onClick={(e) => {
                  e.stopPropagation();
                  startEditing(chat);
                }}
                className="w-full px-3 py-2 text-sm text-left text-gray-700 hover:bg-gray-50 flex items-center gap-2 cursor-pointer"
              >
                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z" />
                </svg>
                Rename
              </button>
              <button
                onClick={(e) => {
                  e.stopPropagation();
                  handleArchive(chat.chat_id, !chat.is_archived);
                }}
                className="w-full px-3 py-2 text-sm text-left text-gray-700 hover:bg-gray-50 flex items-center gap-2 cursor-pointer"
              >
                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  {chat.is_archived ? (
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 8h14M5 8a2 2 0 110-4h14a2 2 0 110 4M5 8v10a2 2 0 002 2h10a2 2 0 002-2V8m-9 4h4" />
                  ) : (
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 8h14M5 8a2 2 0 110-4h14a2 2 0 110 4M5 8v10a2 2 0 002 2h10a2 2 0 002-2V8m-9 4l2 2 4-4" />
                  )}
                </svg>
                {chat.is_archived ? "Unarchive" : "Archive"}
              </button>
              <button
                onClick={(e) => {
                  e.stopPropagation();
                  setDeleteConfirmId(chat.chat_id);
                  setMenuOpenId(null);
                  setMenuPosition(null);
                }}
                className="w-full px-3 py-2 text-sm text-left text-red-600 hover:bg-red-50 flex items-center gap-2 cursor-pointer"
              >
                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                </svg>
                Delete
              </button>
            </div>,
            document.body
          )
        }
      </div>
    );
  };

  const renderGroup = (title: string, chatsInGroup: Chat[]) => {
    if (chatsInGroup.length === 0) return null;
    return (
      <div className="mb-4">
        <p className="px-3 py-1.5 text-xs font-semibold text-gray-400 uppercase tracking-wider">
          {title}
        </p>
        <div className="space-y-1">{chatsInGroup.map(renderChatItem)}</div>
      </div>
    );
  };

  return (
    <>
      {/* Sidebar - fixed position, full height */}
      <div
        className={`fixed left-0 top-0 h-screen bg-white border-r border-gray-200 shadow-lg z-20 transition-all duration-300 ease-in-out ${
          isOpen ? "w-72 translate-x-0" : "w-72 -translate-x-full"
        }`}
      >
        {/* Header */}
        <div className="flex items-center justify-between p-4 border-b border-gray-100">
          <div className="flex items-center gap-2">
            <div className="w-7 h-7 rounded-lg bg-gray-100 flex items-center justify-center">
              <svg className="w-4 h-4 text-gray-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z" />
              </svg>
            </div>
            <h2 className="text-base font-semibold text-gray-700">Chats</h2>
          </div>
          <div className="flex items-center gap-1">
            {/* New Chat Button - Icon style */}
            <button
              onClick={handleNewChat}
              className="p-2 rounded-lg hover:bg-gray-100 transition-colors group"
              title="New Chat"
            >
              <svg className="w-5 h-5 text-gray-500 group-hover:text-gray-700" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z" />
              </svg>
            </button>
            {/* Close Sidebar Button */}
            <button
              onClick={onToggle}
              className="p-2 rounded-lg hover:bg-gray-100 transition-colors group"
              title="Close sidebar"
            >
              <svg className="w-5 h-5 text-gray-500 group-hover:text-gray-700" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M11 19l-7-7 7-7m8 14l-7-7 7-7" />
              </svg>
            </button>
          </div>
        </div>

        {/* Search */}
        <div className="px-3 py-3">
          <div className="relative">
            <svg
              className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400"
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
            </svg>
            <input
              type="text"
              placeholder="Search chats..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="w-full pl-9 pr-3 py-2 text-sm bg-gray-50 border border-gray-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-cyan-400 focus:border-transparent transition-all"
            />
          </div>
        </div>

        {/* Chat List */}
        <div
          ref={scrollContainerRef}
          className="flex-1 overflow-y-auto px-2 pb-4"
          style={{ maxHeight: "calc(100vh - 200px)" }}
        >
          {loading ? (
            <div className="flex flex-col items-center justify-center py-8 text-gray-400">
              <div className="w-8 h-8 border-2 border-cyan-500 border-t-transparent rounded-full animate-spin mb-2" />
              <p className="text-sm">Loading chats...</p>
            </div>
          ) : error ? (
            <div className="flex flex-col items-center justify-center py-8 text-red-500">
              <svg className="w-8 h-8 mb-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
              </svg>
              <p className="text-sm">{error}</p>
              <button
                onClick={() => loadChats()}
                className="mt-2 px-3 py-1 text-sm bg-red-100 text-red-600 rounded-lg hover:bg-red-200 transition-colors"
              >
                Retry
              </button>
            </div>
          ) : activeChats.length === 0 && archivedChats.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-8 text-gray-400">
              <svg className="w-12 h-12 mb-2 text-gray-300" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z" />
              </svg>
              <p className="text-sm font-medium">No chats yet</p>
              <p className="text-xs text-gray-400 mt-1">Start a new conversation</p>
            </div>
          ) : activeChats.length === 0 && archivedChats.length > 0 ? (
            // Only archived chats exist
            <div>
              <div className="flex flex-col items-center justify-center py-6 text-gray-400">
                <p className="text-sm">No active chats</p>
                <p className="text-xs text-gray-400 mt-1">All chats are archived</p>
              </div>
              {/* Show archived section */}
              <div className="mt-2 pt-2 border-t border-gray-200">
                <button
                  onClick={() => setShowArchived(!showArchived)}
                  className="w-full px-3 py-2 text-sm text-gray-600 hover:bg-gray-100 rounded-lg flex items-center justify-between transition-colors"
                >
                  <div className="flex items-center gap-2">
                    <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 8h14M5 8a2 2 0 110-4h14a2 2 0 110 4M5 8v10a2 2 0 002 2h10a2 2 0 002-2V8m-9 4h4" />
                    </svg>
                    <span>Archived ({archivedChats.length})</span>
                  </div>
                  <svg
                    className={`w-4 h-4 transition-transform duration-200 ${showArchived ? "rotate-180" : ""}`}
                    fill="none"
                    stroke="currentColor"
                    viewBox="0 0 24 24"
                  >
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
                  </svg>
                </button>
                {showArchived && (
                  <div className="mt-2 space-y-1">
                    {archivedChats.map(renderChatItem)}
                  </div>
                )}
              </div>
            </div>
          ) : (
            <>
              {/* Virtualized Active chats grouped by time */}
              <div
                style={{
                  height: `${rowVirtualizer.getTotalSize()}px`,
                  width: "100%",
                  position: "relative",
                }}
              >
                {rowVirtualizer.getVirtualItems().map((virtualRow) => {
                  const item = flattenedItems[virtualRow.index];
                  return (
                    <div
                      key={virtualRow.key}
                      style={{
                        position: "absolute",
                        top: 0,
                        left: 0,
                        width: "100%",
                        height: `${virtualRow.size}px`,
                        transform: `translateY(${virtualRow.start}px)`,
                      }}
                    >
                      {item.type === "header" ? (
                        <p className="px-3 py-1.5 text-xs font-semibold text-gray-400 uppercase tracking-wider">
                          {item.title}
                        </p>
                      ) : (
                        renderChatItem(item.chat)
                      )}
                    </div>
                  );
                })}
              </div>

              {/* Show archived toggle if there are archived chats */}
              {archivedChats.length > 0 && (
                <div className="mt-4 pt-4 border-t border-gray-200">
                  <button
                    onClick={() => setShowArchived(!showArchived)}
                    className="w-full px-3 py-2 text-sm text-gray-600 hover:bg-gray-100 rounded-lg flex items-center justify-between transition-colors"
                  >
                    <div className="flex items-center gap-2">
                      <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 8h14M5 8a2 2 0 110-4h14a2 2 0 110 4M5 8v10a2 2 0 002 2h10a2 2 0 002-2V8m-9 4h4" />
                      </svg>
                      <span>Archived ({archivedChats.length})</span>
                    </div>
                    <svg
                      className={`w-4 h-4 transition-transform duration-200 ${showArchived ? "rotate-180" : ""}`}
                      fill="none"
                      stroke="currentColor"
                      viewBox="0 0 24 24"
                    >
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
                    </svg>
                  </button>

                  {/* Archived chats list */}
                  {showArchived && (
                    <div className="mt-2 space-y-1">
                      {archivedChats.map(renderChatItem)}
                    </div>
                  )}
                </div>
              )}
            </>
          )}
        </div>
      </div>

      {/* Delete Confirmation Modal */}
      {deleteConfirmId && (
        <div className="fixed inset-0 bg-black/50 backdrop-blur-sm z-50 flex items-center justify-center animate-fadeIn">
          <div className="bg-white rounded-2xl shadow-2xl p-6 max-w-sm mx-4 animate-slideInUp">
            <div className="flex items-center gap-3 mb-4">
              <div className="w-10 h-10 rounded-full bg-red-100 flex items-center justify-center">
                <svg className="w-5 h-5 text-red-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                </svg>
              </div>
              <div>
                <h3 className="text-lg font-semibold text-gray-900">Delete Chat</h3>
                <p className="text-sm text-gray-500">This action cannot be undone</p>
              </div>
            </div>
            <p className="text-gray-600 mb-6">
              Are you sure you want to delete this chat? All messages will be permanently removed.
            </p>
            <div className="flex gap-3">
              <button
                onClick={() => setDeleteConfirmId(null)}
                className="flex-1 px-4 py-2 bg-gray-100 text-gray-700 rounded-xl font-medium hover:bg-gray-200 transition-colors"
              >
                Cancel
              </button>
              <button
                onClick={() => handleDelete(deleteConfirmId)}
                className="flex-1 px-4 py-2 bg-red-500 text-white rounded-xl font-medium hover:bg-red-600 transition-colors"
              >
                Delete
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Overlay when sidebar is open on mobile */}
      {isOpen && (
        <div
          className="fixed inset-0 bg-black/20 z-30 lg:hidden"
          onClick={onToggle}
        />
      )}
    </>
  );
});

ChatSidebar.displayName = "ChatSidebar";

export default ChatSidebar;
