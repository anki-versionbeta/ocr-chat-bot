"use client";
import { useEffect, useState, useRef, useCallback, useMemo } from "react";
import React from "react";
import { useRouter } from "next/navigation";
import dynamic from "next/dynamic";
import { useVirtualizer } from "@tanstack/react-virtual";
import DOMPurify from "dompurify";

// Environment Configuration - Comment/Uncomment as needed
//const API_BASE_URL = "http://localhost:5000"; // Local development
const API_BASE_URL =
"https://dev.aiparser.ir-bioprocess-poc.awscloud.abbvienet.com"; // Dev environment (via nginx proxy)

// Import the agent service and file utilities
import { agent } from "../../services/agent";
import { extractTextFromFile, cancelProcess } from "../../services/fileUtils";

// Import chat history components and services
import ChatSidebar, { ChatSidebarRef } from "../../components/ChatSidebar";

// Dynamic imports for heavy components - loaded only when needed
const PDFPanel = dynamic(() => import("../../components/PDFPanel"), {
  ssr: false,
  loading: () => (
    <div className="flex items-center justify-center h-full bg-gradient-to-br from-gray-50 to-blue-50">
      <div className="text-center">
        <div className="w-10 h-10 border-4 border-cyan-200 border-t-cyan-500 rounded-full animate-spin mx-auto mb-2"></div>
        <p className="text-gray-500 text-sm">Loading PDF viewer...</p>
      </div>
    </div>
  )
});
const SchemaPanel = dynamic(() => import("../../components/schemas/SchemaPanel"), {
  ssr: false
});
const PDFPanelTest = dynamic(() => import("../../components/PDFPanelTest"), {
  ssr: false
});
import {
  getChatDetails,
  sendChatMessage,
  saveAssistantMessage,
  ChatMessage,
  createChat,
  getUserChats,
  addDocumentToChat,
} from "../../services/chatHistory";

// Reference type for bounding box data
type PageReference = {
  page: number;
  bbox: { left: number; top: number; width: number; height: number; right?: number; bottom?: number };
  cell_id: string;
  text: string;
  row?: number;
  col?: number;
  type?: string;
  highlight_type?: string;  // 'error' | 'info' for Visual Audit
};

type Message = {
  id: string;
  content: string;
  role: "user" | "assistant" | "system";
  timestamp: Date;
  isNew?: boolean;
  isStreaming?: boolean; // For streaming responses (typing effect)
  // For RAG responses with bounding box references
  references?: PageReference[];
  // For COA extraction status messages
  extractionStatus?: {
    processId: string;
    fileName: string;
    enhancedFileName?: string;
    stage: "completed";
    documentType: "coa";
  };
};

// Sanitize HTML to prevent XSS attacks while allowing safe formatting
const sanitizeHtml = (html: string): string =>
  DOMPurify.sanitize(html, {
    ALLOWED_TAGS: ['strong', 'em', 'a', 'br', 'p', 'span', 'div', 'ul', 'ol', 'li', 'code', 'pre', 'b', 'i', 'h1', 'h2', 'h3', 'h4', 'table', 'thead', 'tbody', 'tr', 'th', 'td'],
    ALLOWED_ATTR: ['href', 'target', 'rel', 'class', 'style'],
  });

// Function to render message with formatted links
const renderMessageWithLinks = (
  text: string,
  messageId: string,
  setMessagesCallback?: React.Dispatch<React.SetStateAction<Message[]>>,
) => {
  // Remove action markers from display
  text = text.replace(/\[ACTION:SHOW_COA_UPLOAD\]/g, "");
  text = text.replace(/\[ACTION:SHOW_HBR_UPLOAD\]/g, "");

  // Phase 5: Remove cell/line reference markers from display (they're shown as page buttons instead)
  // Matches [cell:...] and [line:...] patterns like [cell:23:2-4] or [line:5:abc-123]
  text = text.replace(/\s*\[cell:[^\]]+\]/g, "");
  text = text.replace(/\s*\[line:[^\]]+\]/g, "");

  // Process markdown formatting - convert **bold** to HTML
  text = text.replace(
    /\*\*(.*?)\*\*/g,
    '<strong class="font-semibold">$1</strong>',
  );

  // First, let's extract all download links and replace them with special markers
  const downloadLinks: Array<{ text: string; url: string }> = [];
  let linkCounter = 0;

  // Process download section headers
  text = text.replace(
    /### Download Processed Files/g,
    '<div class="download-section-header">📥 Download Processed Files</div>',
  );

  text = text.replace(
    /### Download Sample Template/g,
    '<div class="download-section-header">📄 Download Sample Template</div>',
  );

  // Extract markdown links and replace with placeholders
  text = text.replace(
    /\[([^\]]+)\]\(([^)]+)\)/g,
    (match, linkText, linkUrl) => {
      const isDownloadLink =
        linkUrl.includes("/download") ||
        linkText.includes("Download") ||
        linkText.includes(".xlsx") ||
        linkText.includes(".csv") ||
        linkText.includes(".json") ||
        linkText.includes("Results Excel");
      if (isDownloadLink) {
        const fullUrl = linkUrl.startsWith("http")
          ? linkUrl
          : `${API_BASE_URL}${linkUrl}`;

        const id = `download-link-${messageId}-${linkCounter++}`;
        downloadLinks.push({ text: linkText, url: fullUrl });
        return `<download-placeholder id="${id}"></download-placeholder>`;
      }

      return match;
    },
  );

  // Process direct download buttons
  text = text.replace(
    /<div class="direct-download-button" data-url="([^"]+)" data-filename="([^"]+)">([^<]+)<\/div>/g,
    (match, url, filename, buttonText) => {
      const id = `download-button-${messageId}-${linkCounter++}`;
      downloadLinks.push({ text: buttonText, url });
      return `<download-button-placeholder id="${id}"></download-button-placeholder>`;
    },
  );

  // If no special elements, return text as is
  if (
    !text.includes("<div class=") &&
    !text.includes("<download-placeholder") &&
    !text.includes("<download-button-placeholder") &&
    !text.includes("<strong class=")
  ) {
    return text;
  }

  // Split text by placeholders and other HTML elements
  const parts: React.ReactNode[] = [];
  let currentText = text;
  let partIndex = 0;

  // Process download placeholders
  const downloadPlaceholderRegex =
    /<download-placeholder id="([^"]+)"><\/download-placeholder>/g;
  let match;
  let lastIndex = 0;

  while ((match = downloadPlaceholderRegex.exec(currentText)) !== null) {
    // Add text before the placeholder
    if (match.index > lastIndex) {
      const textBefore = currentText.substring(lastIndex, match.index);
      if (textBefore) {
        parts.push(
          <span
            key={`${messageId}-text-${partIndex++}`}
            dangerouslySetInnerHTML={{ __html: sanitizeHtml(textBefore) }}
          />,
        );
      }
    }

    // Get the download link data
    const placeholderId = match[1];
    const linkIndex = parseInt(placeholderId.split("-").pop() || "0", 10);
    const linkData = downloadLinks[linkIndex];

    if (linkData) {
      // Determine if this is a special Excel link
      const isExcelLink =
        linkData.text.includes("Excel") || linkData.url.includes(".xlsx");
      const isUnifiedExcel =
        linkData.text.includes("Complete Excel Report") ||
        linkData.text.includes("Unified Excel Report");

      // Create icon based on file type
      let icon = "📄";
      if (linkData.text.includes("Excel")) icon = "📊";
      if (linkData.text.includes("CSV")) icon = "📋";
      if (linkData.text.includes("JSON")) icon = "🔍";

      // Add the download link as a button for better visibility and interaction
      parts.push(
        <a
          key={`${messageId}-download-${partIndex++}`}
          href={linkData.url}
          target="_blank"
          rel="noopener noreferrer"
          className={
            isUnifiedExcel
              ? "message-download-unified"
              : "message-download-link"
          }
          onClick={(e) => {
            e.preventDefault();
            console.log(`Downloading file from: ${linkData.url}`);
            window.open(linkData.url, "_blank");
          }}
        >
          <span className="mr-2">{icon}</span>
          {linkData.text}
        </a>,
      );
    }

    lastIndex = match.index + match[0].length;
  }

  // Process download button placeholders
  currentText = lastIndex > 0 ? currentText.substring(lastIndex) : currentText;
  lastIndex = 0;

  const buttonPlaceholderRegex =
    /<download-button-placeholder id="([^"]+)"><\/download-button-placeholder>/g;

  while ((match = buttonPlaceholderRegex.exec(currentText)) !== null) {
    // Add text before the placeholder
    if (match.index > lastIndex) {
      const textBefore = currentText.substring(lastIndex, match.index);
      if (textBefore) {
        parts.push(
          <span
            key={`${messageId}-text-${partIndex++}`}
            dangerouslySetInnerHTML={{ __html: sanitizeHtml(textBefore) }}
          />,
        );
      }
    }

    // Get the download button data
    const placeholderId = match[1];
    const buttonIndex = parseInt(placeholderId.split("-").pop() || "0", 10);
    const buttonData = downloadLinks[buttonIndex];

    if (buttonData) {
      // Add the download button
      parts.push(
        <button
          key={`${messageId}-button-${partIndex++}`}
          className="direct-download-button"
          onClick={() => {
            console.log(`Direct download from: ${buttonData.url}`);
            window.open(buttonData.url, "_blank");
          }}
        >
          <span className="mr-2">📥</span>
          {buttonData.text}
        </button>,
      );
    }

    lastIndex = match.index + match[0].length;
  }

  // Process missing parameter buttons
  const missingParamRegex =
    /<div class="missing-parameter-button" data-session-id="([^"]+)" data-parameter="([^"]+)">([^<]+)<\/div>/g;
  let missingParamMatch;

  while ((missingParamMatch = missingParamRegex.exec(currentText)) !== null) {
    // Add text before the placeholder
    if (missingParamMatch.index > lastIndex) {
      const textBefore = currentText.substring(
        lastIndex,
        missingParamMatch.index,
      );
      if (textBefore) {
        parts.push(
          <span
            key={`${messageId}-text-${partIndex++}`}
            dangerouslySetInnerHTML={{ __html: sanitizeHtml(textBefore) }}
          />,
        );
      }
    }

    const sessionId = missingParamMatch[1];
    const parameter = missingParamMatch[2];
    const buttonText = missingParamMatch[3];

    // Add the missing parameter feedback button
    parts.push(
      <button
        key={`${messageId}-missing-param-${partIndex++}`}
        className="missing-parameter-button bg-amber-500 hover:bg-amber-600 text-white px-3 py-2 rounded-md text-sm transition-colors"
        onClick={async () => {
          console.log(`Requesting feedback for parameter: ${parameter}`);

          // Add user message asking for help
          const userMessage: Message = {
            id: Date.now().toString(),
            content: `I need help finding the parameter: ${parameter}`,
            role: "user",
            timestamp: new Date(),
          };
          setMessagesCallback?.((prev: Message[]) => [...prev, userMessage]);

          try {
            // Import the feedback function
            const { handleHbrParameterFeedback } =
              await import("../../services/fileUtils");

            // Request feedback from the backend
            const feedbackResponse = await handleHbrParameterFeedback(
              sessionId,
              parameter,
              `I need help finding the parameter: ${parameter}`,
            );

            // Add assistant response
            const assistantMessage: Message = {
              id: (Date.now() + 1).toString(),
              content: feedbackResponse,
              role: "assistant",
              timestamp: new Date(),
            };
            setMessagesCallback?.((prev: Message[]) => [
              ...prev,
              assistantMessage,
            ]);
          } catch (error) {
            console.error("Error getting parameter feedback:", error);
            const errorMessage: Message = {
              id: (Date.now() + 1).toString(),
              content: `Sorry, I encountered an error getting feedback for ${parameter}. Please try again.`,
              role: "assistant",
              timestamp: new Date(),
            };
            setMessagesCallback?.((prev: Message[]) => [...prev, errorMessage]);
          }
        }}
      >
        <span className="mr-2">🔍</span>
        {buttonText.replace("🔍 ", "")}
      </button>,
    );

    lastIndex = missingParamMatch.index + missingParamMatch[0].length;
  }

  // Process reprocess parameter buttons
  const reprocessRegex =
    /<div class="reprocess-parameter-button" data-session-id="([^"]+)" data-parameter="([^"]+)" data-recommended-pages="([^"]*)" data-placeholder="([^"]+)">([^<]+)<\/div>/g;
  let reprocessMatch;

  while ((reprocessMatch = reprocessRegex.exec(currentText)) !== null) {
    // Add text before the placeholder
    if (reprocessMatch.index > lastIndex) {
      const textBefore = currentText.substring(lastIndex, reprocessMatch.index);
      if (textBefore) {
        parts.push(
          <span
            key={`${messageId}-text-${partIndex++}`}
            dangerouslySetInnerHTML={{ __html: sanitizeHtml(textBefore) }}
          />,
        );
      }
    }

    const sessionId = reprocessMatch[1];
    const parameter = reprocessMatch[2];
    const recommendedPagesStr = reprocessMatch[3];
    const placeholder = reprocessMatch[4];
    const buttonText = reprocessMatch[5];

    // Add the reprocess parameter button
    parts.push(
      <button
        key={`${messageId}-reprocess-${partIndex++}`}
        className="reprocess-parameter-button bg-blue-500 hover:bg-blue-600 text-white px-3 py-2 rounded-md text-sm transition-colors"
        onClick={async () => {
          const userHint = prompt(placeholder);
          if (!userHint || userHint.trim() === "") {
            return;
          }

          console.log(
            `Reprocessing parameter: ${parameter} with hint: ${userHint}`,
          );

          // Add user message with the hint
          const userMessage: Message = {
            id: Date.now().toString(),
            content: `Please search for ${parameter} with this hint: "${userHint}"`,
            role: "user",
            timestamp: new Date(),
          };
          setMessagesCallback?.((prev: Message[]) => [...prev, userMessage]);

          try {
            const recommendedPages = recommendedPagesStr
              ? recommendedPagesStr.split(",").map((p) => parseInt(p.trim()))
              : [];

            // Import the reprocess function
            const { handleHbrParameterReprocess } =
              await import("../../services/fileUtils");

            // Request reprocessing from the backend
            const reprocessResponse = await handleHbrParameterReprocess(
              sessionId,
              parameter,
              userHint,
              recommendedPages,
            );

            // Add assistant response
            const assistantMessage: Message = {
              id: (Date.now() + 1).toString(),
              content: reprocessResponse,
              role: "assistant",
              timestamp: new Date(),
            };
            setMessagesCallback?.((prev: Message[]) => [
              ...prev,
              assistantMessage,
            ]);
          } catch (error) {
            console.error("Error reprocessing parameter:", error);
            const errorMessage: Message = {
              id: (Date.now() + 1).toString(),
              content: `Sorry, I encountered an error reprocessing ${parameter}. Please try again.`,
              role: "assistant",
              timestamp: new Date(),
            };
            setMessagesCallback?.((prev: Message[]) => [...prev, errorMessage]);
          }
        }}
      >
        <span className="mr-2">🔄</span>
        {buttonText.replace("🔄 ", "")}
      </button>,
    );

    lastIndex = reprocessMatch.index + reprocessMatch[0].length;
  }

  // Add remaining text
  if (lastIndex < currentText.length) {
    const remainingText = currentText.substring(lastIndex);
    if (remainingText) {
      parts.push(
        <span
          key={`${messageId}-text-${partIndex++}`}
          dangerouslySetInnerHTML={{ __html: sanitizeHtml(remainingText) }}
        />,
      );
    }
  }

  // Process any standard links in the remaining text
  const remainingParts = parts.map((part, index) => {
    if (React.isValidElement(part) && part.props.dangerouslySetInnerHTML) {
      const html = part.props.dangerouslySetInnerHTML.__html;

      // Process standard markdown links
      const processedHtml = html.replace(
        /\[([^\]]+)\]\(([^)]+)\)/g,
        (match: string, linkText: string, linkUrl: string) => {
          const fullUrl = linkUrl.startsWith("http")
            ? linkUrl
            : `${API_BASE_URL}${linkUrl}`;
          return `<a href="${fullUrl}" target="_blank" rel="noopener noreferrer" class="text-blue-500 hover:underline">${linkText}</a>`;
        },
      );

      return (
        <span
          key={part.key}
          dangerouslySetInnerHTML={{ __html: sanitizeHtml(processedHtml) }}
        />
      );
    }
    return part;
  });

  return <>{remainingParts}</>;
};

/**
 * Page Reference Buttons Component
 * Renders clickable buttons for each unique page in the references
 * Each button stores bbox data for future PDF highlighting
 */
const PageReferenceButtons = React.memo(({
  references,
  onPageClick
}: {
  references: PageReference[];
  onPageClick?: (page: number, refs: PageReference[]) => void;
}) => {
  if (!references || references.length === 0) return null;

  // Group references by page number
  const pageGroups = references.reduce((acc, ref) => {
    const page = ref.page;
    if (!acc[page]) {
      acc[page] = [];
    }
    acc[page].push(ref);
    return acc;
  }, {} as Record<number, PageReference[]>);

  // Sort pages numerically
  const sortedPages = Object.keys(pageGroups)
    .map(Number)
    .sort((a, b) => a - b);

  const handleClick = (page: number) => {
    const pageRefs = pageGroups[page];
    if (onPageClick) {
      onPageClick(page, pageRefs);
    }
  };

  return (
    <div className="flex flex-wrap gap-2 mt-3 pt-3 border-t border-gray-200">
      <span className="text-xs text-gray-500 self-center mr-1">Sources:</span>
      {sortedPages.map((page) => {
        const pageRefs = pageGroups[page];
        const refCount = pageRefs.length;
        return (
          <button
            key={`page-${page}`}
            onClick={() => handleClick(page)}
            className="inline-flex items-center gap-1 px-3 py-1.5 text-xs font-medium
                       bg-gradient-to-r from-cyan-50 to-blue-50
                       text-cyan-700 border border-cyan-200
                       rounded-full hover:from-cyan-100 hover:to-blue-100
                       hover:border-cyan-300 hover:shadow-sm
                       transition-all duration-200 group"
            title={`${refCount} reference${refCount > 1 ? 's' : ''} on page ${page}. Click to view.`}
          >
            <svg
              className="w-3 h-3 text-cyan-500 group-hover:text-cyan-600"
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"
              />
            </svg>
            Page {page}
            {refCount > 1 && (
              <span className="bg-cyan-200 text-cyan-800 px-1.5 py-0.5 rounded-full text-[10px] font-semibold">
                {refCount}
              </span>
            )}
          </button>
        );
      })}
    </div>
  );
});
PageReferenceButtons.displayName = 'PageReferenceButtons';

/**
 * Loading indicator component
 */
const LoadingDots = React.memo(() => (
  <div className="flex space-x-1 items-center">
    <div
      className="w-2 h-2 bg-blue-500 rounded-full animate-bounce"
      style={{ animationDelay: "0ms" }}
    ></div>
    <div
      className="w-2 h-2 bg-blue-500 rounded-full animate-bounce"
      style={{ animationDelay: "150ms" }}
    ></div>
    <div
      className="w-2 h-2 bg-blue-500 rounded-full animate-bounce"
      style={{ animationDelay: "300ms" }}
    ></div>
  </div>
));
LoadingDots.displayName = 'LoadingDots';

/**
 * Visual Audit Analysis Block Component
 * Shows a masked/blurred background with real-time logs during Visual Audit processing
 */
const VisualAuditAnalysisBlock = ({
  logs,
  stage,
  query
}: {
  logs: string[];
  stage: 'searching' | 'analyzing' | 'extracting' | 'verifying' | 'complete';
  query: string;
}) => {
  const logsEndRef = useRef<HTMLDivElement>(null);

  // Auto-scroll logs to bottom when new logs arrive
  useEffect(() => {
    if (logsEndRef.current) {
      logsEndRef.current.scrollIntoView({ behavior: 'smooth' });
    }
  }, [logs]);

  // Calculate percentage based on stage - 5 stages for smoother progression
  const stageProgress: Record<string, number> = {
    searching: 15,
    analyzing: 35,
    extracting: 60,
    verifying: 85,
    complete: 100
  };

  const stageInfo: Record<string, { icon: string; text: string; color: string }> = {
    searching: { icon: '🔍', text: 'Searching document...', color: 'text-cyan-400' },
    analyzing: { icon: '🤖', text: 'Analyzing content...', color: 'text-cyan-400' },
    extracting: { icon: '📊', text: 'Extracting data...', color: 'text-cyan-400' },
    verifying: { icon: '✓', text: 'Verifying results...', color: 'text-cyan-400' },
    complete: { icon: '✅', text: 'Analysis complete', color: 'text-green-400' }
  };

  const currentStage = stageInfo[stage];

  return (
    <div className="w-full max-w-2xl animate-fadeIn">
      {/* Main container with dark theme and blur effect */}
      <div className="relative rounded-xl overflow-hidden border border-gray-700/50 shadow-2xl">
        {/* Blurred/masked background */}
        <div className="absolute inset-0 bg-gray-900/95 backdrop-blur-sm"></div>

        {/* Animated gradient overlay */}
        <div className="absolute inset-0 bg-gradient-to-br from-cyan-900/20 via-transparent to-cyan-800/20 animate-pulse"></div>

        {/* Content */}
        <div className="relative z-10 p-4">
          {/* Header */}
          <div className="flex items-center justify-between mb-3 pb-3 border-b border-gray-700/50">
            <div className="flex items-center gap-2">
              <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-cyan-400 to-cyan-600 flex items-center justify-center">
                <span className="text-white text-sm">🔬</span>
              </div>
              <div>
                <h3 className="text-sm font-semibold text-white">Visual Audit Analysis</h3>
                <p className="text-xs text-gray-400 truncate max-w-[200px]">{query}</p>
              </div>
            </div>
            <div className={`flex items-center gap-1.5 ${currentStage.color}`}>
              <span className="text-sm font-bold">{stageProgress[stage]}%</span>
              <span className="text-xs font-medium">{currentStage.text}</span>
              {stage !== 'complete' && (
                <div className="w-3 h-3 border-2 border-current border-t-transparent rounded-full animate-spin ml-1"></div>
              )}
            </div>
          </div>

          {/* Logs container - terminal style */}
          <div className="bg-black/60 rounded-lg p-3 font-mono text-xs max-h-[200px] overflow-y-auto scrollbar-thin scrollbar-thumb-gray-700 scrollbar-track-transparent">
            {logs.length === 0 ? (
              <div className="text-gray-500 flex items-center gap-2">
                <span className="animate-pulse">▶</span>
                <span>Initializing analysis pipeline...</span>
              </div>
            ) : (
              logs.map((log, index) => (
                <div
                  key={index}
                  className="flex items-start gap-2 mb-1 animate-slideInUp"
                  style={{ animationDelay: `${index * 50}ms` }}
                >
                  <span className="text-gray-600 select-none">{String(index + 1).padStart(2, '0')}</span>
                  <span className={`${
                    log.startsWith('[ERROR]') ? 'text-red-400' :
                    log.startsWith('[SUCCESS]') ? 'text-green-400' :
                    log.startsWith('[INFO]') ? 'text-cyan-400' :
                    log.startsWith('[ANALYZE]') ? 'text-cyan-400' :
                    log.startsWith('[SEARCH]') ? 'text-cyan-400' :
                    log.startsWith('[EXTRACT]') ? 'text-cyan-400' :
                    'text-gray-300'
                  }`}>{log}</span>
                </div>
              ))
            )}
            <div ref={logsEndRef} />
            {/* Blinking cursor */}
            {stage !== 'complete' && (
              <div className="flex items-center gap-2 mt-1">
                <span className="text-gray-600 select-none">{String(logs.length + 1).padStart(2, '0')}</span>
                <span className="w-2 h-4 bg-cyan-400 animate-pulse"></span>
              </div>
            )}
          </div>

          {/* Progress bar */}
          <div className="mt-3 h-1.5 bg-gray-800 rounded-full overflow-hidden">
            <div
              className={`h-full rounded-full transition-all duration-500 ${
                stage === 'complete' ? 'w-full bg-green-500' : 'bg-gradient-to-r from-cyan-400 to-cyan-600'
              }`}
              style={{ width: `${stageProgress[stage]}%` }}
            ></div>
          </div>
        </div>
      </div>
    </div>
  );
};

/**
 * Dashboard page component
 * Handles chat interface and file uploads
 */
export default function Dashboard() {
  const [user, setUser] = useState<{ username: string; email: string } | null>(
    null,
  );
  const [loading, setLoading] = useState(true);
  const [messages, setMessages] = useState<Message[]>([]);
  const [inputMessage, setInputMessage] = useState("");
  const [isUploading, setIsUploading] = useState(false);
  const [isFirstVisit, setIsFirstVisit] = useState(true);
  const [isThinking, setIsThinking] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [showWelcomeOverlay, setShowWelcomeOverlay] = useState(false);
  const [userScrolling, setUserScrolling] = useState(false);
  const [hasNewMessages, setHasNewMessages] = useState(false);
  const [isChatLoading, setIsChatLoading] = useState(false); // Loading state during chat switch
  const [lastUserMessageTime, setLastUserMessageTime] = useState(Date.now());
  const [showUploadUI, setShowUploadUI] = useState(false);
  const [uploadProgress, setUploadProgress] = useState(0);
  const [uploadStage, setUploadStage] = useState<
    "uploading" | "extracting" | "analyzing"
  >("uploading");
  const [processingState, setProcessingState] = useState<{
    active: boolean;
    stage: "uploading" | "extracting" | "analyzing" | "completed";
    fileName: string;
    progress: number;
    detailedStage?: string;
    documentType?: "coa" | "hbr_pdf" | "hbr_excel" | null;
    fileSize?: number;
  }>({
    active: false,
    stage: "uploading",
    fileName: "",
    progress: 0,
    detailedStage: "",
    documentType: null,
    fileSize: 0,
  });
  const [responseAdded, setResponseAdded] = useState(false);

  // COA Chat Panel state
  const [showCoAChat, setShowCoAChat] = useState(false);
  const [coaProcessId, setCoaProcessId] = useState<string | null>(null);
  const [coaChatMessages, setCoaChatMessages] = useState<
    Array<{
      role: "user" | "assistant";
      content: string;
      timestamp: Date;
      isStreaming?: boolean;
    }>
  >([]);
  const [coaChatLoading, setCoaChatLoading] = useState(false);

  // Phase 5: PDF Viewer Panel state
  const [showPDFPanel, setShowPDFPanel] = useState(false);
  const [showSchemaPanel, setShowSchemaPanel] = useState(false);
  const [pdfHighlights, setPdfHighlights] = useState<PageReference[]>([]);
  const [pdfInitialPage, setPdfInitialPage] = useState(1);
  const [activeDocumentName, setActiveDocumentName] = useState<string>("");
  const activeDocumentNameRef = useRef<string>("");  // Ref for Visual Audit callback
  const [pdfPanelWidth, setPdfPanelWidth] = useState(50); // Panel width in vw

  // Preload PDFPanel component when document is available for faster opening
  useEffect(() => {
    if (coaProcessId) {
      import("../../components/PDFPanel");
    }
  }, [coaProcessId]);

  // TEST MODE: For debugging bbox positioning
  const [showTestPanel, setShowTestPanel] = useState(false);

  // HBR-specific state
  const [currentDocumentType, setCurrentDocumentType] = useState<
    "coa" | "hbr" | "hbr_multiagent" | null
  >(null);
  const [hbrProcessId, setHbrProcessId] = useState<string | null>(null);
  const [showHbrUploadUI, setShowHbrUploadUI] = useState(false);
  const [hbrUploadStage, setHbrUploadStage] = useState<"pdf" | "excel">("pdf");
  const [hbrSessionId, setHbrSessionId] = useState<string | null>(null);
  const [currentProcessId, setCurrentProcessId] = useState<string | null>(null);
  const [canCancel, setCanCancel] = useState(false);
  const [userCancelled, setUserCancelled] = useState(false);

  // Visual Audit Analysis state - shows log-style block while processing
  const [visualAuditState, setVisualAuditState] = useState<{
    active: boolean;
    logs: string[];
    stage: 'searching' | 'analyzing' | 'extracting' | 'verifying' | 'complete';
    query: string;
    pages: number[];  // Target pages being analyzed
  }>({
    active: false,
    logs: [],
    stage: 'searching',
    query: '',
    pages: [],
  });

  // Phase 4: Pending document to save to DB when chat is created
  // This is needed because file upload can happen BEFORE chat exists
  const [pendingDocumentSave, setPendingDocumentSave] = useState<{
    process_id: string;
    document_name: string;
    file_size: number;
    document_type: string;
  } | null>(null);

  // Smooth progress animation states
  const [animatedProgress, setAnimatedProgress] = useState(0);
  const progressAnimationRef = useRef<NodeJS.Timeout | null>(null);

  // Capabilities modal state
  const [showCapabilitiesModal, setShowCapabilitiesModal] = useState(false);

  // AbbVie AI Guidelines modal state
  const [showAIGuidelinesModal, setShowAIGuidelinesModal] = useState(false);

  // User dropdown state
  const [showUserDropdown, setShowUserDropdown] = useState(false);

  // Feedback modal states
  const [showFeedbackModal, setShowFeedbackModal] = useState(false);
  const [feedbackRating, setFeedbackRating] = useState<
    "great" | "okay" | "poor" | null
  >(null);
  const [reportErrors, setReportErrors] = useState(false);
  const [errorDetails, setErrorDetails] = useState("");
  const [additionalComments, setAdditionalComments] = useState("");
  const [showSuccessToast, setShowSuccessToast] = useState(false);
  const targetProgressRef = useRef(0);

  // Chat History Sidebar state
  const [sidebarOpen, setSidebarOpen] = useState(() => {
    // Restore sidebar state from localStorage (default to true/open)
    if (typeof window !== "undefined") {
      const saved = localStorage.getItem("sidebarOpen");
      return saved !== null ? saved === "true" : true; // Default open
    }
    return true;
  });
  const [currentChatId, setCurrentChatId] = useState<string | null>(null);

  const messagesEndRef = useRef<HTMLDivElement>(null);
  const chatContainerRef = useRef<HTMLDivElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const scrollTimeoutRef = useRef<NodeJS.Timeout | null>(null);
  const chatSidebarRef = useRef<ChatSidebarRef>(null);
  const isSwitchingChatRef = useRef<boolean>(false); // Flag to disable scroll handler during chat switch
  const isAutoScrollingRef = useRef<boolean>(false); // Flag to prevent scroll detection during programmatic scroll
  const router = useRouter();

  // Memoized computations - only recalculate when messages change
  const hasNewMessagesInList = useMemo(() => messages.some((msg) => msg.isNew), [messages]);
  const hasStreamingMessage = useMemo(() => messages.some((msg) => msg.isStreaming), [messages]);
  const newMessagesCount = useMemo(() => messages.filter((msg) => msg.isNew).length, [messages]);

  // Message virtualizer for performance with large chat histories
  const messageVirtualizer = useVirtualizer({
    count: messages.length,
    getScrollElement: () => chatContainerRef.current,
    estimateSize: () => 120, // Estimated average message height
    overscan: 5, // Render 5 extra items above/below viewport
  });

  // Helper function to scroll chat to bottom (newest messages)
  // Use direct DOM scroll for reliability during dynamic updates
  const scrollChatToBottom = useCallback((behavior: "smooth" | "auto" = "smooth") => {
    if (chatContainerRef.current) {
      isAutoScrollingRef.current = true;
      const container = chatContainerRef.current;
      // Scroll to the maximum scroll position (bottom)
      container.scrollTo({
        top: container.scrollHeight,
        behavior: behavior
      });
      // Reset flag after scroll completes
      setTimeout(() => {
        isAutoScrollingRef.current = false;
      }, behavior === "smooth" ? 500 : 100);
    }
  }, []);

  // Scroll to bottom on initial load and when messages change (after chat switch)
  const prevMessagesLengthRef = useRef(0);
  useEffect(() => {
    // When messages are first loaded or significantly changed (chat switch)
    if (messages.length > 0 && prevMessagesLengthRef.current === 0) {
      // Initial load - scroll to bottom without animation after virtualizer renders
      requestAnimationFrame(() => {
        setTimeout(() => {
          scrollChatToBottom("auto");
        }, 50);
      });
    }
    prevMessagesLengthRef.current = messages.length;
  }, [messages.length, scrollChatToBottom]);

  // Focus input on load
  useEffect(() => {
    if (!loading && inputRef.current) {
      inputRef.current.focus();
    }
  }, [loading]);

  // Keep activeDocumentNameRef in sync with state (for use in callbacks)
  useEffect(() => {
    activeDocumentNameRef.current = activeDocumentName;
  }, [activeDocumentName]);

  // Set up Visual Audit callback on agent for real-time progress updates
  // Backend detects Visual Audit intent and signals frontend via SSE
  useEffect(() => {
    const handleVisualAuditUpdate = (update: {
      type: 'start' | 'log' | 'stage' | 'complete';
      query?: string;
      log?: string;
      stage?: 'searching' | 'analyzing' | 'extracting' | 'complete';
      pages?: number[];
    }) => {
      switch (update.type) {
        case 'start':
          const targetPages = update.pages || [];
          setVisualAuditState({
            active: true,
            logs: [],
            stage: update.stage || 'searching',
            query: update.query || '',
            pages: targetPages,
          });
          // Preload PDF before opening panel to reduce load time
          // This starts fetching the PDF in background immediately
          const currentDocName = activeDocumentNameRef.current;
          if (targetPages.length > 0 && currentDocName) {
            const sanitizeName = (name: string) => {
              let n = name.replace(/\.pdf$/i, '');
              n = n.replace(/\s+/g, '_').replace(/[()]/g, '').replace(/[^a-zA-Z0-9_\-]/g, '_');
              n = n.replace(/_+/g, '_').replace(/_+$/, '');
              return n;
            };
            const pdfUrl = `${API_BASE_URL}/temp/${encodeURIComponent(sanitizeName(currentDocName))}.pdf`;

            // Preload PDF using link prefetch (browser will cache it)
            const link = document.createElement('link');
            link.rel = 'prefetch';
            link.href = pdfUrl;
            link.as = 'fetch';
            document.head.appendChild(link);

            // Also fetch directly to warm up the connection
            fetch(pdfUrl, { method: 'GET', cache: 'force-cache' }).catch(() => {});

            console.log("[Visual Audit] Preloading PDF:", pdfUrl);
          }
          // Open PDF panel immediately with scanning mode if we have pages
          if (targetPages.length > 0) {
            console.log("[Visual Audit] Opening PDF panel with scanning pages:", targetPages);
            setPdfInitialPage(targetPages[0]);  // Go to first target page
            setPdfHighlights([]);  // Clear existing highlights, will show scanning animation
            setShowPDFPanel(true);
          }
          break;
        case 'stage':
          if (update.stage) {
            setVisualAuditState(prev => ({
              ...prev,
              stage: update.stage!,
            }));
          }
          break;
        case 'log':
          // Logs were for testing - no longer needed, skip state updates
          break;
        case 'complete':
          // Keep visible briefly then clear
          setVisualAuditState(prev => ({
            ...prev,
            stage: 'complete',
          }));
          setTimeout(() => {
            setVisualAuditState({
              active: false,
              logs: [],
              stage: 'searching',
              query: '',
              pages: [],
            });
          }, 500);
          break;
      }
    };

    agent.setVisualAuditCallback(handleVisualAuditUpdate);

    return () => {
      agent.setVisualAuditCallback(null);
    };
  }, []);

  // Handle scroll events in the chat container
  // With normal scroll (no flex-col-reverse):
  // - scrollTop = 0 means at TOP (oldest messages)
  // - scrollTop + clientHeight = scrollHeight means at BOTTOM (newest messages)
  useEffect(() => {
    // Wait for loading to complete so the ref is attached
    if (loading) return;

    const chatContainer = chatContainerRef.current;
    if (!chatContainer) {
      return;
    }

    const handleScroll = () => {
      // Skip scroll handling during chat switching or programmatic scrolling
      if (isSwitchingChatRef.current || isAutoScrollingRef.current) {
        return;
      }

      const { scrollTop, scrollHeight, clientHeight } = chatContainer;

      // Check if content is scrollable at all
      const isScrollable = scrollHeight > clientHeight;
      if (!isScrollable) {
        setUserScrolling(false);
        setHasNewMessages(false);
        return;
      }

      // With normal scroll:
      // At bottom when scrollTop + clientHeight >= scrollHeight - threshold
      const distanceFromBottom = scrollHeight - scrollTop - clientHeight;
      const isAtBottom = distanceFromBottom < 100; // 100px threshold for more tolerance

      if (!isAtBottom) {
        setUserScrolling(true);
      } else {
        setUserScrolling(false);
        setHasNewMessages(false);
      }
    };

    chatContainer.addEventListener("scroll", handleScroll);

    return () => {
      chatContainer.removeEventListener("scroll", handleScroll);
    };
  }, [loading]); // Re-run when loading changes

  // Create a separate effect for auto-scrolling for new messages
  useEffect(() => {
    // Don't auto-scroll if switching chats or user is viewing history
    if (isSwitchingChatRef.current || userScrolling) {
      return;
    }

    // Auto-scroll when new messages arrive or when streaming (using memoized values)
    if (hasNewMessagesInList || hasStreamingMessage) {
      // Use requestAnimationFrame to ensure DOM is updated
      requestAnimationFrame(() => {
        if (!isSwitchingChatRef.current && !userScrolling) {
          scrollChatToBottom("auto");
        }
      });
    }
  }, [hasNewMessagesInList, hasStreamingMessage, userScrolling, scrollChatToBottom]);

  // Separate effect just for marking messages as seen
  useEffect(() => {
    // Skip during chat switching
    if (isSwitchingChatRef.current) {
      return;
    }

    // Check if there are any new messages when the user is scrolling (using memoized value)
    if (userScrolling && hasNewMessagesInList) {
      setHasNewMessages(true);
    }

    // Mark new messages as seen after they appear (only if not scrolling)
    if (!userScrolling) {
      const timer = setTimeout(() => {
        // Double-check we're not switching chats
        if (!isSwitchingChatRef.current) {
          setMessages((prev) =>
            prev.map((msg) => (msg.isNew ? { ...msg, isNew: false } : msg)),
          );
          setHasNewMessages(false);
        }
      }, 300);

      return () => clearTimeout(timer);
    }
  }, [hasNewMessagesInList, userScrolling]);

  // Auto-scroll when processing state becomes active
  useEffect(() => {
    if (processingState.active) {
      // Auto-scroll to show the processing block
      setTimeout(() => {
        scrollChatToBottom();
        setUserScrolling(false);
      }, 200); // Small delay to ensure processing block is rendered
    }
  }, [processingState.active]);

  // Function to manually scroll to bottom (called by scroll-to-bottom button)
  const scrollToBottom = () => {
    scrollChatToBottom();

    // Only after explicit user action, we can reset this
    setUserScrolling(false);
    setHasNewMessages(false);

    // Mark all messages as seen
    setMessages((prev) =>
      prev.map((msg) => (msg.isNew ? { ...msg, isNew: false } : msg)),
    );
  };

  // Show welcome overlay on first visit but no chat messages
  useEffect(() => {
    const hasVisitedBefore = localStorage.getItem("hasVisitedDashboard");

    if (
      !loading &&
      user &&
      (!hasVisitedBefore || hasVisitedBefore === "false")
    ) {
      // Show welcome overlay
      setShowWelcomeOverlay(true);

      // Hide overlay after 2 seconds and mark as visited
      setTimeout(() => {
        setShowWelcomeOverlay(false);
        localStorage.setItem("hasVisitedDashboard", "true");
        setIsFirstVisit(false);
      }, 2000);
    } else {
      setIsFirstVisit(false);
    }
  }, [loading, user]);

  useEffect(() => {
    const checkAuth = async () => {
      const startTime = Date.now();

      try {
        const res = await fetch(`${API_BASE_URL}/api/check-auth`, {
          method: "GET",
          credentials: "include",
        });

        if (!res.ok) {
          router.push("/login");
          return;
        }

        const data = await res.json();

        // Handle both response formats for better compatibility
        if (data.authenticated && data.username) {
          // New format: { authenticated: true, username: "...", email: "..." }
          setUser({
            username: data.username,
            email: data.email || "",
          });
        } else if (data.username) {
          // Old format: { username: "...", email: "..." }
          setUser(data);
        } else {
          // Not authenticated
          router.push("/login");
          return;
        }

        // Remove the automatic welcome message
        // The welcome message will only appear when user says "hi" or similar
      } catch (error) {
        console.error("Auth check error:", error);
        router.push("/login");
      } finally {
        // Show UI immediately when auth completes - no artificial delay
        setLoading(false);
      }
    };

    checkAuth();
  }, [router]);

  // Initialize chat on page load - restore last viewed chat if user was on one
  // Otherwise show fresh page (like ChatGPT/Claude behavior)
  useEffect(() => {
    const initializeChat = async () => {
      if (!user || loading || currentChatId) return; // Don't run if not authenticated or already have a chat

      try {
        // Check if user was viewing a specific chat before (for page reload)
        const savedChatId = localStorage.getItem("currentChatId");

        if (savedChatId) {
          // Show loading spinner while restoring chat
          setIsChatLoading(true);

          // User was on a chat - try to restore it
          const chats = await getUserChats();
          const chatExists = chats.find((c) => c.chat_id === savedChatId);

          if (chatExists) {
            // Load the saved chat
            const details = await getChatDetails(savedChatId);
            setCurrentChatId(savedChatId);

            // Load existing messages (including references for Phase 5 PDF highlighting)
            const loadedMessages: Message[] = details.messages.map(
              (msg: ChatMessage) => ({
                id: msg.message_id,
                content: msg.content,
                role: msg.role as "user" | "assistant" | "system",
                timestamp: new Date(msg.created_at),
                references: msg.references as PageReference[] | undefined,
              }),
            );
            setMessages(loadedMessages);

            // Load conversation history into the agent so it has context
            const agentHistory = details.messages
              .filter(
                (msg: ChatMessage) =>
                  msg.role === "user" || msg.role === "assistant",
              )
              .slice(-30) // Only last 30 messages (matches summarization interval)
              .map((msg: ChatMessage) => ({
                role: msg.role as "user" | "assistant",
                content: msg.content,
              }));

            // Pass summary (if exists) along with recent messages
            const chatSummary = details.chat.summary;
            agent.loadConversationHistory(agentHistory, chatSummary);

            // Phase 4: Restore active COA document for RAG if available
            if (details.documents && details.documents.length > 0) {
              // Find the most recent document with a process_id (highest upload_order)
              const docsWithProcessId = details.documents.filter(
                (d: { process_id?: string; upload_order: number }) =>
                  d.process_id,
              ) as Array<{
                process_id: string;
                document_name: string;
                upload_order: number;
              }>;
              if (docsWithProcessId.length > 0) {
                // Sort by upload_order descending and take the first (most recent)
                const activeDoc = docsWithProcessId.sort(
                  (a, b) => b.upload_order - a.upload_order,
                )[0];
                agent.setActiveCoaDocument(
                  activeDoc.process_id,
                  activeDoc.document_name,
                );
                setCoaProcessId(activeDoc.process_id);
                setActiveDocumentName(activeDoc.document_name); // Phase 5: For PDF panel
              }
            }

            // Hide loading and scroll to bottom
            setIsChatLoading(false);
            setTimeout(() => {
              scrollChatToBottom();
            }, 100);
          } else {
            // Saved chat no longer exists - clear it and show fresh page
            localStorage.removeItem("currentChatId");
            agent.resetConversation();
            setIsChatLoading(false);
          }
        } else {
          // No saved chat - show fresh page (don't create a chat yet)
          // Chat will be created when user sends first message (in handleSendMessage)
          agent.resetConversation();
          // Clear any stale COA document from previous session
          agent.clearActiveCoaDocument();
          setCoaProcessId(null);
        }
      } catch (error) {
        console.error("Failed to initialize chat:", error);
        // On error, just show fresh page
        localStorage.removeItem("currentChatId");
        agent.resetConversation();
        // Clear any stale COA document
        agent.clearActiveCoaDocument();
        setCoaProcessId(null);
        setIsChatLoading(false);
      }
    };

    initializeChat();
  }, [user, loading]);

  const handleLogout = async () => {
    try {
      await fetch(`${API_BASE_URL}/api/logout`, {
        method: "POST",
        credentials: "include",
      });

      // Clear the messages
      setMessages([]);

      // Reset the agent conversation
      agent.resetConversation();

      // Reset the first visit flag so welcome overlay shows again
      localStorage.setItem("hasVisitedDashboard", "false");

      // Redirect to login page
      router.push("/login");
    } catch (error) {
      console.error("Logout error:", error);
    }
  };

  // Chat History Sidebar handlers
  const handleSelectChat = useCallback(async (chatId: string) => {
    // If clicking on the same chat, do nothing - keep scroll position
    if (chatId === currentChatId) {
      return;
    }

    // Set flag to disable scroll handler during chat switch
    isSwitchingChatRef.current = true;
    setIsChatLoading(true); // Show loading state to hide empty state flash

    try {
      // FIRST: Clear messages and reset scroll state
      setUserScrolling(false);
      setHasNewMessages(false);
      setMessages([]); // Clear old messages FIRST to reset scroll

      // Fetch new chat details
      const details = await getChatDetails(chatId);
      setCurrentChatId(chatId);
      localStorage.setItem("currentChatId", chatId);

      // Convert chat messages to local Message format (including references for Phase 5 PDF highlighting)
      const loadedMessages: Message[] = details.messages.map(
        (msg: ChatMessage) => ({
          id: msg.message_id,
          content: msg.content,
          role: msg.role as "user" | "assistant" | "system",
          timestamp: new Date(msg.created_at),
          references: msg.references as PageReference[] | undefined,
        }),
      );

      // Load conversation history into the agent
      const agentHistory = details.messages
        .filter(
          (msg: ChatMessage) => msg.role === "user" || msg.role === "assistant",
        )
        .slice(-30)
        .map((msg: ChatMessage) => ({
          role: msg.role as "user" | "assistant",
          content: msg.content,
        }));

      const chatSummary = details.chat.summary;
      agent.loadConversationHistory(agentHistory, chatSummary);

      // Phase 4: Restore active COA document for RAG if available
      if (details.documents && details.documents.length > 0) {
        // Find the most recent document with a process_id (highest upload_order)
        const docsWithProcessId = details.documents.filter(
          (d: { process_id?: string; upload_order: number }) => d.process_id,
        ) as Array<{
          process_id: string;
          document_name: string;
          upload_order: number;
        }>;
        if (docsWithProcessId.length > 0) {
          // Sort by upload_order descending and take the first (most recent)
          const activeDoc = docsWithProcessId.sort(
            (a, b) => b.upload_order - a.upload_order,
          )[0];
          agent.setActiveCoaDocument(
            activeDoc.process_id,
            activeDoc.document_name,
          );
          setCoaProcessId(activeDoc.process_id);
          setActiveDocumentName(activeDoc.document_name); // Phase 5: For PDF panel
        } else {
          // Clear active document if this chat has no documents with process_id
          agent.clearActiveCoaDocument();
          setCoaProcessId(null);
          setActiveDocumentName(""); // Phase 5: Clear PDF panel document name
        }
      } else {
        // Clear active document if this chat has no documents
        agent.clearActiveCoaDocument();
        setCoaProcessId(null);
      }

      // Set new messages
      setMessages(loadedMessages);
      setIsChatLoading(false); // Hide loading state

      // Re-enable scroll handler after DOM settles
      setTimeout(() => {
        // Scroll to bottom (newest messages) after new content renders
        scrollChatToBottom("auto");
        isSwitchingChatRef.current = false;
      }, 100);
    } catch (error) {
      console.error("Failed to load chat:", error);
      isSwitchingChatRef.current = false;
      setIsChatLoading(false);
    }
  }, [currentChatId]);

  const handleNewChat = useCallback((chatId: string) => {
    // Set flag to disable scroll handler during chat switch
    isSwitchingChatRef.current = true;

    // Empty chatId means "fresh page mode" - don't create chat yet
    // Chat will be created when user sends first message (like ChatGPT/Claude)
    if (chatId) {
      setCurrentChatId(chatId);
      localStorage.setItem("currentChatId", chatId);
    } else {
      setCurrentChatId(null);
      localStorage.removeItem("currentChatId");
    }
    setMessages([]);
    agent.resetConversation();

    // CRITICAL: Clear active COA document when starting new chat
    // This prevents RAG queries from using previous chat's document
    agent.clearActiveCoaDocument();
    setCoaProcessId(null);

    // Reset scroll state when creating new chat
    setUserScrolling(false);
    setHasNewMessages(false);
    // For new chat with no messages, scroll position doesn't matter
    // but we reset it anyway for consistency

    // Re-enable scroll handler after DOM settles
    setTimeout(() => {
      isSwitchingChatRef.current = false;
    }, 150);
    // Sidebar stays open - user can close manually if needed
  }, []);

  // Toggle sidebar and persist state
  const toggleSidebar = useCallback(() => {
    const newState = !sidebarOpen;
    setSidebarOpen(newState);
    localStorage.setItem("sidebarOpen", String(newState));
  }, [sidebarOpen]);

  // Feedback modal handlers
  const handleFeedbackOpen = useCallback(() => {
    setShowFeedbackModal(true);
  }, []);

  const handleFeedbackClose = useCallback(() => {
    setShowFeedbackModal(false);
    // Reset form
    setFeedbackRating(null);
    setReportErrors(false);
    setErrorDetails("");
    setAdditionalComments("");
  }, []);

  const handleFeedbackSubmit = async () => {
    // Power Automate Flow URL
    const POWER_AUTOMATE_FLOW_URL =
      "https://prod-128.westus.logic.azure.com:443/workflows/82b48de7f60d451db00d5df75d21b466/triggers/manual/paths/invoke?api-version=2016-06-01&sp=%2Ftriggers%2Fmanual%2Frun&sv=1.0&sig=1Mz-6qLZUHyp-xROomG0pf8wyr0i7ly3pvsZ1VuehCI";

    // Prepare feedback data
    const feedbackData = {
      user: user?.username || "Unknown",
      email: user?.email || "not.provided@abbvie.com",
      documentType: currentDocumentType || "General",
      rating: feedbackRating || "not-rated",
      ratingEmoji:
        feedbackRating === "great"
          ? "😊"
          : feedbackRating === "poor"
            ? "😞"
            : "😐",
      hasErrors: reportErrors || false,
      errorDetails: errorDetails || "No errors reported",
      comments: additionalComments || "No additional comments",
      timestamp: new Date().toISOString(),
      sessionId: hbrSessionId || "N/A",
      environment: window.location.hostname,
      appName: "AI Document Parser",
    };

    console.log("Sending feedback to Power Automate:", feedbackData);

    try {
      // Send to Power Automate
      const response = await fetch(POWER_AUTOMATE_FLOW_URL, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify(feedbackData),
      });

      // Power Automate returns 202 Accepted
      if (response.ok || response.status === 202) {
        console.log("✅ Feedback sent successfully to Power Automate");

        // Show success toast
        setShowSuccessToast(true);

        // Close modal and reset form after 2 seconds
        setTimeout(() => {
          setShowFeedbackModal(false);
          setShowSuccessToast(false);
          // Reset form
          setFeedbackRating(null);
          setReportErrors(false);
          setErrorDetails("");
          setAdditionalComments("");
        }, 2000);
      } else {
        throw new Error(`Flow returned status: ${response.status}`);
      }
    } catch (error) {
      console.error("❌ Error sending to Power Automate:", error);

      // FALLBACK: Open email client if Power Automate fails
      const subject = `[Document Parser Feedback] ${feedbackRating?.toUpperCase()} - ${
        currentDocumentType?.toUpperCase() || "General"
      }`;
      const body = `
Feedback from Document Parser
==============================
User: ${user?.username || "Unknown"}
Email: ${user?.email || "N/A"}
Document Type: ${currentDocumentType || "None"}
Rating: ${feedbackRating} ${
        feedbackRating === "great"
          ? "😊"
          : feedbackRating === "poor"
            ? "😞"
            : "😐"
      }
Session ID: ${hbrSessionId || "N/A"}
Timestamp: ${new Date().toLocaleString()}

${reportErrors ? `Errors Reported:\n${errorDetails}\n` : ""}
${additionalComments ? `Comments:\n${additionalComments}\n` : ""}

---
Sent from: ${window.location.hostname}
      `.trim();

      // Open email client as fallback
      window.location.href = `mailto:aidocparser-feedback@abbvie.com?subject=${encodeURIComponent(
        subject,
      )}&body=${encodeURIComponent(body)}`;

      // Still show success (email opened)
      setShowSuccessToast(true);
      setTimeout(() => {
        handleFeedbackClose();
      }, 2000);
    }
  };

  /**
   * Check if a message is related to HBR processing
   */
  const isHbrRelatedMessage = (
    message: string,
    isAssistantResponse: boolean = false,
  ): boolean => {
    const lowerMessage = message.toLowerCase().trim();

    // Keywords related to HBR
    const hbrKeywords = [
      "hbr",
      "health based requirement",
      "health-based requirement",
      "health based requirements",
      "health-based requirements",
      "handwritten batch record",
      "handwritten batch records",
    ];

    // Check if any HBR keyword is in the message
    const containsHbrKeyword = hbrKeywords.some((keyword) =>
      lowerMessage.includes(keyword),
    );

    // For user messages, be more flexible
    if (!isAssistantResponse) {
      // Direct HBR mentions or questions
      return (
        containsHbrKeyword ||
        lowerMessage === "hbr" ||
        lowerMessage.match(/\bhbr\b/) !== null ||
        (lowerMessage.includes("what") && lowerMessage.includes("hbr")) ||
        (lowerMessage.includes("upload") && lowerMessage.includes("hbr"))
      );
    }

    // For assistant responses, check for HBR keywords and upload instructions
    return (
      containsHbrKeyword ||
      (lowerMessage.includes("upload") && lowerMessage.includes("hbr")) ||
      (lowerMessage.includes("upload") &&
        lowerMessage.includes("handwritten batch")) ||
      lowerMessage.includes("upload your handwritten batch records")
    );
  };

  /**
   * Check if a message is related to uploading
   */
  const isUploadRelatedMessage = (
    message: string,
    isAssistantResponse: boolean = false,
  ): boolean => {
    const lowerMessage = message.toLowerCase();

    // Check if it's HBR related first
    if (isHbrRelatedMessage(message, isAssistantResponse)) {
      return false; // We'll handle HBR separately
    }

    // COA related keywords
    const coaKeywords = [
      "coa",
      "certificate of analysis",
      "certificate",
      "analysis",
    ];

    // Check if any COA keyword is in the message
    const containsCoaKeyword = coaKeywords.some((keyword) =>
      lowerMessage.includes(keyword),
    );

    // For user messages, just check for COA keywords
    if (!isAssistantResponse) {
      return (
        containsCoaKeyword ||
        (lowerMessage.includes("analyze") && !lowerMessage.includes("hbr")) ||
        (lowerMessage.includes("test") && !lowerMessage.includes("hbr"))
      );
    }

    // For assistant responses, check for upload instructions or COA keywords
    return (
      containsCoaKeyword ||
      (lowerMessage.includes("upload") && !lowerMessage.includes("hbr")) ||
      (lowerMessage.includes("upload") && lowerMessage.includes("coa"))
    );
  };

  // Removed hardcoded detection - now using Claude AI for intelligent context understanding

  /**
   * Check if a message is a greeting
   */
  const isGreeting = (message: string): boolean => {
    const lowerMessage = message.toLowerCase().trim();
    const greetings = [
      "hi",
      "hello",
      "hey",
      "greetings",
      "good morning",
      "good afternoon",
      "good evening",
      "howdy",
      "hi there",
      "hello there",
    ];

    return greetings.some(
      (greeting) =>
        lowerMessage === greeting || lowerMessage.startsWith(greeting + " "),
    );
  };

  /**
   * Handle cancelling the current process
   */
  const handleCancelProcess = async () => {
    if (currentProcessId) {
      // Safety check: Don't allow cancellation of HBR processes
      const isHBRDocument =
        currentDocumentType === "hbr" ||
        currentDocumentType === "hbr_multiagent";
      if (isHBRDocument) {
        console.log(
          "⚠️ Cancellation disabled for HBR documents (multi-agent processing)",
        );
        return; // Exit early for HBR documents
      }

      console.log("🛑 Cancelling process:", currentProcessId);

      // Mark that user has actively cancelled
      setUserCancelled(true);

      // Immediately update ALL UI state to give instant feedback
      setCanCancel(false);
      setIsThinking(false);
      setIsLoading(false);

      // Reset processing state
      setProcessingState({
        active: false,
        stage: "uploading",
        fileName: "",
        progress: 0,
        detailedStage: "",
      });

      // Reset upload progress state
      setUploadProgress(0);
      setUploadStage("uploading");

      // Check if this is a temporary process ID (before backend responded)
      if (currentProcessId.startsWith("temp-")) {
        console.log(
          "🔄 Cancelling temporary process ID (before backend response)",
        );
        // For temporary IDs, we can't cancel on backend yet, just reset UI
        console.log(
          "⚠️ Early cancellation - backend process hasn't started yet",
        );
      } else {
        // Send cancel request to backend for real process IDs
        const success = await cancelProcess(currentProcessId);
        if (!success) {
          console.warn("⚠️ Backend cancellation failed, but UI already reset");
        }
      }

      setCurrentProcessId(null);
    }
  };

  /**
   * Handle sending a message
   */
  const handleSendMessage = useCallback(async (message: string) => {
    if (!message.trim()) return;

    // Ensure we have a chat ID - create one if needed (like ChatGPT/Claude)
    let activeChatId = currentChatId;
    if (!activeChatId) {
      try {
        const newChat = await createChat();
        activeChatId = newChat.chat_id;
        setCurrentChatId(activeChatId);
        localStorage.setItem("currentChatId", activeChatId); // Save for page reload

        // Immediately refresh sidebar to show the new chat
        chatSidebarRef.current?.refreshChats();

        // Phase 4: Save any pending document that was uploaded BEFORE chat was created
        if (pendingDocumentSave) {
          console.log(
            "[DB] Saving pending document to newly created chat:",
            activeChatId,
          );
          addDocumentToChat(activeChatId, {
            document_id: pendingDocumentSave.process_id,
            document_name: pendingDocumentSave.document_name,
            file_size: pendingDocumentSave.file_size,
            process_id: pendingDocumentSave.process_id,
            document_type: pendingDocumentSave.document_type,
          })
            .then(() => {
              console.log(
                "[DB] Pending document saved to PostgreSQL:",
                pendingDocumentSave.process_id,
                pendingDocumentSave.document_name,
              );
              setPendingDocumentSave(null); // Clear after successful save
            })
            .catch((err) => {
              console.error(
                "[DB] Failed to save pending document to PostgreSQL:",
                err,
              );
            });
        }
      } catch (error) {
        console.error("Failed to create chat:", error);
        // Continue with local-only messages if chat creation fails
      }
    }

    // Add user message to chat
    const userMessage: Message = {
      id: Date.now().toString(),
      content: message,
      role: "user",
      timestamp: new Date(),
      isNew: true, // Mark as new to trigger auto-scroll
    };

    // Reset scroll state BEFORE adding message
    setUserScrolling(false);
    setHasNewMessages(false);

    // Add the message
    setMessages((prev) => [...prev, userMessage]);

    // Force INSTANT scroll to bottom after message is added
    // Wait for React to flush the update, then scroll
    requestAnimationFrame(() => {
      scrollChatToBottom("auto");
      // Backup scroll after DOM settles
      setTimeout(() => {
        scrollChatToBottom("auto");
      }, 100);
    });

    // Save user message to database
    if (activeChatId) {
      try {
        await sendChatMessage(activeChatId, message);

        // Refresh sidebar after a short delay to pick up auto-generated title
        // Backend generates title asynchronously, so we wait ~3 seconds
        setTimeout(() => {
          chatSidebarRef.current?.refreshChats();
        }, 3000);
      } catch (error) {
        console.error("Failed to save user message to database:", error);
      }
    }

    // Update timestamp for user message (for auto-scroll logic)
    setLastUserMessageTime(Date.now());

    // Hide upload UI while waiting for response
    setShowUploadUI(false);
    setShowHbrUploadUI(false);

    // DON'T show loading indicator - we use streaming placeholder instead
    // The streaming message with blinking cursor replaces the loading dots
    setIsLoading(false);

    // Check if the message is a greeting
    const isUserGreeting = isGreeting(message);

    // Let the Claude agent handle all intelligence - no hardcoded detection

    // Create a streaming message placeholder
    const streamingMessageId = (Date.now() + 1).toString();
    const streamingMessage: Message = {
      id: streamingMessageId,
      content: "",
      role: "assistant",
      timestamp: new Date(),
      isStreaming: true,
    };
    setMessages((prev) => [...prev, streamingMessage]);

    // Set up streaming callback to update message in real-time
    agent.setStreamCallback((text: string, done: boolean) => {
      setMessages((prev) => {
        const newMessages = [...prev];
        const streamingIdx = newMessages.findIndex(
          (m) => m.id === streamingMessageId,
        );
        if (streamingIdx !== -1) {
          newMessages[streamingIdx] = {
            ...newMessages[streamingIdx],
            content: text,
            isStreaming: !done,
          };
        }
        return newMessages;
      });

      // Auto-scroll while streaming
      if (!done) {
        scrollChatToBottom();
      }
    });

    // Process the message through the agent
    try {
      const response = await agent.processMessage(message);

      // Clear the stream callback
      agent.setStreamCallback(null);

      // Check for action markers first
      let actionHandled = false;

      if (response.includes("[ACTION:SHOW_HBR_MULTIAGENT_UPLOAD]")) {
        console.log("Agent triggered HBR MULTIAGENT upload action");
        setCurrentDocumentType("hbr_multiagent");
        setHbrUploadStage("pdf");
        setShowHbrUploadUI(true);
        setShowUploadUI(false);
        actionHandled = true;
      } else if (response.includes("[ACTION:SHOW_HBR_UPLOAD]")) {
        console.log("Agent triggered HBR standard upload action");
        setCurrentDocumentType("hbr");
        setHbrUploadStage("pdf");
        setShowHbrUploadUI(true);
        setShowUploadUI(false);
        actionHandled = true;
      }
      // Check for COA upload action
      else if (response.includes("[ACTION:SHOW_COA_UPLOAD]")) {
        setCurrentDocumentType("coa");
        setShowUploadUI(true);
        setShowHbrUploadUI(false);
        actionHandled = true;
      }
      // Check for HBR template download action
      else if (response.includes("[ACTION:SHOW_HBR_TEMPLATE]")) {
        // Trigger template download
        handleHbrTemplateDownload();
        actionHandled = true;
      }

      // Clean the response of action markers
      const cleanResponse = response
        .replace(/\[ACTION:SHOW_HBR_MULTIAGENT_UPLOAD\]/g, "")
        .replace(/\[ACTION:SHOW_HBR_UPLOAD\]/g, "")
        .replace(/\[ACTION:SHOW_COA_UPLOAD\]/g, "")
        .replace(/\[ACTION:SHOW_HBR_TEMPLATE\]/g, "")
        .trim();

      // Update the streaming message with final cleaned content
      if (cleanResponse) {
        // Filter out cancellation-related messages
        const lowerResponse = cleanResponse.toLowerCase();
        if (
          lowerResponse.includes("cancelled by user") ||
          lowerResponse.includes("process cancelled")
        ) {
          console.log("Filtering out cancellation message from agent response");
          // Remove the streaming message since we're filtering it out
          setMessages((prev) =>
            prev.filter((m) => m.id !== streamingMessageId),
          );
        } else {
          // Get references from the last RAG response (Phase 5: for bbox highlighting)
          const ragResponse = agent.getLastRAGResponse();
          const references = ragResponse?.references || [];

          // Update the message with clean content, references, and mark as not streaming
          setMessages((prev) => {
            const newMessages = [...prev];
            const streamingIdx = newMessages.findIndex(
              (m) => m.id === streamingMessageId,
            );
            if (streamingIdx !== -1) {
              newMessages[streamingIdx] = {
                ...newMessages[streamingIdx],
                content: cleanResponse,
                isStreaming: false,
                references: references.length > 0 ? references : undefined,
              };
            }
            return newMessages;
          });

          // Save assistant message to database and get current summary
          if (activeChatId) {
            try {
              const saveResult = await saveAssistantMessage(
                activeChatId,
                cleanResponse,
                undefined,  // documentId
                references.length > 0 ? references : undefined  // Phase 5: Pass references for DB storage
              );
              console.log(
                "Save result from backend:",
                JSON.stringify(saveResult, null, 2),
              );
              if (references.length > 0) {
                console.log(`Saved ${references.length} references for PDF highlighting`);
              }

              // If there's a summary, update the agent's context
              if (saveResult.current_summary) {
                console.log(
                  "Updating agent with current summary:",
                  saveResult.current_summary,
                );
                agent.updateSummary(saveResult.current_summary);
              } else {
                console.log(
                  "No summary returned from backend (summary may not exist yet)",
                );
              }
            } catch (error) {
              console.error(
                "Failed to save assistant message to database:",
                error,
              );
            }
          }

          // ALWAYS scroll to bottom after AI response
          setTimeout(() => {
            scrollChatToBottom();
            setUserScrolling(false);
          }, 100);
        }
      } else {
        // No content - remove the streaming placeholder
        setMessages((prev) => prev.filter((m) => m.id !== streamingMessageId));
      }

      // Additional intelligence for template requests (fallback for responses without action markers)
      if (!actionHandled) {
        const lowerResponse = response.toLowerCase();
        if (
          (lowerResponse.includes("template") ||
            lowerResponse.includes("sample")) &&
          (lowerResponse.includes("hbr") ||
            lowerResponse.includes("target list") ||
            lowerResponse.includes("excel"))
        ) {
          // Auto-trigger template download for intelligent responses
          setTimeout(() => {
            handleHbrTemplateDownload();
          }, 1000); // Small delay to let the message appear first
        }
      }

      // Check if the response contains an HBR process ID
      const processIdMatch = response.match(
        /<hbr_process_id>(.*?)<\/hbr_process_id>/,
      );
      if (processIdMatch && processIdMatch[1]) {
        setHbrProcessId(processIdMatch[1]);
        setHbrUploadStage("excel");
      }
    } catch (error) {
      console.error("Error processing message:", error);
      handleApiError(error as Error, "message processing");
    } finally {
      setIsLoading(false);
    }
  }, [currentChatId, pendingDocumentSave, chatContainerRef]);

  /**
   * Handle HBR template download - provide a downloadable link instead of auto-download
   */
  const handleHbrTemplateDownload = useCallback(async () => {
    try {
      // Create the download link URL with cache-busting timestamp
      const timestamp = new Date().getTime();
      const templateUrl = `${API_BASE_URL}/api/download-sample-template?t=${timestamp}`;

      // Add a message to chat with the download link
      const downloadMessage: Message = {
        id: (Date.now() + 2).toString(),
        content: `📋 **HBR Target List Template**

Here's your sample template with three columns: Parameter, Search_Pages, and Comments.

📥 [Download HBR Target List Template](${templateUrl})

**Instructions:**
1. Click the link above to download the template
2. Fill in the following columns:
   - **Parameter**: The exact parameter name you're looking for
   - **Search_Pages**: Comma-separated list of page numbers to search (e.g., "1,2,3" or just "5")
   - **Comments**: Optional hints or notes to help locate the parameter
3. Save the file and upload it back here

The template contains sample data to show you the correct format.`,
        role: "assistant",
        timestamp: new Date(),
      };
      setMessages((prev) => [...prev, downloadMessage]);
    } catch (error) {
      console.error("Error providing template link:", error);

      // Add error message to chat
      const errorMessage: Message = {
        id: (Date.now() + 2).toString(),
        content:
          "❌ Failed to provide template link. You can manually create an Excel file with three columns: 'Parameter', 'Search_Pages', and 'Comments'.",
        role: "assistant",
        timestamp: new Date(),
      };
      setMessages((prev) => [...prev, errorMessage]);

      // ALWAYS scroll to bottom after error message
      setTimeout(() => {
        scrollChatToBottom();
        setUserScrolling(false);
      }, 100);
    }
  }, []);

  /**
   * Open COA Chat Panel
   */
  const openCoAChat = useCallback(() => {
    setShowCoAChat(true);
    // Initialize chat if needed
    if (coaProcessId && coaChatMessages.length === 0) {
      // Add welcome message
      setCoaChatMessages([
        {
          role: "assistant",
          content:
            "Hello! I can help you explore and understand the extracted COA data. You can ask me about:\n• Product information\n• Test results and specifications\n• Specific parameters or methods\n• Comparisons and summaries\n\nWhat would you like to know?",
          timestamp: new Date(),
        },
      ]);
    }
  }, [coaProcessId, coaChatMessages.length]);

  /**
   * Send message in COA Chat with STREAMING response
   * Uses Server-Sent Events (SSE) for real-time typing effect
   */
  const sendCoAChatMessage = useCallback(async (message: string) => {
    if (!coaProcessId || !message.trim()) return;

    // Add user message
    const userMessage = {
      role: "user" as const,
      content: message,
      timestamp: new Date(),
    };
    setCoaChatMessages((prev) => [...prev, userMessage]);
    setCoaChatLoading(true);

    // Add placeholder for streaming assistant message
    const streamingMessageId = Date.now();
    setCoaChatMessages((prev) => [
      ...prev,
      {
        role: "assistant" as const,
        content: "",
        timestamp: new Date(),
        isStreaming: true,
      },
    ]);

    try {
      const response = await fetch(
        `${API_BASE_URL}/api/chat/coa-rag-stream/${coaProcessId}`,
        {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
          },
          body: JSON.stringify({ question: message }),
        },
      );

      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }

      // Read the stream
      const reader = response.body?.getReader();
      const decoder = new TextDecoder();
      let accumulatedText = "";

      if (!reader) {
        throw new Error("No response body reader available");
      }

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        const chunk = decoder.decode(value, { stream: true });
        const lines = chunk
          .split("\n")
          .filter((line) => line.startsWith("data: "));

        for (const line of lines) {
          const data = line.replace("data: ", "").trim();
          if (!data) continue;

          try {
            const parsed = JSON.parse(data);

            if (parsed.error) {
              throw new Error(parsed.error);
            }

            if (parsed.text) {
              accumulatedText += parsed.text;
              // Update the last message (streaming one) with accumulated text
              setCoaChatMessages((prev) => {
                const newMessages = [...prev];
                const lastIdx = newMessages.length - 1;
                if (lastIdx >= 0 && newMessages[lastIdx].role === "assistant") {
                  newMessages[lastIdx] = {
                    ...newMessages[lastIdx],
                    content: accumulatedText,
                    isStreaming: true,
                  };
                }
                return newMessages;
              });
            }

            if (parsed.done) {
              // Mark streaming as complete
              setCoaChatMessages((prev) => {
                const newMessages = [...prev];
                const lastIdx = newMessages.length - 1;
                if (lastIdx >= 0 && newMessages[lastIdx].role === "assistant") {
                  newMessages[lastIdx] = {
                    ...newMessages[lastIdx],
                    content: accumulatedText,
                    isStreaming: false,
                  };
                }
                return newMessages;
              });
            }
          } catch (parseError) {
            console.warn("Error parsing SSE data:", parseError);
          }
        }
      }

      // Ensure streaming flag is removed at the end
      setCoaChatMessages((prev) => {
        const newMessages = [...prev];
        const lastIdx = newMessages.length - 1;
        if (lastIdx >= 0 && newMessages[lastIdx].role === "assistant") {
          newMessages[lastIdx] = {
            ...newMessages[lastIdx],
            isStreaming: false,
          };
        }
        return newMessages;
      });
    } catch (error) {
      console.error("Error sending COA chat message:", error);
      // Update the streaming message to show error
      setCoaChatMessages((prev) => {
        const newMessages = [...prev];
        const lastIdx = newMessages.length - 1;
        if (lastIdx >= 0 && newMessages[lastIdx].role === "assistant") {
          newMessages[lastIdx] = {
            role: "assistant" as const,
            content:
              "Sorry, I encountered an error processing your question. Please try again.",
            timestamp: new Date(),
            isStreaming: false,
          };
        }
        return newMessages;
      });
    } finally {
      setCoaChatLoading(false);
    }
  }, [coaProcessId]);

  /**
   * Close COA Chat Panel
   */
  const closeCoAChat = useCallback(() => {
    setShowCoAChat(false);
  }, []);

  /**
   * Smooth progress animation function
   */
  const startSmoothProgress = (targetProgress: number) => {
    // Clear existing animation
    if (progressAnimationRef.current) {
      clearInterval(progressAnimationRef.current);
    }

    // Store target in ref
    targetProgressRef.current = targetProgress;

    // Start interval that increments animatedProgress
    progressAnimationRef.current = setInterval(() => {
      setAnimatedProgress((current) => {
        const target = targetProgressRef.current;
        const gap = target - current;

        // If we've reached or passed the target, STOP there
        if (gap <= 0) {
          if (progressAnimationRef.current) {
            clearInterval(progressAnimationRef.current);
            progressAnimationRef.current = null;
          }
          return target;
        }

        // Calculate increment based on gap size
        let increment;
        if (gap > 50)
          increment = 2; // Fast for big jumps (10→60)
        else if (gap > 10)
          increment = 1; // Medium speed
        else increment = 0.5; // Slow for small gaps

        // Don't overshoot the target
        const nextProgress = Math.min(current + increment, target);

        // If we've reached the target, stop the animation
        if (nextProgress >= target) {
          if (progressAnimationRef.current) {
            clearInterval(progressAnimationRef.current);
            progressAnimationRef.current = null;
          }
          return target;
        }

        return nextProgress;
      });
    }, 100);
  };

  /**
   * Handle file upload
   */
  const handleFileUpload = async (file: File) => {
    if (!file) return;

    // Add upload message to chat
    const uploadMessage: Message = {
      id: Date.now().toString(),
      content: `Uploading ${file.name}...`,
      role: "user",
      timestamp: new Date(),
    };
    setMessages((prev) => [...prev, uploadMessage]);

    try {
      // Auto-detect document type if not set - use local variable for immediate use
      let effectiveDocumentType = currentDocumentType;
      if (!currentDocumentType && file.type === "application/pdf") {
        effectiveDocumentType = "coa";
        setCurrentDocumentType("coa");
      }

      // Show upload progress
      setUploadProgress(0);
      setUploadStage("uploading");

      // Reset animated progress
      if (progressAnimationRef.current) {
        clearInterval(progressAnimationRef.current);
        progressAnimationRef.current = null;
      }
      setAnimatedProgress(0);

      // Show processing state with file information
      setProcessingState({
        active: true,
        stage: "uploading",
        fileName: file.name,
        progress: 0,
        detailedStage: "",
        fileSize: file.size,
      });

      // Reset response flag for new upload
      setResponseAdded(false);

      // Enable cancellation immediately (before backend responds) - ONLY for COA documents
      // HBR documents are multi-agent and can't be meaningfully cancelled
      const isCOADocument = !(
        effectiveDocumentType === "hbr" ||
        effectiveDocumentType === "hbr_multiagent"
      );

      const tempProcessId = `temp-${Date.now()}-${Math.random()
        .toString(36)
        .substr(2, 9)}`;
      setCurrentProcessId(tempProcessId);
      setCanCancel(isCOADocument); // Only enable for COA documents
      setUserCancelled(false); // Reset cancellation flag for new upload
      console.log(
        "🔄 Upload started, immediate cancellation enabled with temp ID:",
        tempProcessId,
        "- COA cancellation enabled:",
        isCOADocument,
      );

      let extractedText = "";
      let finalProcessId: string | null = null; // Declare at this scope so it's accessible everywhere

      // Handle different document types
      if (
        effectiveDocumentType === "hbr" ||
        effectiveDocumentType === "hbr_multiagent"
      ) {
        // For HBR documents, we need to handle PDF and Excel files differently
        if (hbrUploadStage === "pdf") {
          // Process HBR PDF file - show simple upload flow (no OCR processing yet)
          extractedText = await extractTextFromFile(
            file,
            (stage, progress) => {
              setUploadStage(stage);
              setUploadProgress(progress);

              // Start smooth progress animation
              startSmoothProgress(progress);

              // For HBR PDF, show simple upload status instead of full OCR processing
              let simpleStatus = "";
              if (progress < 60) simpleStatus = "Uploading file...";
              else if (progress < 100)
                simpleStatus = "File uploaded successfully";
              else simpleStatus = "Ready for target list";

              setProcessingState({
                active: true,
                stage: stage,
                fileName: file.name,
                progress: progress,
                detailedStage: simpleStatus,
                documentType: "hbr_pdf",
                fileSize: file.size,
              });

              // When complete, show completed state for 2 seconds
              if (stage === "analyzing" && progress === 100) {
                // Quickly animate to 100% on completion
                if (progressAnimationRef.current) {
                  clearInterval(progressAnimationRef.current);
                  progressAnimationRef.current = null;
                }
                setAnimatedProgress(100);

                setTimeout(() => {
                  setProcessingState({
                    active: true,
                    stage: "completed",
                    fileName: file.name,
                    progress: 100,
                    detailedStage: "File uploaded - Ready for target list",
                    documentType: "hbr_pdf",
                    fileSize: file.size,
                  });

                  // Hide the processing state after 2 seconds
                  setTimeout(() => {
                    setProcessingState({
                      active: false,
                      stage: "uploading",
                      fileName: "",
                      progress: 0,
                      detailedStage: "",
                    });
                  }, 2000);
                }, 500);
              }
            },
            "hbr_pdf",
            undefined,
            (processId) => {
              // Update with real process ID from backend (replacing temporary ID)
              console.log(
                "📋 HBR PDF real process ID received, updating from temp:",
                tempProcessId,
                "to:",
                processId,
              );

              // Note: HBR cancellation is disabled, so no need to check userCancelled
              setCurrentProcessId(processId);
            },
          );

          // Check if the response contains an error message
          if (extractedText.startsWith("[Error")) {
            // Clear progress animation
            if (progressAnimationRef.current) {
              clearInterval(progressAnimationRef.current);
              progressAnimationRef.current = null;
            }
            setAnimatedProgress(0);

            // Make sure to reset processing state on error
            setProcessingState({
              active: false,
              stage: "uploading",
              fileName: "",
              progress: 0,
              detailedStage: "",
            });
          } else {
            // Check if the response contains an HBR process ID
            const processIdMatch = extractedText.match(
              /<hbr_process_id>(.*?)<\/hbr_process_id>/,
            );

            if (processIdMatch && processIdMatch[1]) {
              // Update state to show Excel upload button
              setHbrProcessId(processIdMatch[1]);
              setHbrUploadStage("excel");
              setShowHbrUploadUI(true); // Make sure this is set to true
              console.log("HBR PDF uploaded, switching to Excel upload stage");
            }
          }
        } else if (hbrUploadStage === "excel" && hbrProcessId) {
          // Process HBR Excel file with process ID - choose processing method based on document type
          console.log("Debug - Current document type:", effectiveDocumentType);
          console.log("Debug - HBR upload stage:", hbrUploadStage);
          console.log("Debug - HBR process ID:", hbrProcessId);

          const hbrExcelType =
            effectiveDocumentType === "hbr_multiagent"
              ? "hbr_excel_multiagent"
              : "hbr_excel";

          console.log("Debug - Selected HBR Excel type:", hbrExcelType);

          extractedText = await extractTextFromFile(
            file,
            (stage, progress) => {
              setUploadStage(stage);
              setUploadProgress(progress);

              // Start smooth progress animation
              startSmoothProgress(progress);

              // Update processing state with current progress
              setProcessingState({
                active: true,
                stage: stage,
                fileName: file.name,
                progress: progress,
                detailedStage: getDetailedStatusMessages(progress),
                documentType: "hbr_excel",
                fileSize: file.size,
              });

              // When complete, show completed state for 2 seconds
              if (stage === "analyzing" && progress === 100) {
                // Quickly animate to 100% on completion
                if (progressAnimationRef.current) {
                  clearInterval(progressAnimationRef.current);
                  progressAnimationRef.current = null;
                }
                setAnimatedProgress(100);

                setTimeout(() => {
                  setProcessingState({
                    active: true,
                    stage: "completed",
                    fileName: file.name,
                    progress: 100,
                    detailedStage: "Processing complete",
                  });

                  // Hide the processing state after 2 seconds to let user appreciate completion
                  setTimeout(() => {
                    setProcessingState({
                      active: false,
                      stage: "uploading",
                      fileName: "",
                      progress: 0,
                      detailedStage: "",
                    });
                  }, 2000);
                }, 500);
              }
            },
            hbrExcelType,
            hbrProcessId,
            (processId) => {
              // Update with real process ID from backend (replacing temporary ID)
              console.log(
                "📋 HBR Excel real process ID received, updating from temp:",
                tempProcessId,
                "to:",
                processId,
              );

              // Note: HBR cancellation is disabled, so no need to check userCancelled
              setCurrentProcessId(processId);
            },
          );

          // Check if the response contains an error message
          if (extractedText.startsWith("[Error")) {
            // Clear progress animation
            if (progressAnimationRef.current) {
              clearInterval(progressAnimationRef.current);
              progressAnimationRef.current = null;
            }
            setAnimatedProgress(0);

            // Make sure to reset processing state on error
            setProcessingState({
              active: false,
              stage: "uploading",
              fileName: "",
              progress: 0,
              detailedStage: "",
            });
          } else {
            // Extract session ID from multi-agent response if available
            if (effectiveDocumentType === "hbr_multiagent") {
              const sessionIdMatch = extractedText.match(
                /Multi-Agent Session ID: ([a-f0-9-]+)/,
              );
              if (sessionIdMatch && sessionIdMatch[1]) {
                setHbrSessionId(sessionIdMatch[1]);
                console.log(
                  "Stored HBR multi-agent session ID:",
                  sessionIdMatch[1],
                );
              }
            }

            // Reset HBR state after processing both files
            setHbrProcessId(null);
            setHbrUploadStage("pdf");
            setShowHbrUploadUI(false);
          }
        } else {
          throw new Error("Invalid HBR upload stage or missing process ID");
        }
      } else {
        // Process standard COA file
        extractedText = await extractTextFromFile(
          file,
          (stage, progress) => {
            setUploadStage(stage);
            setUploadProgress(progress);

            // Start smooth progress animation
            startSmoothProgress(progress);

            // Update processing state with current progress
            setProcessingState({
              active: true,
              stage: stage,
              fileName: file.name,
              progress: progress,
              detailedStage: getDetailedStatusMessages(progress),
              documentType: "coa",
              fileSize: file.size,
            });

            // When complete, show completed state and keep it visible for chat
            if (stage === "analyzing" && progress === 100) {
              // Quickly animate to 100% on completion
              if (progressAnimationRef.current) {
                clearInterval(progressAnimationRef.current);
                progressAnimationRef.current = null;
              }
              setAnimatedProgress(100);

              setTimeout(() => {
                // Hide the processing state after completion
                setProcessingState({
                  active: false,
                  stage: "uploading",
                  fileName: "",
                  progress: 0,
                  detailedStage: "",
                });

                // When completed, disable cancel button
                setCanCancel(false);
              }, 500);
            }
          },
          "coa",
          undefined,
          (processId) => {
            // Store COA process ID for chat
            finalProcessId = processId; // Store in local variable
            setCoaProcessId(processId);
            setActiveDocumentName(file.name); // Phase 5: For PDF panel

            // Phase 4: Set active COA document in agent for RAG queries
            agent.setActiveCoaDocument(processId, file.name);
            console.log(
              "[RAG] Active COA document set in agent:",
              processId,
              file.name,
            );

            // Phase 4: Save document to PostgreSQL for persistence (enables RAG after page refresh)
            // If chat exists, save directly. Otherwise, store as pending to save when chat is created.
            if (currentChatId) {
              console.log(
                "[DB] Chat exists, saving document directly to:",
                currentChatId,
              );
              // Clear any previous pending save to prevent duplicates
              setPendingDocumentSave(null);
              addDocumentToChat(currentChatId, {
                document_id: processId, // Use process_id as document_id
                document_name: file.name,
                file_size: file.size,
                process_id: processId,
                document_type: effectiveDocumentType || "coa",
              })
                .then(() => {
                  console.log(
                    "[DB] Document saved to PostgreSQL:",
                    processId,
                    file.name,
                  );
                })
                .catch((err) => {
                  console.error(
                    "[DB] Failed to save document to PostgreSQL:",
                    err,
                  );
                });
            } else {
              // No chat yet - store as pending to save when chat is created
              console.log(
                "[DB] No chat yet, storing document as pending:",
                processId,
                file.name,
              );
              setPendingDocumentSave({
                process_id: processId,
                document_name: file.name,
                file_size: file.size,
                document_type: effectiveDocumentType || "coa",
              });
            }

            // Update with real process ID from backend (replacing temporary ID)
            console.log(
              "📋 COA real process ID received, updating from temp:",
              tempProcessId,
              "to:",
              processId,
            );

            // Check if user already cancelled before backend responded
            if (userCancelled) {
              console.log(
                "⚠️ Process already cancelled, sending cancellation to backend",
              );
              cancelProcess(processId); // Cancel the backend process that just started
              return;
            }

            setCurrentProcessId(processId);
            // setCanCancel already set to true immediately above
          },
        );

        // Check if the response contains an error message
        if (extractedText.startsWith("[Error")) {
          // Clear progress animation
          if (progressAnimationRef.current) {
            clearInterval(progressAnimationRef.current);
            progressAnimationRef.current = null;
          }
          setAnimatedProgress(0);

          // Make sure to reset processing state on error
          setProcessingState({
            active: false,
            stage: "uploading",
            fileName: "",
            progress: 0,
            detailedStage: "",
          });

          // Add error message immediately for errors
          const errorMessage: Message = {
            id: (Date.now() + 1).toString(),
            content: extractedText
              .replace(/<hbr_process_id>.*?<\/hbr_process_id>/g, "")
              .trim(),
            role: "assistant",
            timestamp: new Date(),
          };
          setMessages((prev) => [...prev, errorMessage]);

          // ALWAYS scroll to bottom after error message
          setTimeout(() => {
            scrollChatToBottom();
            setUserScrolling(false);
          }, 100);
        }
      }

      // Add AI response with centralized timing after completion state
      if (!extractedText.startsWith("[Error")) {
        // For COA, show the response immediately since the status bar stays visible
        const responseDelay = effectiveDocumentType === "coa" ? 500 : 2500;

        // For COA, add the status message first, then the response
        if (effectiveDocumentType === "coa") {
          // Add COA completion status as a message in chat history
          setTimeout(() => {
            // Use the local variable which should have the process ID by now
            const processIdToUse =
              finalProcessId || coaProcessId || currentProcessId;
            console.log("Adding COA status message:");
            console.log("  - finalProcessId (local var):", finalProcessId);
            console.log("  - coaProcessId (state):", coaProcessId);
            console.log("  - currentProcessId (state):", currentProcessId);
            console.log("  - processIdToUse:", processIdToUse);
            console.log("  - effectiveDocumentType:", effectiveDocumentType);
            console.log("  - file.name:", file.name);

            if (processIdToUse) {
              // Sanitize filename the same way backend does
              const sanitizeFilename = (filename: string) => {
                const [name, ext] = filename.split(/\.(?=[^.]+$)/);
                // Replace spaces with underscores
                let safeName = name.replace(/\s+/g, "_");
                // Remove parentheses
                safeName = safeName.replace(/[()]/g, "");
                // Replace other special chars with underscore
                safeName = safeName.replace(/[^a-zA-Z0-9_\-]/g, "_");
                // Clean up multiple underscores
                safeName = safeName.replace(/_+/g, "_");
                // Remove trailing underscores
                safeName = safeName.replace(/_+$/, "");
                return safeName;
              };

              const sanitizedName = sanitizeFilename(file.name);
              const enhancedFileName = `${sanitizedName}_enhanced.xlsx`;

              const statusMessage: Message = {
                id: `status-${Date.now()}`,
                content: "",
                role: "system",
                timestamp: new Date(),
                extractionStatus: {
                  processId: processIdToUse,
                  fileName: file.name,
                  enhancedFileName: enhancedFileName,
                  stage: "completed",
                  documentType: "coa",
                },
              };
              console.log("Status message created:", statusMessage);
              setMessages((prev) => {
                console.log("Previous messages:", prev);
                const newMessages = [...prev, statusMessage];
                console.log("New messages with status:", newMessages);
                return newMessages;
              });

              // Also ensure the state is updated for later use
              if (!coaProcessId && processIdToUse) {
                setCoaProcessId(processIdToUse);
                // Phase 4: Also set in agent for RAG queries
                agent.setActiveCoaDocument(processIdToUse, file.name);
              }
            } else {
              console.error("No process ID available for COA status message");
            }
          }, 100); // Small delay to ensure everything is set
        }

        // For COA, skip the download message since it's in the status card
        // For other document types, show the full response
        if (effectiveDocumentType !== "coa") {
          setTimeout(() => {
            const extractedMessage: Message = {
              id: (Date.now() + 1).toString(),
              content: extractedText
                .replace(/<hbr_process_id>.*?<\/hbr_process_id>/g, "")
                .trim(),
              role: "assistant",
              timestamp: new Date(),
            };
            setMessages((prev) => [...prev, extractedMessage]);

            // ALWAYS scroll to bottom after file upload response
            setTimeout(() => {
              scrollChatToBottom();
              setUserScrolling(false);
            }, 100);
          }, responseDelay); // Delayed for non-COA documents
        } else {
          // For COA, just scroll to show the status card
          setTimeout(() => {
            scrollChatToBottom();
            setUserScrolling(false);
          }, 600);
        }
      }

      // Only hide the upload UI for COA or after completing the HBR Excel upload
      if (effectiveDocumentType !== "hbr" || hbrUploadStage !== "pdf") {
        setShowUploadUI(false);
      }

      // Reset file input to allow re-uploading the same file
      if (fileInputRef.current) {
        fileInputRef.current.value = "";
      }

      // Reset cancellation state
      setUserCancelled(false);
    } catch (error) {
      console.error("Error uploading file:", error);

      // Don't show cancellation errors - user initiated these
      const errorMessage = (error as Error).message.toLowerCase();
      if (
        errorMessage.includes("cancelled by user") ||
        errorMessage.includes("process cancelled")
      ) {
        console.log("File upload cancelled by user, not showing error message");

        // Clear progress animation
        if (progressAnimationRef.current) {
          clearInterval(progressAnimationRef.current);
          progressAnimationRef.current = null;
        }
        setAnimatedProgress(0);

        // Reset processing state for cancellation
        setProcessingState({
          active: false,
          stage: "uploading",
          fileName: "",
          progress: 0,
          detailedStage: "",
        });

        // Reset upload-related states
        setUploadProgress(0);
        setUploadStage("uploading");
        setCanCancel(false);
        setCurrentProcessId(null);

        // Reset file input to allow re-uploading the same file
        if (fileInputRef.current) {
          fileInputRef.current.value = "";
        }

        // Reset cancellation state
        setUserCancelled(false);

        return; // Exit silently for cancellation
      }

      handleApiError(error as Error, `file upload for ${file.name}`);

      // Reset HBR-specific states if applicable
      if (
        currentDocumentType === "hbr" ||
        currentDocumentType === "hbr_multiagent"
      ) {
        // Only reset if we're in the Excel upload stage (keep PDF upload state if that's where we are)
        if (hbrUploadStage === "excel") {
          setHbrUploadStage("pdf");
        }
      }
    } finally {
      // Reset file input to allow re-uploading the same file (always reset regardless of outcome)
      if (fileInputRef.current) {
        fileInputRef.current.value = "";
      }

      // Remove this from finally since we're handling it in both try and catch blocks
      // setUploadProgress(0);
      // setUploadStage("uploading");
    }
  };

  const handleKeyPress = useCallback((e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSendMessage(inputMessage);
      setInputMessage("");
    }
  }, [inputMessage, handleSendMessage]);

  // Add keyboard shortcut for scrolling to bottom
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      // If End key is pressed, scroll to bottom
      if (e.key === "End") {
        scrollToBottom();
      }
    };

    window.addEventListener("keydown", handleKeyDown);
    return () => {
      window.removeEventListener("keydown", handleKeyDown);
    };
  }, []);

  // Add this useEffect after other useEffects
  // Ensure processing state is reset if component unmounts during active upload
  useEffect(() => {
    return () => {
      // Cleanup function - reset processing state when component unmounts
      if (processingState.active) {
        // Clear progress animation
        if (progressAnimationRef.current) {
          clearInterval(progressAnimationRef.current);
          progressAnimationRef.current = null;
        }
        setAnimatedProgress(0);

        setProcessingState({
          active: false,
          stage: "uploading",
          fileName: "",
          progress: 0,
          detailedStage: "",
        });
      }
    };
  }, [processingState.active]);

  // Add a timeout to automatically hide the processing state after 5 minutes
  // This is a safety mechanism in case the normal completion flow fails
  useEffect(() => {
    let timeoutId: NodeJS.Timeout | null = null;

    if (processingState.active) {
      // Main timeout - only hide processing state after 5 minutes for true failures
      timeoutId = setTimeout(
        () => {
          console.log(
            "Processing state safety timeout triggered after 5 minutes",
          );
          setProcessingState({
            active: false,
            stage: "uploading",
            fileName: "",
            progress: 0,
            detailedStage: "",
          });

          // Only add error message if it's been a very long time (5 minutes)
          const errorMessage: Message = {
            id: Date.now().toString(),
            content:
              "Processing is taking longer than expected. Please check if your document has finished processing or try refreshing the page.",
            role: "assistant",
            timestamp: new Date(),
          };
          setMessages((prev) => [...prev, errorMessage]);
        },
        30 * 60 * 1000,
      ); // 5 minutes timeout - much more patient
    }

    return () => {
      if (timeoutId) {
        clearTimeout(timeoutId);
      }
    };
  }, [processingState.active]); // Only depend on active state, not progress

  // Add this function after handleFileUpload
  /**
   * Handle API errors and reset UI state
   */
  const handleApiError = (error: Error, context: string) => {
    console.error(`API error in ${context}:`, error);
    console.log("Full error message:", error.message); // Debug log

    // Don't show cancellation errors - these are user-initiated
    const errorMessage = error.message.toLowerCase();
    if (
      errorMessage.includes("cancelled by user") ||
      errorMessage.includes("process cancelled") ||
      (errorMessage.includes("error processing") &&
        errorMessage.includes("cancelled"))
    ) {
      console.log("Process cancelled by user, not showing error message");
      return; // Don't show error message to user or reset UI
    }

    // Don't show timeout errors, network issues, or "stalled" messages to users
    // These are usually due to slow processing or network issues, not actual failures
    if (
      errorMessage.includes("timeout") ||
      errorMessage.includes("stalled") ||
      errorMessage.includes("no updates received") ||
      errorMessage.includes("processing may have failed") ||
      errorMessage.includes("connection") ||
      errorMessage.includes("fetch")
    ) {
      console.warn(
        "Network/timeout issue detected, not showing to user:",
        error.message,
      );
      return; // Don't show error message to user or reset UI - let processing continue
    }

    // Only show real errors (like authentication failures, server errors, etc.)
    const realErrorMessage: Message = {
      id: Date.now().toString(),
      content: `Error: ${error.message}. Please try again or refresh the page.`,
      role: "assistant",
      timestamp: new Date(),
    };
    setMessages((prev) => [...prev, realErrorMessage]);

    // Only reset processing state for real errors, not timeouts
    setProcessingState({
      active: false,
      stage: "uploading",
      fileName: "",
      progress: 0,
      detailedStage: "",
    });

    // Reset upload-related states
    setUploadProgress(0);
    setUploadStage("uploading");
  };

  // Add a beforeunload event listener to reset processing state when page is refreshed
  useEffect(() => {
    const handleBeforeUnload = () => {
      // Reset processing state before page unload
      setProcessingState({
        active: false,
        stage: "uploading",
        fileName: "",
        progress: 0,
        detailedStage: "",
      });
    };

    window.addEventListener("beforeunload", handleBeforeUnload);

    return () => {
      window.removeEventListener("beforeunload", handleBeforeUnload);
    };
  }, []);

  // Add this useEffect to reset all states when component unmounts
  useEffect(() => {
    // This is the cleanup function that runs when component unmounts
    return () => {
      // Clear progress animation
      if (progressAnimationRef.current) {
        clearInterval(progressAnimationRef.current);
        progressAnimationRef.current = null;
      }
      setAnimatedProgress(0);

      // Reset all upload and processing states
      setProcessingState({
        active: false,
        stage: "uploading",
        fileName: "",
        progress: 0,
        detailedStage: "",
      });
      setUploadProgress(0);
      setUploadStage("uploading");
      setShowUploadUI(false);
      setShowHbrUploadUI(false);
      setHbrProcessId(null);
      setHbrUploadStage("pdf");
    };
  }, []);

  // Processing Status Messages with detailed stages based on document type
  const getDetailedStatusMessages = (progress: number): string => {
    // Check if this is an HBR document processing
    if (processingState.documentType?.includes("hbr")) {
      // HBR-specific status messages
      if (progress < 10) return "Excel configuration uploaded successfully";
      if (progress < 20) return "Initializing multi-agent HBR system...";
      if (progress < 35) return "Document extraction in progress...";
      if (progress < 55) return "Data processing with AI agents...";
      if (progress < 75) return "Merging results from multiple agents...";
      if (progress < 90) return "Validating extracted parameters...";
      if (progress < 100) return "Creating final output report...";
      return "HBR extraction complete";
    } else {
      // COA-specific status messages
      if (progress < 10) return "Document uploaded successfully";
      if (progress < 20) return "Preparing document analysis...";
      if (progress < 35) return "Scanning document structure...";
      if (progress < 50) return "Reading text and data...";
      if (progress < 65) return "Interpreting complex content...";
      if (progress < 80) return "Analyzing with specialized agents...";
      if (progress < 95) return "Organizing extracted information...";
      if (progress < 100) return "Finalizing results...";
      return "Analysis complete";
    }
  };

  // Helper function to format file size
  const formatFileSize = (bytes: number): string => {
    if (bytes === 0) return "0 B";
    const k = 1024;
    const sizes = ["B", "KB", "MB", "GB"];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + " " + sizes[i];
  };

  if (loading) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-gradient-to-br from-gray-50 to-blue-50">
        <div className="text-center">
          <div className="relative w-24 h-24 mx-auto mb-6">
            <div className="absolute inset-0 border-4 border-blue-200 rounded-full animate-pulse"></div>
            <div className="absolute inset-2 border-4 border-blue-400 border-t-transparent rounded-full animate-spin"></div>
            <div
              className="absolute inset-4 border-4 border-blue-600 border-t-transparent border-b-transparent rounded-full animate-spin"
              style={{ animationDuration: "1.5s" }}
            ></div>
            <div
              className="absolute inset-6 border-4 border-blue-800 border-b-transparent rounded-full animate-spin"
              style={{ animationDuration: "2s", animationDirection: "reverse" }}
            ></div>
          </div>
          <p className="text-blue-600 font-medium animate-pulse">
            Loading AI Document Parser...
          </p>
        </div>
      </div>
    );
  }

  return (
    <div
      className="flex flex-col h-screen bg-gradient-to-br from-gray-50 to-blue-50 relative overflow-hidden transition-all duration-150"
      style={{ marginLeft: showPDFPanel ? `${pdfPanelWidth}vw` : '0' }}
    >
      {/* Chat History Sidebar - hidden when PDF panel is open */}
      <ChatSidebar
        ref={chatSidebarRef}
        isOpen={sidebarOpen && !showPDFPanel}
        onToggle={toggleSidebar}
        currentChatId={currentChatId || undefined}
        onSelectChat={handleSelectChat}
        onNewChat={handleNewChat}
      />

      {/* Animated background elements */}
      <div className="absolute inset-0 overflow-hidden pointer-events-none">
        <div className="absolute -top-[30%] -left-[10%] w-[70%] h-[70%] bg-blue-100/20 rounded-full blur-3xl animate-blob1"></div>
        <div className="absolute -bottom-[30%] -right-[10%] w-[70%] h-[70%] bg-purple-100/20 rounded-full blur-3xl animate-blob2"></div>
        <div className="absolute top-[40%] left-[60%] w-[40%] h-[40%] bg-pink-100/10 rounded-full blur-3xl animate-blob3"></div>
      </div>

      {/* Welcome overlay */}
      {showWelcomeOverlay && (
        <div className="fixed inset-0 bg-gradient-to-br from-cyan-600/90 to-cyan-700/90 z-50 flex items-center justify-center animate-fadeIn">
          <div className="text-center">
            <div className="flex items-center justify-center mb-6">
              <div className="w-16 h-16 bg-white rounded-full flex items-center justify-center">
                <svg
                  xmlns="http://www.w3.org/2000/svg"
                  className="h-10 w-10 text-cyan-600"
                  viewBox="0 0 20 20"
                  fill="currentColor"
                >
                  <path
                    fillRule="evenodd"
                    d="M4 4a2 2 0 012-2h4.586A2 2 0 0112 2.586L15.414 6A2 2 0 0116 7.414V16a2 2 0 01-2 2H6a2 2 0 01-2-2V4z"
                    clipRule="evenodd"
                  />
                </svg>
              </div>
              <div className="ml-4 text-left">
                <h1 className="text-3xl font-bold text-white">
                  AI Document Parser
                </h1>
                <p className="text-cyan-100">Document analysis assistant</p>
              </div>
            </div>
            <p className="text-xl text-white mb-2">
              Welcome, {user?.username}!
            </p>
            <p className="text-cyan-100">Getting things ready for you...</p>
          </div>
        </div>
      )}

      {/* File Upload Progress Overlay - Removed as it's redundant with the Processing indicator below */}

      {/* Main content wrapper - shifts when sidebar is open */}
      <div
        className={`flex-1 flex flex-col h-full overflow-hidden transition-all duration-300 ${sidebarOpen && !showPDFPanel ? "ml-72" : "ml-0"}`}
      >
        {/* Navigation bar */}
        <nav className="bg-white shadow-sm border-b border-gray-200 z-10 sticky top-0">
          <div className="max-w-full mx-auto px-4">
            <div className="flex justify-between items-center h-14">
              {/* Left side - Sidebar toggle + App title */}
              <div className="flex items-center">
                {/* Chat History Toggle Button */}
                <button
                  onClick={toggleSidebar}
                  className="p-2 mr-2 rounded-lg hover:bg-gray-100 transition-colors group"
                  title="Toggle chat history"
                >
                  <svg
                    className="w-5 h-5 text-gray-600 group-hover:text-cyan-600 transition-colors"
                    fill="none"
                    stroke="currentColor"
                    viewBox="0 0 24 24"
                  >
                    <path
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      strokeWidth={2}
                      d="M4 6h16M4 12h16M4 18h7"
                    />
                  </svg>
                </button>

                <div className="w-8 h-8 rounded-full bg-gradient-to-r from-cyan-400 to-cyan-600 flex items-center justify-center text-white mr-2 shadow-md hover:shadow-lg transition-shadow duration-300">
                  <svg
                    xmlns="http://www.w3.org/2000/svg"
                    className="h-5 w-5"
                    viewBox="0 0 20 20"
                    fill="currentColor"
                  >
                    <path
                      fillRule="evenodd"
                      d="M4 4a2 2 0 012-2h4.586A2 2 0 0112 2.586L15.414 6A2 2 0 0116 7.414V16a2 2 0 01-2 2H6a2 2 0 01-2-2V4zm2 6a1 1 0 011-1h6a1 1 0 110 2H7a1 1 0 01-1-1zm1 3a1 1 0 100 2h6a1 1 0 100-2H7z"
                      clipRule="evenodd"
                    />
                  </svg>
                </div>
                <h1 className="text-xl font-bold text-slate-700 hover:scale-105 transition-transform duration-300 cursor-default">
                  AI Document Parser
                </h1>
              </div>

              {/* Right side - User welcome & logout */}
              <div className="flex items-center">
                {/* Schema Panel Button - Hidden for now, functionality preserved */}
                <button
                  onClick={() => {
                    setShowSchemaPanel(!showSchemaPanel);
                    if (!showSchemaPanel) setShowPDFPanel(false);
                  }}
                  className={`px-3 py-1.5 rounded-lg text-sm font-medium transition-all duration-200 flex items-center mr-2 hidden ${
                    showSchemaPanel
                      ? "bg-cyan-500 text-white shadow-md shadow-cyan-200"
                      : "text-cyan-600 bg-cyan-50 hover:bg-cyan-100 border border-cyan-200"
                  }`}
                >
                  <svg className="w-5 h-5 mr-1.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                    <path d="M14 11H8M10 15H8M16 7H8M20 10.5V6.8C20 5.11984 20 4.27976 19.673 3.63803C19.3854 3.07354 18.9265 2.6146 18.362 2.32698C17.7202 2 16.8802 2 15.2 2H8.8C7.11984 2 6.27976 2 5.63803 2.32698C5.07354 2.6146 4.6146 3.07354 4.32698 3.63803C4 4.27976 4 5.11984 4 6.8V17.2C4 18.8802 4 19.7202 4.32698 20.362C4.6146 20.9265 5.07354 21.3854 5.63803 21.673C6.27976 22 7.11984 22 8.8 22H11.5M22 22L20.5 20.5M21.5 18C21.5 19.933 19.933 21.5 18 21.5C16.067 21.5 14.5 19.933 14.5 18C14.5 16.067 16.067 14.5 18 14.5C19.933 14.5 21.5 16.067 21.5 18Z" />
                  </svg>
                  Extract
                </button>

                {/* Feedback Button */}
                <button
                  onClick={handleFeedbackOpen}
                  className="border border-cyan-400 text-cyan-600 px-3 py-1.5 rounded-md text-sm font-medium hover:bg-cyan-600 hover:text-white transition duration-300 shadow-sm hover:shadow-md flex items-center transform hover:scale-105 mr-3"
                >
                  💭 Feedback
                </button>

                {user && (
                  <div className="relative">
                    <button
                      onClick={() => setShowUserDropdown(!showUserDropdown)}
                      className={`w-10 h-10 rounded-full bg-gradient-to-br from-gray-100 to-gray-200 hover:from-cyan-50 hover:to-cyan-100 flex items-center justify-center transition-all duration-300 shadow-md hover:shadow-lg ring-2 ring-white ${showUserDropdown ? 'ring-cyan-400 from-cyan-50 to-cyan-100' : ''}`}
                    >
                      <svg className={`w-5 h-5 transition-colors duration-300 ${showUserDropdown ? 'text-cyan-600' : 'text-gray-500 hover:text-cyan-600'}`} fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z" />
                      </svg>
                    </button>

                    {showUserDropdown && (
                      <>
                        <div
                          className="fixed inset-0 z-40"
                          onClick={() => setShowUserDropdown(false)}
                        />
                        <div className="absolute right-0 mt-3 w-56 bg-white rounded-2xl shadow-xl border border-gray-100 overflow-hidden z-50 animate-fadeIn">
                          {/* User info header */}
                          <div className="bg-gradient-to-r from-gray-50 to-gray-100 px-4 py-4">
                            <div className="flex items-center gap-3">
                              <div className="w-10 h-10 rounded-full bg-gradient-to-br from-cyan-400 to-cyan-600 flex items-center justify-center text-white font-bold shadow-md">
                                {user.username.substring(0, 1).toUpperCase()}
                              </div>
                              <div>
                                <p className="text-sm font-semibold text-gray-800">{user.username}</p>
                              </div>
                            </div>
                          </div>

                          {/* Menu items */}
                          <div className="p-2">
                            <button
                              onClick={() => {
                                setShowUserDropdown(false);
                                handleLogout();
                              }}
                              className="w-full px-3 py-2.5 text-left text-sm text-gray-700 hover:bg-red-50 hover:text-red-600 rounded-xl flex items-center gap-3 transition-all duration-200 group"
                            >
                              <div className="w-8 h-8 rounded-lg bg-gray-100 group-hover:bg-red-100 flex items-center justify-center transition-colors">
                                <svg className="w-4 h-4 text-gray-500 group-hover:text-red-500 transition-colors" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M17 16l4-4m0 0l-4-4m4 4H7m6 4v1a3 3 0 01-3 3H6a3 3 0 01-3-3V7a3 3 0 013-3h4a3 3 0 013 3v1" />
                                </svg>
                              </div>
                              <span className="font-medium">Sign out</span>
                            </button>
                          </div>
                        </div>
                      </>
                    )}
                  </div>
                )}
              </div>
            </div>
          </div>
        </nav>

        {/* Chat Container - Full height */}
        <div className="flex-1 flex flex-col overflow-hidden">
          {/* Messages area with scrolling - virtualized for performance */}
          <div
            ref={chatContainerRef}
            className="flex-1 overflow-y-auto px-4 py-6 relative"
            style={{
              backgroundImage:
                "radial-gradient(circle at 25px 25px, rgba(0, 50, 200, 0.03) 2%, transparent 0%), radial-gradient(circle at 75px 75px, rgba(0, 100, 255, 0.03) 2%, transparent 0%)",
              backgroundSize: "100px 100px",
              backgroundAttachment: "fixed",
            }}
          >
            {/* Virtualized message container */}
            <div
              style={{
                height: `${messageVirtualizer.getTotalSize()}px`,
                width: "100%",
                position: "relative",
              }}
            >
              {messageVirtualizer.getVirtualItems().map((virtualRow) => {
                const message = messages[virtualRow.index];
                if (!message) return null;
                // Skip rendering empty streaming messages when Visual Audit is active
                // This prevents showing duplicate loading dots alongside the Visual Audit block
                if (visualAuditState.active && message.isStreaming && !message.content) {
                  return null;
                }

                // Render COA extraction status as a special message
                if (message.role === "system" && message.extractionStatus) {
                  const status = message.extractionStatus;
                  return (
                    <div
                      key={virtualRow.key}
                      data-index={virtualRow.index}
                      ref={messageVirtualizer.measureElement}
                      style={{
                        position: "absolute",
                        top: 0,
                        left: 0,
                        width: "100%",
                        transform: `translateY(${virtualRow.start}px)`,
                      }}
                      className="flex justify-center px-4"
                    >
                    <div className="w-full max-w-3xl">
                    <div
                      className="flex justify-start animate-messageIn mb-4"
                    >
                      <div className="w-9 h-9 rounded-full bg-gradient-to-r from-cyan-400 to-cyan-600 flex items-center justify-center text-white text-xs font-bold mr-2 flex-shrink-0 self-start mt-1 shadow-lg ring-2 ring-white relative overflow-hidden">
                        <div className="absolute inset-0 bg-gradient-to-br from-blue-400/30 to-purple-500/30 backdrop-blur-sm"></div>
                        <span className="text-sm relative z-10">AI</span>
                      </div>
                      <div className="w-full max-w-2xl">
                        {/* Processing Container */}
                        <div className="bg-cyan-50 border-cyan-500 border-[1.5px] rounded-xl p-5 transition-all duration-500 ease-in-out shadow-lg hover:shadow-xl relative overflow-hidden">
                          {/* Header Section */}
                          <div className="flex items-center justify-between mb-3">
                            <div className="flex items-center gap-3">
                              <div className="w-8 h-8 rounded-lg flex items-center justify-center bg-cyan-500 text-white">
                                <span className="text-base">📄</span>
                              </div>
                              <div>
                                <h3 className="text-[15px] font-semibold text-gray-800">
                                  COA Extraction Complete
                                </h3>
                                <p className="text-xs text-gray-600 mt-0.5">
                                  {status.fileName}
                                </p>
                              </div>
                            </div>
                            <span className="text-xs text-cyan-600 font-medium px-2 py-1 bg-cyan-100 rounded">
                              ✓ Completed
                            </span>
                          </div>

                        </div>
                      </div>
                    </div>
                    </div>
                    </div>
                  );
                }

                // Regular message rendering
                return (
                  <div
                    key={virtualRow.key}
                    data-index={virtualRow.index}
                    ref={messageVirtualizer.measureElement}
                    style={{
                      position: "absolute",
                      top: 0,
                      left: 0,
                      width: "100%",
                      transform: `translateY(${virtualRow.start}px)`,
                    }}
                    className="flex justify-center px-4 py-2"
                  >
                  <div className="w-full max-w-3xl">
                  <div
                    className={`flex ${
                      message.role === "user" ? "justify-end" : "justify-start"
                    } ${message.isNew ? "animate-messageIn" : ""}`}
                  >
                    {/* AI icon removed for cleaner assistant responses */}
                    <div
                      className={`p-4 ${
                        message.role === "user"
                          ? "max-w-md bg-gray-100 text-gray-800 rounded-3xl rounded-br-md shadow-lg hover:shadow-xl border border-gray-200 hover:border-gray-300 transition-all duration-300"
                          : "max-w-2xl bg-white/90 backdrop-blur-sm border border-gray-100 hover:border-gray-200 shadow-md hover:shadow-lg text-gray-800 rounded-3xl rounded-tl-md transition-all duration-300"
                      } relative overflow-hidden group`}
                    >
                      <div
                        className={`absolute inset-0 pointer-events-none ${
                          message.role === "user"
                            ? "bg-gradient-to-br from-gray-200/20 via-transparent to-gray-300/20"
                            : "bg-gradient-to-br from-blue-50/50 via-transparent to-purple-50/30"
                        } opacity-0 group-hover:opacity-100 transition-opacity duration-700`}
                      ></div>
                      <div className="whitespace-pre-wrap break-words relative z-10">
                        {/* Show loading dots when streaming but no content yet */}
                        {message.isStreaming && !message.content ? (
                          <div className="flex space-x-1 items-center py-0.5">
                            <div
                              className="w-2 h-2 rounded-full bg-cyan-500 animate-bounce"
                              style={{ animationDelay: "0ms" }}
                            ></div>
                            <div
                              className="w-2 h-2 rounded-full bg-cyan-500 animate-bounce"
                              style={{ animationDelay: "150ms" }}
                            ></div>
                            <div
                              className="w-2 h-2 rounded-full bg-cyan-500 animate-bounce"
                              style={{ animationDelay: "300ms" }}
                            ></div>
                          </div>
                        ) : (
                          <>
                            {renderMessageWithLinks(
                              message.content,
                              message.id,
                              setMessages,
                            )}
                            {/* Streaming cursor - blinking cursor while AI is typing */}
                            {message.isStreaming && message.content && (
                              <span className="inline-block w-2 h-4 ml-1 bg-cyan-500 animate-pulse align-middle" />
                            )}
                          </>
                        )}
                      </div>
                      <p className="text-xs opacity-70 mt-2 text-right font-medium relative z-10">
                        {message.timestamp.toLocaleTimeString([], {
                          hour: "2-digit",
                          minute: "2-digit",
                        })}
                      </p>
                      {/* Phase 5: Page reference buttons for PDF highlighting */}
                      {message.role === "assistant" && message.references && message.references.length > 0 && (
                        <div className="relative z-20">
                          <PageReferenceButtons
                            references={message.references}
                            onPageClick={(page, refs) => {
                              console.log(`[PDF-Panel] Opening page ${page} with ${refs.length} highlights`);
                              // Phase 5: Open PDF viewer with highlights
                              setPdfHighlights(refs);
                              setPdfInitialPage(page);
                              setShowPDFPanel(true);
                            }}
                          />
                        </div>
                      )}
                    </div>
                    {message.role === "user" && (
                      <div className="w-9 h-9 rounded-full bg-gray-400 flex items-center justify-center text-white text-xs font-bold ml-2 flex-shrink-0 self-start mt-1 shadow-lg ring-2 ring-white relative overflow-hidden group">
                        <div className="absolute inset-0 bg-gradient-to-br from-gray-300/30 to-gray-500/30 backdrop-blur-sm group-hover:scale-110 transition-all duration-500"></div>
                        <span className="text-sm relative z-10">
                          {user?.username.substring(0, 2).toUpperCase() || "U"}
                        </span>
                      </div>
                    )}
                  </div>
                  </div>
                  </div>
                );
              })}
            </div>

            {/* Indicators below virtualized messages */}
            <div className="flex justify-center px-4 py-4">
            <div className="w-full max-w-3xl">
              {/* Thinking indicator - Hide when Visual Audit is active */}
              {isThinking && !visualAuditState.active && (
                <div className="flex justify-start animate-messageIn">
                  <div className="w-9 h-9 rounded-full bg-gradient-to-r from-cyan-400 to-cyan-600 flex items-center justify-center text-white text-xs font-bold mr-2 flex-shrink-0 self-start mt-1 shadow-lg ring-2 ring-white relative overflow-hidden">
                    <div className="absolute inset-0 bg-gradient-to-br from-blue-400/30 to-purple-500/30 backdrop-blur-sm"></div>
                    <span className="text-sm relative z-10">AI</span>
                  </div>
                  <div className="bg-white/90 backdrop-blur-sm border border-gray-100 shadow-md rounded-3xl rounded-tl-md p-4 flex items-center relative overflow-hidden group">
                    <div className="absolute inset-0 bg-gradient-to-br from-blue-50/50 via-transparent to-purple-50/30 animate-pulse"></div>
                    <div className="flex space-x-2 relative z-10">
                      <div
                        className="w-2.5 h-2.5 rounded-full bg-gradient-to-r from-cyan-400 to-cyan-600 animate-bounce shadow-sm"
                        style={{ animationDelay: "0ms" }}
                      ></div>
                      <div
                        className="w-2.5 h-2.5 rounded-full bg-gradient-to-r from-cyan-400 to-cyan-600 animate-bounce shadow-sm"
                        style={{ animationDelay: "300ms" }}
                      ></div>
                      <div
                        className="w-2.5 h-2.5 rounded-full bg-gradient-to-r from-cyan-400 to-cyan-600 animate-bounce shadow-sm"
                        style={{ animationDelay: "600ms" }}
                      ></div>
                    </div>
                  </div>
                </div>
              )}

              {/* Loading indicator - Only show if processingState is not active AND no streaming message AND no visual audit */}
              {isLoading &&
                !processingState.active &&
                !visualAuditState.active &&
                !hasStreamingMessage && (
                  <div className="flex justify-start animate-messageIn">
                    <div className="w-9 h-9 rounded-full bg-gradient-to-r from-cyan-400 to-cyan-600 flex items-center justify-center text-white text-xs font-bold mr-2 flex-shrink-0 self-start mt-1 shadow-lg ring-2 ring-white relative overflow-hidden">
                      <div className="absolute inset-0 bg-gradient-to-br from-blue-400/30 to-purple-500/30 backdrop-blur-sm"></div>
                      <span className="text-sm relative z-10">AI</span>
                    </div>
                    <div className="bg-white/90 backdrop-blur-sm border border-gray-100 shadow-md rounded-3xl rounded-tl-md p-4 flex items-center relative overflow-hidden group">
                      <div className="absolute inset-0 bg-gradient-to-br from-blue-50/50 via-transparent to-purple-50/30 animate-pulse"></div>
                      <div className="flex space-x-2 relative z-10">
                        <div
                          className="w-2.5 h-2.5 rounded-full bg-gradient-to-r from-cyan-400 to-cyan-600 animate-bounce shadow-sm"
                          style={{ animationDelay: "0ms" }}
                        ></div>
                        <div
                          className="w-2.5 h-2.5 rounded-full bg-gradient-to-r from-cyan-400 to-cyan-600 animate-bounce shadow-sm"
                          style={{ animationDelay: "300ms" }}
                        ></div>
                        <div
                          className="w-2.5 h-2.5 rounded-full bg-gradient-to-r from-cyan-400 to-cyan-600 animate-bounce shadow-sm"
                          style={{ animationDelay: "600ms" }}
                        ></div>
                      </div>
                    </div>
                  </div>
                )}

              {/* Visual Audit Analysis Block - REPLACES loading dots with terminal-like logs */}
              {visualAuditState.active && (
                <div className="flex justify-start animate-messageIn">
                  <div className="w-9 h-9 rounded-full bg-gradient-to-r from-cyan-400 to-cyan-600 flex items-center justify-center text-white text-xs font-bold mr-2 flex-shrink-0 self-start mt-1 shadow-lg ring-2 ring-white relative overflow-hidden">
                    <div className="absolute inset-0 bg-gradient-to-br from-cyan-300/30 to-cyan-500/30 backdrop-blur-sm"></div>
                    <span className="text-sm relative z-10">AI</span>
                  </div>
                  <VisualAuditAnalysisBlock
                    logs={visualAuditState.logs}
                    stage={visualAuditState.stage}
                    query={visualAuditState.query}
                  />
                </div>
              )}

              {/* Upload UI for COA */}
              {showUploadUI && (
                <div className="flex justify-center my-4">
                  <div className="max-w-xs">
                    <label className="flex items-center justify-center gap-2 px-4 py-2 bg-gradient-to-r from-cyan-400 to-cyan-600 text-white text-sm rounded-lg cursor-pointer hover:from-cyan-500 hover:to-cyan-700 transition-all duration-300 shadow-sm hover:shadow-md transform hover:scale-105">
                      <svg
                        xmlns="http://www.w3.org/2000/svg"
                        className="h-4 w-4"
                        viewBox="0 0 20 20"
                        fill="currentColor"
                      >
                        <path
                          fillRule="evenodd"
                          d="M3 17a1 1 0 011-1h12a1 1 0 110 2H4a1 1 0 01-1-1zM6.293 6.707a1 1 0 010-1.414l3-3a1 1 0 011.414 0l3 3a1 1 0 01-1.414 1.414L11 5.414V13a1 1 0 11-2 0V5.414L7.707 6.707a1 1 0 01-1.414 0z"
                          clipRule="evenodd"
                        />
                      </svg>
                      Upload COA Document
                      <input
                        type="file"
                        className="hidden"
                        ref={fileInputRef}
                        onChange={(e) => {
                          const file = e.target.files?.[0];
                          if (file) handleFileUpload(file);
                        }}
                        accept=".pdf,.png,.jpg,.jpeg,.doc,.docx,.txt"
                      />
                    </label>
                  </div>
                </div>
              )}

              {/* Upload UI for HBR */}
              {showHbrUploadUI && (
                <div className="flex justify-center my-4">
                  <div className="max-w-xs">
                    <label className="flex items-center justify-center gap-2 px-4 py-2 bg-gradient-to-r from-cyan-400 to-cyan-600 text-white text-sm rounded-lg cursor-pointer hover:from-cyan-500 hover:to-cyan-700 transition-all duration-300 shadow-sm hover:shadow-md transform hover:scale-105">
                      <svg
                        xmlns="http://www.w3.org/2000/svg"
                        className="h-4 w-4"
                        viewBox="0 0 20 20"
                        fill="currentColor"
                      >
                        <path
                          fillRule="evenodd"
                          d="M3 17a1 1 0 011-1h12a1 1 0 110 2H4a1 1 0 01-1-1zM6.293 6.707a1 1 0 010-1.414l3-3a1 1 0 011.414 0l3 3a1 1 0 01-1.414 1.414L11 5.414V13a1 1 0 11-2 0V5.414L7.707 6.707a1 1 0 01-1.414 0z"
                          clipRule="evenodd"
                        />
                      </svg>
                      {hbrUploadStage === "pdf"
                        ? "Upload HBR PDF Document"
                        : "Upload HBR Excel Configuration"}
                      <input
                        type="file"
                        className="hidden"
                        ref={fileInputRef}
                        onChange={(e) => {
                          const file = e.target.files?.[0];
                          if (file) handleFileUpload(file);
                        }}
                        accept={
                          hbrUploadStage === "pdf" ? ".pdf" : ".xlsx,.xls"
                        }
                      />
                    </label>
                  </div>
                </div>
              )}

              {/* Chat loading spinner during chat switch - positioned at center of chat area */}
              {isChatLoading && (
                <div className="absolute inset-0 flex items-center justify-center pointer-events-none">
                  <div className="relative w-12 h-12">
                    <div className="absolute inset-0 border-4 border-cyan-100 rounded-full"></div>
                    <div className="absolute inset-0 border-4 border-cyan-500 border-t-transparent rounded-full animate-spin"></div>
                  </div>
                </div>
              )}

              {/* Empty state for first visit - hide during chat switching, positioned at top center */}
              {messages.length === 0 &&
                !isThinking &&
                !isFirstVisit &&
                !isChatLoading && (
                  <div className="absolute inset-x-0 top-0 flex flex-col items-center text-center py-12 animate-fadeIn">
                    <div className="w-20 h-20 bg-cyan-100 rounded-full flex items-center justify-center mb-4 shadow-inner">
                      <svg
                        xmlns="http://www.w3.org/2000/svg"
                        className="h-10 w-10 text-cyan-600"
                        fill="none"
                        viewBox="0 0 24 24"
                        stroke="currentColor"
                      >
                        <path
                          strokeLinecap="round"
                          strokeLinejoin="round"
                          strokeWidth={2}
                          d="M7 8h10M7 12h4m1 8l-4-4H5a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v8a2 2 0 01-2 2h-3l-4 4z"
                        />
                      </svg>
                    </div>
                    <h3 className="text-xl font-medium text-slate-700 mb-1">
                      Document Extraction Assistant
                    </h3>
                    <p className="text-gray-400 text-sm mb-4">Upload a document to get started</p>
                    <button
                      onClick={() => setShowCapabilitiesModal(true)}
                      className="flex items-center gap-2 text-cyan-600 hover:text-white bg-white hover:bg-cyan-600 text-sm font-medium px-4 py-2 rounded-full border border-cyan-200 shadow-sm hover:shadow-md transition-all duration-300 transform hover:scale-105"
                    >
                      <span className="text-lg">ℹ️</span>
                      Capabilities
                    </button>
                    <div
                      onClick={() => setShowAIGuidelinesModal(true)}
                      className="mt-4 p-3 bg-cyan-50 border border-cyan-200 rounded-xl text-xs text-cyan-800 flex items-start gap-2 max-w-md cursor-pointer hover:bg-cyan-100 hover:border-cyan-300 transition-all duration-200"
                    >
                      <svg className="w-4 h-4 text-cyan-500 flex-shrink-0 mt-0.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                      </svg>
                      <span>This application is <strong>non-GxP</strong> and is intended as an advisory tool only. AI is flawed, and human oversight is crucial. Please read the <strong className="underline">AbbVie AI Guidelines</strong>.</span>
                    </div>
                  </div>
                )}

              {/* OCR Processing Block - Inline in chat (hide for completed COA) */}
              {processingState.active &&
                !(
                  processingState.stage === "completed" &&
                  processingState.documentType === "coa"
                ) && (
                  <div className="flex justify-start animate-messageIn mb-4">
                    <div className="w-9 h-9 rounded-full bg-gradient-to-r from-cyan-400 to-cyan-600 flex items-center justify-center text-white text-xs font-bold mr-2 flex-shrink-0 self-start mt-1 shadow-lg ring-2 ring-white relative overflow-hidden">
                      <div className="absolute inset-0 bg-gradient-to-br from-blue-400/30 to-purple-500/30 backdrop-blur-sm"></div>
                      <span className="text-sm relative z-10">AI</span>
                    </div>
                    <div className="w-full max-w-2xl">
                      {/* Processing Container */}
                      <div
                        className={`
                    ${
                      processingState.stage === "completed" ||
                      processingState.progress === 100
                        ? "bg-cyan-50 border-cyan-500"
                        : "bg-gray-50 border-gray-300"
                    } 
                    border-[1.5px] rounded-xl p-5 transition-all duration-500 ease-in-out shadow-lg hover:shadow-xl relative overflow-hidden
                  `}
                      >
                        {/* Background shimmer effect when processing */}
                        {processingState.stage !== "completed" && (
                          <div className="absolute inset-0 bg-gradient-to-r from-transparent via-white/20 to-transparent animate-shimmer"></div>
                        )}

                        {/* Header Section */}
                        <div className="flex items-center justify-between mb-3">
                          <div className="flex items-center gap-3">
                            {/* Document Icon with background color transition */}
                            <div
                              className={`
                           w-8 h-8 rounded-lg flex items-center justify-center transition-all duration-500
                           ${
                             processingState.stage === "completed" ||
                             processingState.progress === 100
                               ? "bg-cyan-500 text-white"
                               : "bg-cyan-50 text-gray-700"
                           }
                         `}
                            >
                              <span className="text-base">📄</span>
                            </div>

                            {/* Title */}
                            <div>
                              <h3 className="text-[15px] font-semibold text-gray-800">
                                Processing{" "}
                                {processingState.fileName.length > 20
                                  ? processingState.fileName.substring(0, 20) +
                                    "..."
                                  : processingState.fileName}
                              </h3>
                            </div>
                          </div>

                          {/* Live Percentage Counter */}
                          <div className="text-right">
                            <span
                              className={`
                           text-xl font-bold transition-colors duration-300
                           ${
                             processingState.stage === "completed" ||
                             processingState.progress === 100
                               ? "text-cyan-600"
                               : "text-gray-700"
                           }
                         `}
                            >
                              {Math.floor(animatedProgress)}%
                            </span>
                          </div>
                        </div>

                        {/* File Information */}
                        <div className="mb-4">
                          <div className="flex items-center gap-2 text-sm text-gray-600">
                            <span>📄</span>
                            <span className="font-medium">
                              {processingState.fileName}
                            </span>
                            <span className="text-gray-400">•</span>
                            <span className="text-gray-500">
                              {formatFileSize(processingState.fileSize || 0)}
                            </span>
                          </div>
                        </div>

                        {/* Progress Bar Section */}
                        <div className="mb-4">
                          <div className="w-full bg-gray-200 rounded-full h-3 shadow-inner relative overflow-hidden">
                            {/* Shimmer effect overlay while processing */}
                            {processingState.stage !== "completed" &&
                              processingState.progress < 100 && (
                                <div className="absolute inset-0 bg-gradient-to-r from-transparent via-white/30 to-transparent animate-shimmer"></div>
                              )}

                            {/* Progress fill with gradient */}
                            <div
                              className={`
                            h-3 rounded-full transition-all duration-700 ease-out relative
                            ${
                              processingState.stage === "completed" ||
                              processingState.progress === 100
                                ? "bg-gradient-to-r from-cyan-400 to-cyan-600"
                                : "bg-gradient-to-r from-cyan-400 to-cyan-600"
                            }
                          `}
                              style={{ width: `${animatedProgress}%` }}
                            >
                              {/* Inner shimmer for progress bar while processing */}
                              {processingState.stage !== "completed" &&
                                processingState.progress < 100 && (
                                  <div className="absolute inset-0 bg-gradient-to-r from-transparent via-white/20 to-transparent animate-shimmer"></div>
                                )}
                            </div>
                          </div>
                        </div>

                        {/* Processing Steps Checklist - Sequential appearance */}
                        <div className="space-y-2 text-xs">
                          {(processingState.documentType === "hbr_pdf"
                            ? [
                                {
                                  step: "File upload",
                                  startThreshold: 0,
                                  completeThreshold: 60,
                                },
                                {
                                  step: "Document stored",
                                  startThreshold: 60,
                                  completeThreshold: 100,
                                },
                              ]
                            : [
                                {
                                  step: "Document extraction",
                                  startThreshold: 0,
                                  completeThreshold: 25,
                                },
                                {
                                  step: "Text recognition",
                                  startThreshold: 25,
                                  completeThreshold: 50,
                                },
                                {
                                  step: "Data processing",
                                  startThreshold: 50,
                                  completeThreshold: 75,
                                },
                                {
                                  step: "Quality validation",
                                  startThreshold: 75,
                                  completeThreshold: 100,
                                },
                              ]
                          ).map((item, index) => {
                            // Only show step if it has started or previous steps are complete
                            const shouldShow =
                              processingState.progress >= item.startThreshold;
                            const isActive =
                              processingState.progress >= item.startThreshold &&
                              processingState.progress < item.completeThreshold;
                            const isComplete =
                              processingState.progress >=
                              item.completeThreshold;

                            if (!shouldShow) return null;

                            return (
                              <div
                                key={index}
                                className="flex items-center gap-2 animate-slideInUp"
                                style={{ animationDelay: `${index * 100}ms` }}
                              >
                                <div
                                  className={`
                                w-4 h-4 rounded-full border-2 flex items-center justify-center transition-all duration-500
                                ${
                                  isComplete
                                    ? "bg-cyan-500 border-cyan-500 text-white"
                                    : isActive
                                      ? "bg-cyan-500 border-cyan-500 text-white"
                                      : "border-gray-300 bg-gray-50"
                                }
                              `}
                                >
                                  {isComplete && (
                                    <span className="text-xs font-bold">✓</span>
                                  )}
                                  {isActive && !isComplete && (
                                    <div className="w-2 h-2 border border-white border-t-transparent rounded-full animate-spin"></div>
                                  )}
                                </div>
                                <span
                                  className={`
                                transition-all duration-300
                                ${
                                  isComplete
                                    ? "text-cyan-700 font-semibold"
                                    : isActive
                                      ? "text-cyan-700 font-medium"
                                      : "text-gray-500"
                                }
                              `}
                                >
                                  {item.step}
                                </span>
                              </div>
                            );
                          })}
                        </div>
                      </div>
                    </div>
                  </div>
                )}

              {/* Invisible element to scroll to */}
              <div ref={messagesEndRef} />
            </div>
            </div>
          </div>

          {/* Scroll to bottom button - show only when user has scrolled up */}
          {userScrolling && (
            <button
              onClick={scrollToBottom}
              className="fixed bottom-24 right-8 bg-blue-600 text-white rounded-full p-3 shadow-lg hover:bg-blue-700 transition-all duration-300 animate-bounceIn z-50 group flex items-center overflow-hidden"
              aria-label="Scroll to bottom"
            >
              <div className="absolute inset-0 bg-gradient-to-br from-blue-400/30 to-purple-500/30 group-hover:scale-110 transition-all duration-500"></div>
              <div className="absolute right-full mr-3 bg-blue-600/90 backdrop-blur-sm text-white text-xs py-1.5 px-3 rounded-full whitespace-nowrap opacity-0 group-hover:opacity-100 transition-opacity duration-300 shadow-md">
                {hasNewMessages ? "View new messages" : "Return to bottom"}
              </div>
              <div className="relative z-10">
                <svg
                  xmlns="http://www.w3.org/2000/svg"
                  className="h-6 w-6"
                  viewBox="0 0 20 20"
                  fill="currentColor"
                >
                  <path
                    fillRule="evenodd"
                    d="M5.293 9.707a1 1 0 010-1.414l4-4a1 1 0 011.414 0l4 4a1 1 0 01-1.414 1.414L10 6.414l-3.293 3.293a1 1 0 01-1.414 0z"
                    clipRule="evenodd"
                    transform="rotate(180, 10, 10)"
                  />
                </svg>
                {hasNewMessages && (
                  <span className="absolute -top-1 -right-1 h-4 w-4 bg-red-500 rounded-full animate-pulse shadow-md"></span>
                )}
              </div>
              {hasNewMessages && (
                <span className="absolute -right-3 -top-3 px-2 py-0.5 bg-gradient-to-r from-red-500 to-red-600 text-white text-xs rounded-full animate-pulse shadow-md z-20">
                  {newMessagesCount}
                </span>
              )}
            </button>
          )}

          {/* Input area - Fixed at bottom */}
          <div className="border-t border-gray-200/50 bg-white backdrop-blur-sm px-4 py-4 shadow-lg relative z-30">
            <div className="max-w-3xl mx-auto">
              <div className="flex items-center rounded-xl border border-gray-300/70 bg-white/80 backdrop-blur-sm shadow-md hover:shadow-lg transition-all duration-300 focus-within:ring-2 focus-within:ring-cyan-400 focus-within:border-cyan-400 overflow-hidden">
                <input
                  type="text"
                  value={inputMessage}
                  onChange={(e) => setInputMessage(e.target.value)}
                  onKeyPress={handleKeyPress}
                  placeholder="Ask about your documents or upload a file..."
                  className="flex-1 py-3.5 px-4 outline-none rounded-l-xl text-gray-700 placeholder-gray-500 bg-transparent backdrop-blur-sm"
                  disabled={
                    isThinking ||
                    (processingState.active &&
                      processingState.stage !== "completed")
                  }
                  ref={inputRef}
                />
                <div className="flex pr-2">
                  <button
                    onClick={() => fileInputRef.current?.click()}
                    className="p-2 text-gray-500 hover:text-cyan-600 hover:bg-cyan-50/80 backdrop-blur-sm rounded-full transition-all mr-1.5 transform hover:scale-110 duration-200"
                    title="Upload document"
                    disabled={
                      isThinking ||
                      (processingState.active &&
                        processingState.stage !== "completed")
                    }
                  >
                    <svg
                      xmlns="http://www.w3.org/2000/svg"
                      className="h-5 w-5"
                      viewBox="0 0 20 20"
                      fill="currentColor"
                    >
                      <path
                        fillRule="evenodd"
                        d="M8 4a3 3 0 00-3 3v4a5 5 0 0010 0V7a1 1 0 112 0v4a7 7 0 11-14 0V7a5 5 0 0110 0v4a3 3 0 11-6 0V7a1 1 0 012 0v4a1 1 0 102 0V7a3 3 0 00-3-3z"
                        clipRule="evenodd"
                      />
                    </svg>
                  </button>
                  <input
                    type="file"
                    className="hidden"
                    ref={fileInputRef}
                    onChange={(e) => {
                      const file = e.target.files?.[0];
                      if (file) handleFileUpload(file);
                    }}
                    accept=".pdf,.png,.jpg,.jpeg,.doc,.docx,.txt"
                  />
                  <button
                    onClick={async () => {
                      if (
                        canCancel &&
                        (isThinking ||
                          (processingState.active &&
                            processingState.stage !== "completed"))
                      ) {
                        // Cancel the current process
                        await handleCancelProcess();
                      } else {
                        handleSendMessage(inputMessage);
                        setInputMessage("");
                      }
                    }}
                    className={`p-2.5 rounded-full transition-all duration-300 transform ${
                      canCancel &&
                      (isThinking ||
                        (processingState.active &&
                          processingState.stage !== "completed"))
                        ? "bg-gradient-to-r from-red-400 to-red-600 text-white hover:shadow-xl hover:scale-110 shadow-md relative overflow-hidden group animate-pulse"
                        : inputMessage.trim() &&
                            !isThinking &&
                            !processingState.active
                          ? "bg-gradient-to-r from-cyan-400 to-cyan-600 text-white hover:shadow-xl hover:scale-110 shadow-md relative overflow-hidden group"
                          : "bg-gray-200 text-gray-400 cursor-not-allowed"
                    }`}
                    disabled={
                      !canCancel &&
                      (!inputMessage.trim() ||
                        isThinking ||
                        processingState.active)
                    }
                    title={
                      canCancel &&
                      (isThinking ||
                        (processingState.active &&
                          processingState.stage !== "completed"))
                        ? "Cancel processing"
                        : "Send message"
                    }
                  >
                    {canCancel &&
                    (isThinking ||
                      (processingState.active &&
                        processingState.stage !== "completed")) ? (
                      <div className="absolute inset-0 bg-gradient-to-br from-red-400/20 via-transparent to-red-500/20 opacity-100 transition-opacity duration-700"></div>
                    ) : (
                      inputMessage.trim() &&
                      !isThinking &&
                      !processingState.active && (
                        <div className="absolute inset-0 bg-gradient-to-br from-blue-400/20 via-transparent to-purple-500/20 opacity-0 group-hover:opacity-100 transition-opacity duration-700"></div>
                      )
                    )}

                    {/* Stop icon when processing/thinking and cancellable */}
                    {canCancel &&
                    (isThinking ||
                      (processingState.active &&
                        processingState.stage !== "completed")) ? (
                      <svg
                        xmlns="http://www.w3.org/2000/svg"
                        className="h-5 w-5 relative z-10"
                        viewBox="0 0 20 20"
                        fill="currentColor"
                      >
                        <path
                          fillRule="evenodd"
                          d="M10 18a8 8 0 100-16 8 8 0 000 16zM8 7a1 1 0 00-1 1v4a1 1 0 001 1h4a1 1 0 001-1V8a1 1 0 00-1-1H8z"
                          clipRule="evenodd"
                        />
                      </svg>
                    ) : (
                      /* Send icon when normal */
                      <svg
                        xmlns="http://www.w3.org/2000/svg"
                        className="h-5 w-5 relative z-10"
                        viewBox="0 0 20 20"
                        fill="currentColor"
                      >
                        <path d="M10.894 2.553a1 1 0 00-1.788 0l-7 14a1 1 0 001.169 1.409l5-1.429A1 1 0 009 15.571V11a1 1 0 112 0v4.571a1 1 0 00.725.962l5 1.428a1 1 0 001.17-1.408l-7-14z" />
                      </svg>
                    )}
                  </button>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
      {/* End of main content wrapper */}

      <style jsx global>{`
        @keyframes fadeIn {
          from {
            opacity: 0;
          }
          to {
            opacity: 1;
          }
        }

        @keyframes messageIn {
          0% {
            opacity: 0;
            transform: translateY(10px) scale(0.98);
          }
          70% {
            opacity: 1;
            transform: translateY(-2px) scale(1.01);
          }
          100% {
            opacity: 1;
            transform: translateY(0) scale(1);
          }
        }

        @keyframes bounceIn {
          0% {
            opacity: 0;
            transform: scale(0.8);
          }
          70% {
            opacity: 1;
            transform: scale(1.1);
          }
          100% {
            opacity: 1;
            transform: scale(1);
          }
        }

        @keyframes blob1 {
          0% {
            transform: translate(0, 0) scale(1);
          }
          33% {
            transform: translate(5%, 5%) scale(1.1);
          }
          66% {
            transform: translate(-5%, 10%) scale(0.95);
          }
          100% {
            transform: translate(0, 0) scale(1);
          }
        }

        @keyframes blob2 {
          0% {
            transform: translate(0, 0) scale(1);
          }
          33% {
            transform: translate(-8%, -3%) scale(1.05);
          }
          66% {
            transform: translate(5%, -6%) scale(0.98);
          }
          100% {
            transform: translate(0, 0) scale(1);
          }
        }

        @keyframes blob3 {
          0% {
            transform: translate(0, 0) scale(1);
          }
          33% {
            transform: translate(-5%, 8%) scale(0.9);
          }
          66% {
            transform: translate(10%, -2%) scale(1.05);
          }
          100% {
            transform: translate(0, 0) scale(1);
          }
        }

        .animate-blob1 {
          animation: blob1 20s ease-in-out infinite;
        }

        .animate-blob2 {
          animation: blob2 25s ease-in-out infinite;
        }

        .animate-blob3 {
          animation: blob3 30s ease-in-out infinite;
        }

        .animate-fadeIn {
          animation: fadeIn 0.5s ease-out forwards;
        }

        .animate-messageIn {
          animation: messageIn 0.4s cubic-bezier(0.22, 1, 0.36, 1) forwards;
        }

        .animate-bounceIn {
          animation: bounceIn 0.4s cubic-bezier(0.22, 1, 0.36, 1) forwards;
        }

        @keyframes slideInUp {
          from {
            opacity: 0;
            transform: translateY(10px);
          }
          to {
            opacity: 1;
            transform: translateY(0);
          }
        }

        .animate-slideInUp {
          animation: slideInUp 0.3s ease-out forwards;
        }

        /* Scrollbar styling for Visual Audit logs */
        .scrollbar-thin::-webkit-scrollbar {
          width: 4px;
        }
        .scrollbar-thin::-webkit-scrollbar-track {
          background: transparent;
        }
        .scrollbar-thin::-webkit-scrollbar-thumb {
          background: #4b5563;
          border-radius: 2px;
        }
      `}</style>

      {/* Capabilities Modal */}
      {showCapabilitiesModal && (
        <div
          className="fixed inset-0 bg-black/60 backdrop-blur-sm flex items-center justify-center z-50 animate-fadeIn"
          onClick={() => setShowCapabilitiesModal(false)}
        >
          <div
            className="bg-white rounded-2xl shadow-2xl max-w-5xl w-full mx-4 transform animate-bounceIn overflow-hidden"
            onClick={(e) => e.stopPropagation()}
          >
            {/* Header with gradient */}
            <div className="relative bg-gradient-to-r from-cyan-500 via-cyan-600 to-blue-600 p-6 text-white overflow-hidden">
              <div className="absolute inset-0 opacity-10" style={{ backgroundImage: 'radial-gradient(circle at 25% 25%, white 1px, transparent 1px)', backgroundSize: '20px 20px' }}></div>
              <button
                onClick={() => setShowCapabilitiesModal(false)}
                className="absolute top-4 right-4 text-white/80 hover:text-white transition-colors"
              >
                <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
              <div className="relative">
                <div className="w-14 h-14 bg-white/20 rounded-xl flex items-center justify-center mb-4 backdrop-blur-sm">
                  <svg className="w-8 h-8 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z" />
                  </svg>
                </div>
                <h2 className="text-2xl font-bold tracking-tight">System Capabilities</h2>
                <p className="text-cyan-100 mt-1">Intelligent document extraction & verification</p>
              </div>
            </div>

            {/* Content */}
            <div className="p-6">
              {/* Platform Description */}
              <div className="mb-5 p-4 bg-slate-50 rounded-xl border border-slate-100 text-sm text-slate-700 leading-relaxed">
                This platform is a self-service, prompt-driven chatbot designed to intelligently extract and structure information from complex documents such as paper batch records, Certificates of Analysis (COAs), manufacturing records, and laboratory analysis reports. Users can simply provide prompts or ask questions in natural language, and the system automatically processes multi-page documents to identify and extract relevant parameters. It provides visual verification of extracted values, enabling users to trace results back to their exact location in the source document for accuracy and transparency. The system also learns from previous extractions to improve performance over time and allows results to be exported into structured formats like Excel for downstream analysis.
              </div>

              <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                {/* Capability 1 */}
                <div className="group p-4 rounded-xl border border-gray-100 hover:border-cyan-200 hover:bg-gradient-to-br hover:from-cyan-50 hover:to-white transition-all duration-300">
                  <div className="w-10 h-10 bg-cyan-100 rounded-lg flex items-center justify-center mb-3 group-hover:bg-cyan-500 group-hover:text-white transition-colors">
                    <svg className="w-5 h-5 text-cyan-600 group-hover:text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                    </svg>
                  </div>
                  <h3 className="font-semibold text-gray-900 mb-1">Multi-Page Extraction</h3>
                  <p className="text-sm text-gray-500">Process 100+ pages simultaneously with intelligent data recognition</p>
                </div>

                {/* Capability 2 */}
                <div className="group p-4 rounded-xl border border-gray-100 hover:border-cyan-200 hover:bg-gradient-to-br hover:from-cyan-50 hover:to-white transition-all duration-300">
                  <div className="w-10 h-10 bg-emerald-100 rounded-lg flex items-center justify-center mb-3 group-hover:bg-emerald-500 group-hover:text-white transition-colors">
                    <svg className="w-5 h-5 text-emerald-600 group-hover:text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
                    </svg>
                  </div>
                  <h3 className="font-semibold text-gray-900 mb-1">Visual Verification</h3>
                  <p className="text-sm text-gray-500">Click any value to see its exact source with highlighted bounding boxes</p>
                </div>

                {/* Capability 3 */}
                <div className="group p-4 rounded-xl border border-gray-100 hover:border-cyan-200 hover:bg-gradient-to-br hover:from-cyan-50 hover:to-white transition-all duration-300">
                  <div className="w-10 h-10 bg-violet-100 rounded-lg flex items-center justify-center mb-3 group-hover:bg-violet-500 group-hover:text-white transition-colors">
                    <svg className="w-5 h-5 text-violet-600 group-hover:text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
                    </svg>
                  </div>
                  <h3 className="font-semibold text-gray-900 mb-1">Excel Export</h3>
                  <p className="text-sm text-gray-500">Export structured data directly to Excel with custom headers</p>
                </div>

                {/* Capability 4 */}
                <div className="group p-4 rounded-xl border border-gray-100 hover:border-cyan-200 hover:bg-gradient-to-br hover:from-cyan-50 hover:to-white transition-all duration-300">
                  <div className="w-10 h-10 bg-amber-100 rounded-lg flex items-center justify-center mb-3 group-hover:bg-amber-500 group-hover:text-white transition-colors">
                    <svg className="w-5 h-5 text-amber-600 group-hover:text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 10V3L4 14h7v7l9-11h-7z" />
                    </svg>
                  </div>
                  <h3 className="font-semibold text-gray-900 mb-1">Pattern Learning</h3>
                  <p className="text-sm text-gray-500">System learns from successful extractions for improved accuracy</p>
                </div>

                {/* Capability 5 */}
                <div className="group p-4 rounded-xl border border-gray-100 hover:border-cyan-200 hover:bg-gradient-to-br hover:from-cyan-50 hover:to-white transition-all duration-300">
                  <div className="w-10 h-10 bg-rose-100 rounded-lg flex items-center justify-center mb-3 group-hover:bg-rose-500 group-hover:text-white transition-colors">
                    <svg className="w-5 h-5 text-rose-600 group-hover:text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2m-3 7h3m-3 4h3m-6-4h.01M9 16h.01" />
                    </svg>
                  </div>
                  <h3 className="font-semibold text-gray-900 mb-1">Batch Parameter Extraction</h3>
                  <p className="text-sm text-gray-500">Extract multiple parameters at once and export structured results</p>
                </div>

                {/* Capability 6 */}
                <div className="group p-4 rounded-xl border border-gray-100 hover:border-cyan-200 hover:bg-gradient-to-br hover:from-cyan-50 hover:to-white transition-all duration-300">
                  <div className="w-10 h-10 bg-sky-100 rounded-lg flex items-center justify-center mb-3 group-hover:bg-sky-500 group-hover:text-white transition-colors">
                    <svg className="w-5 h-5 text-sky-600 group-hover:text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z" />
                    </svg>
                  </div>
                  <h3 className="font-semibold text-gray-900 mb-1">Natural Language Queries</h3>
                  <p className="text-sm text-gray-500">Ask questions in plain language - no technical knowledge required</p>
                </div>
              </div>

              {/* Footer */}
              <div className="mt-6 pt-4 border-t border-gray-100 flex justify-end">
                <button
                  onClick={() => setShowCapabilitiesModal(false)}
                  className="px-5 py-2 bg-gradient-to-r from-cyan-500 to-cyan-600 text-white text-sm font-medium rounded-lg hover:from-cyan-600 hover:to-cyan-700 transition-all duration-300 shadow-md hover:shadow-lg"
                >
                  Got it
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* AbbVie AI Guidelines Modal */}
      {showAIGuidelinesModal && (
        <div
          className="fixed inset-0 bg-black/60 backdrop-blur-sm flex items-center justify-center z-50 animate-fadeIn"
          onClick={() => setShowAIGuidelinesModal(false)}
        >
          <div
            className="bg-white rounded-2xl shadow-2xl max-w-2xl w-full mx-4 transform animate-bounceIn overflow-hidden max-h-[85vh] flex flex-col"
            onClick={(e) => e.stopPropagation()}
          >
            {/* Header with cyan gradient */}
            <div className="relative bg-gradient-to-r from-cyan-500 via-cyan-600 to-blue-600 p-6 text-white overflow-hidden flex-shrink-0">
              <div className="absolute inset-0 opacity-10" style={{ backgroundImage: 'radial-gradient(circle at 25% 25%, white 1px, transparent 1px)', backgroundSize: '20px 20px' }}></div>
              <button
                onClick={() => setShowAIGuidelinesModal(false)}
                className="absolute top-4 right-4 text-white/80 hover:text-white transition-colors"
              >
                <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
              <div className="relative">
                <div className="w-14 h-14 bg-white/20 rounded-xl flex items-center justify-center mb-4 backdrop-blur-sm">
                  <svg className="w-8 h-8 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z" />
                  </svg>
                </div>
                <h2 className="text-2xl font-bold tracking-tight">AbbVie AI Terms of Use</h2>
              </div>
            </div>

            {/* Content - scrollable */}
            <div className="p-6 overflow-y-auto flex-1">
              <div className="space-y-4 text-sm text-slate-700 leading-relaxed">
                <div className="flex items-start gap-3 p-3 bg-cyan-50/50 rounded-lg border border-cyan-100">
                  <svg className="w-5 h-5 text-cyan-500 flex-shrink-0 mt-0.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                  </svg>
                  <p className="text-slate-800 font-medium">All technologies are governed in line with our core values, Code of Business Ethics, and internal policies.</p>
                </div>

                <div className="flex items-start gap-3 p-3 rounded-lg hover:bg-slate-50 transition-colors">
                  <span className="w-5 h-5 bg-cyan-100 text-cyan-600 rounded-full flex items-center justify-center flex-shrink-0 mt-0.5 text-xs font-bold">1</span>
                  <p>This tool is hosted within a secure AbbVie environment. All output should be considered &lsquo;Internal Use Only&rsquo;. Input data up to and including &lsquo;Restricted&rsquo; classifications are supported. <strong className="text-red-600">Do not upload Secret data</strong> (i.e., information containing PHI, IP, trade secrets, or U.S. export-controlled information).</p>
                </div>

                <div className="flex items-start gap-3 p-3 rounded-lg hover:bg-slate-50 transition-colors">
                  <span className="w-5 h-5 bg-cyan-100 text-cyan-600 rounded-full flex items-center justify-center flex-shrink-0 mt-0.5 text-xs font-bold">2</span>
                  <p><strong>Information from this tool should not be used to make Quality or GxP decisions.</strong> Users attest they are responsible for the final decision-making and will be held accountable accordingly.</p>
                </div>

                <div className="flex items-start gap-3 p-3 rounded-lg hover:bg-slate-50 transition-colors">
                  <span className="w-5 h-5 bg-cyan-100 text-cyan-600 rounded-full flex items-center justify-center flex-shrink-0 mt-0.5 text-xs font-bold">3</span>
                  <p>Users are responsible for ensuring the accuracy and legality of the input data they provide and are responsible for utilizing the tool in compliance with their local regulations.</p>
                </div>

                <div className="flex items-start gap-3 p-3 rounded-lg hover:bg-slate-50 transition-colors">
                  <span className="w-5 h-5 bg-cyan-100 text-cyan-600 rounded-full flex items-center justify-center flex-shrink-0 mt-0.5 text-xs font-bold">4</span>
                  <p>Information received from this tool should be considered <strong>exploratory and hypothesis-generating only</strong>.</p>
                </div>

                <div className="flex items-start gap-3 p-3 rounded-lg hover:bg-slate-50 transition-colors">
                  <span className="w-5 h-5 bg-cyan-100 text-cyan-600 rounded-full flex items-center justify-center flex-shrink-0 mt-0.5 text-xs font-bold">5</span>
                  <p>This tool is built on data available in the public domain through 2023. Information and detailed context on recent events (internal or external) will not be available unless otherwise noted.</p>
                </div>

                <div className="flex items-start gap-3 p-3 rounded-lg hover:bg-slate-50 transition-colors">
                  <span className="w-5 h-5 bg-cyan-100 text-cyan-600 rounded-full flex items-center justify-center flex-shrink-0 mt-0.5 text-xs font-bold">6</span>
                  <p>This tool can sometimes write plausible-sounding but incorrect or nonsensical answers (termed <strong>Hallucinations and Epiphanies</strong>).</p>
                </div>

                <div className="flex items-start gap-3 p-3 rounded-lg hover:bg-slate-50 transition-colors">
                  <span className="w-5 h-5 bg-cyan-100 text-cyan-600 rounded-full flex items-center justify-center flex-shrink-0 mt-0.5 text-xs font-bold">7</span>
                  <p>This tool is continuously evolving, meaning the quality of responses will change over time.</p>
                </div>

                <div className="flex items-start gap-3 p-3 rounded-lg hover:bg-slate-50 transition-colors">
                  <span className="w-5 h-5 bg-cyan-100 text-cyan-600 rounded-full flex items-center justify-center flex-shrink-0 mt-0.5 text-xs font-bold">8</span>
                  <p>The AI models behind this tool are not deterministic but rather probabilistic, meaning responses are expected to vary even with input text staying the same.</p>
                </div>

                <div className="flex items-start gap-3 p-3 rounded-lg hover:bg-slate-50 transition-colors">
                  <span className="w-5 h-5 bg-cyan-100 text-cyan-600 rounded-full flex items-center justify-center flex-shrink-0 mt-0.5 text-xs font-bold">9</span>
                  <p>User activity monitoring is employed to improve performance of the tool, identify new functionality, and monitor data use.</p>
                </div>

                <div className="flex items-start gap-3 p-3 rounded-lg hover:bg-slate-50 transition-colors">
                  <span className="w-5 h-5 bg-cyan-100 text-cyan-600 rounded-full flex items-center justify-center flex-shrink-0 mt-0.5 text-xs font-bold">10</span>
                  <p>There is a cost associated to running this tool. Through 2024, BTS is providing access to this tool with no charges to better understand the cost-benefit ratio as we enter 2025.</p>
                </div>

                <div className="flex items-start gap-3 p-3 rounded-lg hover:bg-slate-50 transition-colors">
                  <span className="w-5 h-5 bg-cyan-100 text-cyan-600 rounded-full flex items-center justify-center flex-shrink-0 mt-0.5 text-xs font-bold">11</span>
                  <p>The accuracy of the output may vary depending on the selected LLM model.</p>
                </div>
              </div>

              {/* Footer */}
              <div className="mt-6 pt-4 border-t border-gray-100 flex justify-end">
                <button
                  onClick={() => setShowAIGuidelinesModal(false)}
                  className="px-5 py-2 bg-gradient-to-r from-cyan-500 to-cyan-600 text-white text-sm font-medium rounded-lg hover:from-cyan-600 hover:to-cyan-700 transition-all duration-300 shadow-md hover:shadow-lg"
                >
                  I Understand
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Feedback Modal */}
      {showFeedbackModal && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 animate-fadeIn">
          <div className="bg-white rounded-lg shadow-xl max-w-md w-full mx-4 transform animate-bounceIn">
            {/* Header Bar */}
            <div className="flex justify-between items-center p-4 border-b border-gray-200">
              <h2 className="text-lg font-semibold text-gray-800">
                Share Your Feedback
              </h2>
              <button
                onClick={handleFeedbackClose}
                className="text-gray-400 hover:text-gray-600 transition-colors"
              >
                <svg
                  className="w-6 h-6"
                  fill="none"
                  stroke="currentColor"
                  viewBox="0 0 24 24"
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth={2}
                    d="M6 18L18 6M6 6l12 12"
                  />
                </svg>
              </button>
            </div>

            <div className="p-4 space-y-4">
              {/* Document Badge */}
              <div className="inline-block bg-blue-100 text-blue-800 px-3 py-1 rounded-full text-sm font-medium">
                📄 Current:{" "}
                {currentDocumentType === "coa"
                  ? "COA Document"
                  : currentDocumentType === "hbr" ||
                      currentDocumentType === "hbr_multiagent"
                    ? "HBR Document"
                    : "No Document"}
              </div>

              {/* Rating Section */}
              <div>
                <h3 className="text-sm font-medium text-gray-700 mb-2">
                  How was your experience?
                </h3>
                <div className="flex space-x-2">
                  <button
                    onClick={() => setFeedbackRating("great")}
                    className={`flex-1 p-3 rounded-lg border text-center transition-colors ${
                      feedbackRating === "great"
                        ? "border-green-500 bg-green-50 text-green-700"
                        : "border-gray-300 hover:border-green-300 hover:bg-green-50"
                    }`}
                  >
                    <div className="text-2xl mb-1">😊</div>
                    <div className="text-sm font-medium">Great</div>
                  </button>
                  <button
                    onClick={() => setFeedbackRating("okay")}
                    className={`flex-1 p-3 rounded-lg border text-center transition-colors ${
                      feedbackRating === "okay"
                        ? "border-yellow-500 bg-yellow-50 text-yellow-700"
                        : "border-gray-300 hover:border-yellow-300 hover:bg-yellow-50"
                    }`}
                  >
                    <div className="text-2xl mb-1">😐</div>
                    <div className="text-sm font-medium">Okay</div>
                  </button>
                  <button
                    onClick={() => setFeedbackRating("poor")}
                    className={`flex-1 p-3 rounded-lg border text-center transition-colors ${
                      feedbackRating === "poor"
                        ? "border-red-500 bg-red-50 text-red-700"
                        : "border-gray-300 hover:border-red-300 hover:bg-red-50"
                    }`}
                  >
                    <div className="text-2xl mb-1">😞</div>
                    <div className="text-sm font-medium">Poor</div>
                  </button>
                </div>
              </div>

              {/* Error Reporting (Only show for HBR) */}
              {(currentDocumentType === "hbr" ||
                currentDocumentType === "hbr_multiagent") && (
                <div className="bg-yellow-50 border border-yellow-200 rounded-lg p-3">
                  <label className="flex items-center space-x-2 cursor-pointer">
                    <input
                      type="checkbox"
                      checked={reportErrors}
                      onChange={(e) => setReportErrors(e.target.checked)}
                      className="w-4 h-4 text-yellow-600 border-yellow-300 rounded focus:ring-yellow-500"
                    />
                    <span className="text-sm font-medium text-yellow-800">
                      ☐ Report extraction errors
                    </span>
                  </label>
                  {reportErrors && (
                    <textarea
                      value={errorDetails}
                      onChange={(e) => setErrorDetails(e.target.value)}
                      placeholder="Which values were incorrect?"
                      className="mt-2 w-full px-3 py-2 border border-yellow-300 rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-yellow-500 focus:border-transparent"
                      rows={3}
                    />
                  )}
                </div>
              )}

              {/* Comments Box */}
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  Additional comments
                </label>
                <textarea
                  value={additionalComments}
                  onChange={(e) => setAdditionalComments(e.target.value)}
                  placeholder="Share any thoughts or suggestions..."
                  className="w-full px-3 py-2 border border-gray-300 rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-cyan-500 focus:border-transparent"
                  rows={3}
                />
              </div>

              {/* Submit Button */}
              <button
                onClick={handleFeedbackSubmit}
                className="w-full py-3 px-4 rounded-md text-white font-medium transition-colors bg-cyan-500 hover:bg-cyan-600 focus:ring-2 focus:ring-cyan-500 focus:ring-offset-2"
              >
                Submit Feedback
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Success Toast */}
      {showSuccessToast && (
        <div className="fixed top-4 right-4 bg-green-500 text-white px-6 py-3 rounded-lg shadow-lg z-50 animate-bounceIn">
          <div className="flex items-center space-x-2">
            <svg
              className="w-5 h-5"
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M5 13l4 4L19 7"
              />
            </svg>
            <span className="font-medium">
              ✓ Feedback submitted successfully!
            </span>
          </div>
        </div>
      )}

      {/* COA Chat Panel - Slide in from right */}
      {showCoAChat && (
        <div className="fixed inset-0 z-[100] flex">
          {/* Backdrop */}
          <div
            className="flex-1 bg-black/30 backdrop-blur-sm"
            onClick={closeCoAChat}
          />

          {/* Chat Panel */}
          <div className="w-full max-w-md lg:max-w-lg bg-white shadow-2xl flex flex-col animate-slideInRight">
            {/* Header */}
            <div className="bg-gradient-to-r from-cyan-500 to-cyan-600 text-white px-6 py-4 flex items-center justify-between">
              <div>
                <h2 className="text-lg font-semibold">COA Data Chat</h2>
                <p className="text-cyan-100 text-sm mt-0.5">
                  Ask questions about the extracted data
                </p>
              </div>
              <button
                onClick={closeCoAChat}
                className="p-2 hover:bg-white/20 rounded-lg transition-colors"
              >
                <svg
                  className="w-5 h-5"
                  fill="none"
                  stroke="currentColor"
                  viewBox="0 0 24 24"
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth={2}
                    d="M6 18L18 6M6 6l12 12"
                  />
                </svg>
              </button>
            </div>

            {/* Chat Messages */}
            <div className="flex-1 overflow-y-auto p-4 space-y-4">
              {coaChatMessages.map((message, index) => (
                <div
                  key={index}
                  className={`flex ${
                    message.role === "user" ? "justify-end" : "justify-start"
                  }`}
                >
                  <div
                    className={`max-w-[80%] px-4 py-2.5 rounded-lg ${
                      message.role === "user"
                        ? "bg-cyan-500 text-white"
                        : "bg-gray-100 text-gray-800"
                    }`}
                  >
                    <p className="text-sm whitespace-pre-wrap">
                      {message.content}
                      {/* Show blinking cursor while streaming */}
                      {message.isStreaming && (
                        <span className="inline-block w-2 h-4 ml-1 bg-gray-500 animate-pulse" />
                      )}
                    </p>
                  </div>
                </div>
              ))}
              {/* Show loading dots only before first chunk arrives */}
              {coaChatLoading &&
                coaChatMessages.length > 0 &&
                coaChatMessages[coaChatMessages.length - 1]?.content === "" &&
                coaChatMessages[coaChatMessages.length - 1]?.isStreaming && (
                  <div className="flex justify-start">
                    <div className="bg-gray-100 px-4 py-3 rounded-lg">
                      <div className="flex space-x-2">
                        <div className="w-2 h-2 bg-gray-500 rounded-full animate-bounce"></div>
                        <div
                          className="w-2 h-2 bg-gray-500 rounded-full animate-bounce"
                          style={{ animationDelay: "0.1s" }}
                        ></div>
                        <div
                          className="w-2 h-2 bg-gray-500 rounded-full animate-bounce"
                          style={{ animationDelay: "0.2s" }}
                        ></div>
                      </div>
                    </div>
                  </div>
                )}
            </div>

            {/* Quick Actions */}
            <div className="border-t px-4 py-3">
              <div className="flex gap-2 flex-wrap mb-3">
                <button
                  onClick={() =>
                    sendCoAChatMessage("Summarize the test results")
                  }
                  className="px-3 py-1.5 bg-gray-100 text-gray-700 rounded-full text-sm hover:bg-gray-200 transition-colors"
                  disabled={coaChatLoading}
                >
                  Summarize Results
                </button>
                <button
                  onClick={() =>
                    sendCoAChatMessage("What are the product details?")
                  }
                  className="px-3 py-1.5 bg-gray-100 text-gray-700 rounded-full text-sm hover:bg-gray-200 transition-colors"
                  disabled={coaChatLoading}
                >
                  Product Info
                </button>
                <button
                  onClick={() =>
                    sendCoAChatMessage("Are all tests within specification?")
                  }
                  className="px-3 py-1.5 bg-gray-100 text-gray-700 rounded-full text-sm hover:bg-gray-200 transition-colors"
                  disabled={coaChatLoading}
                >
                  Check Specs
                </button>
              </div>
            </div>

            {/* Input Area */}
            <div className="border-t px-4 py-4">
              <form
                onSubmit={(e) => {
                  e.preventDefault();
                  const input = e.currentTarget.querySelector(
                    "input",
                  ) as HTMLInputElement;
                  if (input?.value.trim()) {
                    sendCoAChatMessage(input.value);
                    input.value = "";
                  }
                }}
                className="flex gap-2"
              >
                <input
                  type="text"
                  placeholder="Ask a question about the COA data..."
                  className="flex-1 px-4 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-cyan-500 focus:border-transparent"
                  disabled={coaChatLoading}
                />
                <button
                  type="submit"
                  className="px-4 py-2 bg-cyan-500 text-white rounded-lg hover:bg-cyan-600 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                  disabled={coaChatLoading}
                >
                  <svg
                    className="w-5 h-5"
                    fill="none"
                    stroke="currentColor"
                    viewBox="0 0 24 24"
                  >
                    <path
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      strokeWidth={2}
                      d="M12 19l9 2-9-18-9 18 9-2zm0 0v-8"
                    />
                  </svg>
                </button>
              </form>
            </div>
          </div>
        </div>
      )}

      {/* Phase 5: PDF Viewer Panel for bbox highlighting */}
      {/* Only load PDFPanel when actually needed - prevents unnecessary dynamic import loading */}
      {coaProcessId && showPDFPanel && (
        <PDFPanel
          processId={coaProcessId}
          documentName={activeDocumentName || "Document"}
          isOpen={showPDFPanel}
          onClose={() => {
            setShowPDFPanel(false);
            setPdfHighlights([]);
            setPdfPanelWidth(50); // Reset to default width
          }}
          highlights={pdfHighlights.map(ref => ({
            page: ref.page,
            bbox: ref.bbox,
            text: ref.text,
            type: ref.type as "cell" | "line" | "table_layout" | undefined,
            highlight_type: ref.highlight_type as "error" | "info" | undefined
          }))}
          initialPage={pdfInitialPage}
          onWidthChange={setPdfPanelWidth}
          scanningPages={visualAuditState.active ? visualAuditState.pages : []}
          scanningStage={visualAuditState.active ? visualAuditState.stage : undefined}
        />
      )}

      {/* Schema Panel - slide-in from right */}
      {showSchemaPanel && (
        <SchemaPanel
          onClose={() => setShowSchemaPanel(false)}
          onSchemaSelect={(schema) => {
            console.log("Schema selected:", schema.name, schema.parameters);
          }}
        />
      )}

      {/* TEST MODE: PDF Panel Test for debugging bbox positioning */}
      {coaProcessId && activeDocumentName && (
        <PDFPanelTest
          pdfUrl={`${API_BASE_URL}/temp/${encodeURIComponent(activeDocumentName.replace(/\.pdf$/i, '').replace(/\s+/g, '_').replace(/[()]/g, '').replace(/[^a-zA-Z0-9_\-]/g, '_').replace(/_+/g, '_').replace(/_+$/, ''))}.pdf`}
          documentName={activeDocumentName}
          isOpen={showTestPanel}
          onClose={() => setShowTestPanel(false)}
        />
      )}

    </div>
  );
}
