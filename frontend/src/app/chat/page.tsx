"use client";
import { useEffect, useState, useRef } from "react";
import React from "react";
import { useRouter } from "next/navigation";

// Environment Configuration - Comment/Uncomment as needed
//const API_BASE_URL = "http://localhost:5000"; // Local development
const API_BASE_URL =
  "https://dev.aiparser.ir-bioprocess-poc.awscloud.abbvienet.com"; // Dev environment (via nginx proxy)

// Import the agent service and file utilities
import { agent } from "../../services/agent";
import { extractTextFromFile, cancelProcess } from "../../services/fileUtils";

type Message = {
  id: string;
  content: string;
  role: "user" | "assistant" | "system";
  timestamp: Date;
  isNew?: boolean;
  // For COA extraction status messages
  extractionStatus?: {
    processId: string;
    fileName: string;
    enhancedFileName?: string;
    stage: "completed";
    documentType: "coa";
  };
};

// Function to render message with formatted links
const renderMessageWithLinks = (
  text: string,
  messageId: string,
  setMessagesCallback?: React.Dispatch<React.SetStateAction<Message[]>>
) => {
  // Remove action markers from display
  text = text.replace(/\[ACTION:SHOW_COA_UPLOAD\]/g, "");
  text = text.replace(/\[ACTION:SHOW_HBR_UPLOAD\]/g, "");

  // Process markdown formatting - convert **bold** to HTML
  text = text.replace(
    /\*\*(.*?)\*\*/g,
    '<strong class="font-semibold">$1</strong>'
  );

  // First, let's extract all download links and replace them with special markers
  const downloadLinks: Array<{ text: string; url: string }> = [];
  let linkCounter = 0;

  // Process download section headers
  text = text.replace(
    /### Download Processed Files/g,
    '<div class="download-section-header">📥 Download Processed Files</div>'
  );

  text = text.replace(
    /### Download Sample Template/g,
    '<div class="download-section-header">📄 Download Sample Template</div>'
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
    }
  );

  // Process direct download buttons
  text = text.replace(
    /<div class="direct-download-button" data-url="([^"]+)" data-filename="([^"]+)">([^<]+)<\/div>/g,
    (match, url, filename, buttonText) => {
      const id = `download-button-${messageId}-${linkCounter++}`;
      downloadLinks.push({ text: buttonText, url });
      return `<download-button-placeholder id="${id}"></download-button-placeholder>`;
    }
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
            dangerouslySetInnerHTML={{ __html: textBefore }}
          />
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
        </a>
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
            dangerouslySetInnerHTML={{ __html: textBefore }}
          />
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
        </button>
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
        missingParamMatch.index
      );
      if (textBefore) {
        parts.push(
          <span
            key={`${messageId}-text-${partIndex++}`}
            dangerouslySetInnerHTML={{ __html: textBefore }}
          />
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
            const { handleHbrParameterFeedback } = await import(
              "../../services/fileUtils"
            );

            // Request feedback from the backend
            const feedbackResponse = await handleHbrParameterFeedback(
              sessionId,
              parameter,
              `I need help finding the parameter: ${parameter}`
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
      </button>
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
            dangerouslySetInnerHTML={{ __html: textBefore }}
          />
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
            `Reprocessing parameter: ${parameter} with hint: ${userHint}`
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
            const { handleHbrParameterReprocess } = await import(
              "../../services/fileUtils"
            );

            // Request reprocessing from the backend
            const reprocessResponse = await handleHbrParameterReprocess(
              sessionId,
              parameter,
              userHint,
              recommendedPages
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
      </button>
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
          dangerouslySetInnerHTML={{ __html: remainingText }}
        />
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
        }
      );

      return (
        <span
          key={part.key}
          dangerouslySetInnerHTML={{ __html: processedHtml }}
        />
      );
    }
    return part;
  });

  return <>{remainingParts}</>;
};

/**
 * Loading indicator component
 */
const LoadingDots = () => (
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
);

/**
 * Dashboard page component
 * Handles chat interface and file uploads
 */
export default function Dashboard() {
  const [user, setUser] = useState<{ username: string; email: string } | null>(
    null
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
    Array<{ role: "user" | "assistant"; content: string; timestamp: Date }>
  >([]);
  const [coaChatLoading, setCoaChatLoading] = useState(false);

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

  // Smooth progress animation states
  const [animatedProgress, setAnimatedProgress] = useState(0);
  const progressAnimationRef = useRef<NodeJS.Timeout | null>(null);

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

  const messagesEndRef = useRef<HTMLDivElement>(null);
  const chatContainerRef = useRef<HTMLDivElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const scrollTimeoutRef = useRef<NodeJS.Timeout | null>(null);
  const router = useRouter();

  // Focus input on load
  useEffect(() => {
    if (!loading && inputRef.current) {
      inputRef.current.focus();
    }
  }, [loading]);

  // Handle scroll events in the chat container
  useEffect(() => {
    const chatContainer = chatContainerRef.current;
    if (!chatContainer) return;

    const handleScroll = () => {
      if (!chatContainer) return;

      const distanceFromBottom =
        chatContainer.scrollHeight -
        chatContainer.scrollTop -
        chatContainer.clientHeight;

      const isRecentUserMessage = Date.now() - lastUserMessageTime < 10000; // 10 seconds

      // Only block auto-scroll if:
      // 1. User scrolled far from bottom (reading history)
      // 2. AND hasn't sent a message recently
      if (distanceFromBottom > 200 && !isRecentUserMessage) {
        setUserScrolling(true);
      } else {
        // Resume auto-scroll if near bottom OR sent message recently
        setUserScrolling(false);
      }
    };

    chatContainer.addEventListener("scroll", handleScroll);

    return () => {
      chatContainer.removeEventListener("scroll", handleScroll);
    };
  }, [lastUserMessageTime]);

  // Create a separate effect for auto-scrolling for new messages
  useEffect(() => {
    // Don't auto-scroll if user is viewing history
    if (userScrolling) {
      // If user is scrolling up, don't interfere at all
      return;
    }

    // Find any new messages
    const hasNewMessages = messages.some((msg) => msg.isNew);

    // Auto-scroll for new messages
    if (hasNewMessages) {
      const scrollTimeout = setTimeout(() => {
        const isRecentUserMessage = Date.now() - lastUserMessageTime < 10000; // 10 seconds

        // ALWAYS scroll if:
        // 1. User sent message recently (active conversation)
        // 2. OR user is not manually reading history
        if (isRecentUserMessage || !userScrolling) {
          messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
        }
      }, 100);

      return () => clearTimeout(scrollTimeout);
    }
  }, [messages, userScrolling]);

  // Separate effect just for marking messages as seen
  useEffect(() => {
    // Check if there are any new messages when the user is scrolling
    if (userScrolling && messages.some((msg) => msg.isNew)) {
      setHasNewMessages(true);
    }

    // Mark new messages as seen after they appear (only if not scrolling)
    if (!userScrolling) {
      const timer = setTimeout(() => {
        setMessages((prev) =>
          prev.map((msg) => (msg.isNew ? { ...msg, isNew: false } : msg))
        );
        setHasNewMessages(false);
      }, 300); // Increased from 200ms to 300ms

      return () => clearTimeout(timer);
    }
  }, [messages, userScrolling]);

  // Auto-scroll when processing state becomes active
  useEffect(() => {
    if (processingState.active) {
      // Auto-scroll to show the processing block
      setTimeout(() => {
        messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
        setUserScrolling(false);
      }, 200); // Small delay to ensure processing block is rendered
    }
  }, [processingState.active]);

  // Function to manually scroll to bottom
  const scrollToBottom = () => {
    // This is an explicit user action to scroll to bottom
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });

    // Only after explicit user action, we can reset this
    setUserScrolling(false);
    setHasNewMessages(false);

    // Mark all messages as seen
    setMessages((prev) =>
      prev.map((msg) => (msg.isNew ? { ...msg, isNew: false } : msg))
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
        // Ensure loading screen is visible for at least 1.5 seconds
        const elapsedTime = Date.now() - startTime;
        const minLoadingTime = 500; // 1.5 seconds

        if (elapsedTime < minLoadingTime) {
          setTimeout(() => {
            setLoading(false);
          }, minLoadingTime - elapsedTime);
        } else {
          setLoading(false);
        }
      }
    };

    checkAuth();
  }, [router]);

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

  // Feedback modal handlers
  const handleFeedbackOpen = () => {
    setShowFeedbackModal(true);
  };

  const handleFeedbackClose = () => {
    setShowFeedbackModal(false);
    // Reset form
    setFeedbackRating(null);
    setReportErrors(false);
    setErrorDetails("");
    setAdditionalComments("");
  };

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
        subject
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
    isAssistantResponse: boolean = false
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
      lowerMessage.includes(keyword)
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
    isAssistantResponse: boolean = false
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
      lowerMessage.includes(keyword)
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
        lowerMessage === greeting || lowerMessage.startsWith(greeting + " ")
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
          "⚠️ Cancellation disabled for HBR documents (multi-agent processing)"
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
          "🔄 Cancelling temporary process ID (before backend response)"
        );
        // For temporary IDs, we can't cancel on backend yet, just reset UI
        console.log(
          "⚠️ Early cancellation - backend process hasn't started yet"
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
  const handleSendMessage = async (message: string) => {
    if (!message.trim()) return;

    // Add user message to chat
    const userMessage: Message = {
      id: Date.now().toString(),
      content: message,
      role: "user",
      timestamp: new Date(),
    };
    setMessages((prev) => [...prev, userMessage]);

    // Update timestamp for user message (for auto-scroll logic)
    setLastUserMessageTime(Date.now());

    // ALWAYS scroll to bottom after user message
    setTimeout(() => {
      messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
      setUserScrolling(false);
    }, 100);

    // Hide upload UI while waiting for response
    setShowUploadUI(false);
    setShowHbrUploadUI(false);

    // Show loading indicator only if we're not already showing processing state
    if (!processingState.active) {
      setIsLoading(true);
    }

    // Check if the message is a greeting
    const isUserGreeting = isGreeting(message);

    // Let the Claude agent handle all intelligence - no hardcoded detection

    // Process the message through the agent
    try {
      const response = await agent.processMessage(message);

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

      // Only add the agent message if it's not just an action marker
      const cleanResponse = response
        .replace(/\[ACTION:SHOW_HBR_MULTIAGENT_UPLOAD\]/g, "")
        .replace(/\[ACTION:SHOW_HBR_UPLOAD\]/g, "")
        .replace(/\[ACTION:SHOW_COA_UPLOAD\]/g, "")
        .replace(/\[ACTION:SHOW_HBR_TEMPLATE\]/g, "")
        .trim();

      if (cleanResponse) {
        // Filter out cancellation-related messages
        const lowerResponse = cleanResponse.toLowerCase();
        if (
          lowerResponse.includes("cancelled by user") ||
          lowerResponse.includes("process cancelled")
        ) {
          console.log("Filtering out cancellation message from agent response");
        } else {
          const agentMessage: Message = {
            id: (Date.now() + 1).toString(),
            content: cleanResponse,
            role: "assistant",
            timestamp: new Date(),
          };
          setMessages((prev) => [...prev, agentMessage]);

          // ALWAYS scroll to bottom after AI response
          setTimeout(() => {
            messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
            setUserScrolling(false);
          }, 100);
        }
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
        /<hbr_process_id>(.*?)<\/hbr_process_id>/
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
  };

  /**
   * Handle HBR template download - provide a downloadable link instead of auto-download
   */
  const handleHbrTemplateDownload = async () => {
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
        messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
        setUserScrolling(false);
      }, 100);
    }
  };

  /**
   * Open COA Chat Panel
   */
  const openCoAChat = () => {
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
  };

  /**
   * Send message in COA Chat
   */
  const sendCoAChatMessage = async (message: string) => {
    if (!coaProcessId || !message.trim()) return;

    // Add user message
    const userMessage = {
      role: "user" as const,
      content: message,
      timestamp: new Date(),
    };
    setCoaChatMessages((prev) => [...prev, userMessage]);
    setCoaChatLoading(true);

    try {
      const response = await fetch(
        `${API_BASE_URL}/api/chat/coa-rag/${coaProcessId}`,
        {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
          },
          body: JSON.stringify({ question: message }),
        }
      );

      const data = await response.json();

      if (data.success) {
        // Add assistant response
        const assistantMessage = {
          role: "assistant" as const,
          content: data.answer,
          timestamp: new Date(),
        };
        setCoaChatMessages((prev) => [...prev, assistantMessage]);
      } else {
        throw new Error(data.error || "Failed to get response");
      }
    } catch (error) {
      console.error("Error sending COA chat message:", error);
      const errorMessage = {
        role: "assistant" as const,
        content:
          "Sorry, I encountered an error processing your question. Please try again.",
        timestamp: new Date(),
      };
      setCoaChatMessages((prev) => [...prev, errorMessage]);
    } finally {
      setCoaChatLoading(false);
    }
  };

  /**
   * Close COA Chat Panel
   */
  const closeCoAChat = () => {
    setShowCoAChat(false);
  };

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
        if (gap > 50) increment = 2; // Fast for big jumps (10→60)
        else if (gap > 10) increment = 1; // Medium speed
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
        isCOADocument
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
                processId
              );

              // Note: HBR cancellation is disabled, so no need to check userCancelled
              setCurrentProcessId(processId);
            }
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
              /<hbr_process_id>(.*?)<\/hbr_process_id>/
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
                processId
              );

              // Note: HBR cancellation is disabled, so no need to check userCancelled
              setCurrentProcessId(processId);
            }
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
                /Multi-Agent Session ID: ([a-f0-9-]+)/
              );
              if (sessionIdMatch && sessionIdMatch[1]) {
                setHbrSessionId(sessionIdMatch[1]);
                console.log(
                  "Stored HBR multi-agent session ID:",
                  sessionIdMatch[1]
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
            // Update with real process ID from backend (replacing temporary ID)
            console.log(
              "📋 COA real process ID received, updating from temp:",
              tempProcessId,
              "to:",
              processId
            );

            // Check if user already cancelled before backend responded
            if (userCancelled) {
              console.log(
                "⚠️ Process already cancelled, sending cancellation to backend"
              );
              cancelProcess(processId); // Cancel the backend process that just started
              return;
            }

            setCurrentProcessId(processId);
            // setCanCancel already set to true immediately above
          }
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
            messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
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
              messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
              setUserScrolling(false);
            }, 100);
          }, responseDelay); // Delayed for non-COA documents
        } else {
          // For COA, just scroll to show the status card
          setTimeout(() => {
            messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
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

  const handleKeyPress = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSendMessage(inputMessage);
      setInputMessage("");
    }
  };

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
      timeoutId = setTimeout(() => {
        console.log(
          "Processing state safety timeout triggered after 5 minutes"
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
      }, 30 * 60 * 1000); // 5 minutes timeout - much more patient
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
        error.message
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
      console.log("Dashboard component unmounting - resetting all states");

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
    <div className="flex flex-col h-screen bg-gradient-to-br from-gray-50 to-blue-50 relative overflow-hidden">
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

      {/* Navigation bar */}
      <nav className="bg-white shadow-sm border-b border-gray-200 z-10 sticky top-0">
        <div className="max-w-full mx-auto px-4">
          <div className="flex justify-between items-center h-14">
            {/* Left side - App title */}
            <div className="flex items-center">
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
              <h1 className="text-xl font-bold text-black hover:scale-105 transition-transform duration-300 cursor-default">
                AI Document Parser
              </h1>
            </div>

            {/* Right side - User welcome & logout */}
            <div className="flex items-center">
              {/* Feedback Button */}
              <button
                onClick={handleFeedbackOpen}
                className="border border-cyan-400 text-cyan-600 px-3 py-1.5 rounded-md text-sm font-medium hover:bg-cyan-600 hover:text-white transition duration-300 shadow-sm hover:shadow-md flex items-center transform hover:scale-105 mr-3"
              >
                💭 Feedback
              </button>

              {user && (
                <div className="flex items-center mr-4 bg-blue-50 rounded-full py-1 px-3 border border-blue-100 shadow-sm hover:shadow-md transition-shadow duration-300">
                  <div className="w-6 h-6 rounded-full bg-gradient-to-r from-cyan-400 to-cyan-600 flex items-center justify-center text-white text-xs font-bold mr-2">
                    {user.username.substring(0, 1).toUpperCase()}
                  </div>
                  <span className="text-gray-700 font-medium whitespace-nowrap">
                    {user.username}
                  </span>
                </div>
              )}

              <button
                onClick={handleLogout}
                className="bg-gradient-to-r from-red-500 to-red-700 text-white px-3 py-1.5 rounded-md text-sm font-medium hover:from-red-600 hover:to-red-800 transition duration-300 shadow-sm hover:shadow-md flex items-center transform hover:scale-105"
              >
                <svg
                  xmlns="http://www.w3.org/2000/svg"
                  className="h-4 w-4 mr-1"
                  fill="none"
                  viewBox="0 0 24 24"
                  stroke="currentColor"
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth={2}
                    d="M17 16l4-4m0 0l-4-4m4 4H7m6 4v1a3 3 0 01-3 3H6a3 3 0 01-3-3V7a3 3 0 013-3h4a3 3 0 013 3v1"
                  />
                </svg>
                Logout
              </button>
            </div>
          </div>
        </div>
      </nav>

      {/* Chat Container - Full height */}
      <div className="flex-1 flex flex-col overflow-hidden">
        {/* Messages area with scrolling */}
        <div
          ref={chatContainerRef}
          className="flex-1 overflow-y-auto px-4 py-6"
          style={{
            backgroundImage:
              "radial-gradient(circle at 25px 25px, rgba(0, 50, 200, 0.03) 2%, transparent 0%), radial-gradient(circle at 75px 75px, rgba(0, 100, 255, 0.03) 2%, transparent 0%)",
            backgroundSize: "100px 100px",
            backgroundAttachment: "fixed",
          }}
        >
          <div className="max-w-3xl mx-auto space-y-7">
            {messages.map((message) => {
              // Render COA extraction status as a special message
              if (message.role === "system" && message.extractionStatus) {
                const status = message.extractionStatus;
                return (
                  <div
                    key={message.id}
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

                        {/* Action Buttons */}
                        <div className="mt-4 border-t pt-4 space-y-2">
                          {/* Two buttons side by side */}
                          <div className="flex gap-2">
                            {/* Download Button */}
                            <a
                              href={`/download/${status.enhancedFileName}`}
                              download
                              className="flex-1 flex items-center justify-center gap-2 bg-gradient-to-r from-green-500 to-green-600 text-white px-4 py-2.5 rounded-lg hover:from-green-600 hover:to-green-700 transition-all duration-300 shadow-md hover:shadow-lg font-medium"
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
                                  d="M12 10v6m0 0l-3-3m3 3l3-3m2 8H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"
                                />
                              </svg>
                              <span>Download Results</span>
                            </a>

                            {/* Chat Button */}
                            <button
                              onClick={() => {
                                // Use the process ID from this specific extraction
                                setCoaProcessId(status.processId);
                                openCoAChat();
                              }}
                              className="flex-1 flex items-center justify-center gap-2 bg-gradient-to-r from-cyan-500 to-cyan-600 text-white px-4 py-2.5 rounded-lg hover:from-cyan-600 hover:to-cyan-700 transition-all duration-300 shadow-md hover:shadow-lg font-medium"
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
                                  d="M8 10h.01M12 10h.01M16 10h.01M9 16H5a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v8a2 2 0 01-2 2h-5l-5 5v-5z"
                                />
                              </svg>
                              <span>Chat with Data</span>
                            </button>
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
                  key={message.id}
                  className={`flex ${
                    message.role === "user" ? "justify-end" : "justify-start"
                  } ${message.isNew ? "animate-messageIn" : ""}`}
                >
                  {message.role === "assistant" && (
                    <div className="w-9 h-9 rounded-full bg-gradient-to-r from-cyan-400 to-cyan-600 flex items-center justify-center text-white text-xs font-bold mr-2 flex-shrink-0 self-start mt-1 shadow-lg ring-2 ring-white relative overflow-hidden group">
                      <div className="absolute inset-0 bg-gradient-to-br from-cyan-300/30 to-cyan-500/30 backdrop-blur-sm group-hover:scale-110 transition-all duration-500"></div>
                      <span className="text-sm relative z-10">AI</span>
                    </div>
                  )}
                  <div
                    className={`max-w-md p-4 ${
                      message.role === "user"
                        ? "bg-gray-100 text-gray-800 rounded-3xl rounded-br-md shadow-lg hover:shadow-xl border border-gray-200 hover:border-gray-300 transition-all duration-300"
                        : "bg-white/90 backdrop-blur-md border border-gray-100 hover:border-gray-200 shadow-md hover:shadow-lg text-gray-800 rounded-3xl rounded-tl-md transition-all duration-300"
                    } relative overflow-hidden group`}
                  >
                    <div
                      className={`absolute inset-0 ${
                        message.role === "user"
                          ? "bg-gradient-to-br from-gray-200/20 via-transparent to-gray-300/20"
                          : "bg-gradient-to-br from-blue-50/50 via-transparent to-purple-50/30"
                      } opacity-0 group-hover:opacity-100 transition-opacity duration-700`}
                    ></div>
                    <div className="whitespace-pre-wrap break-words relative z-10">
                      {renderMessageWithLinks(
                        message.content,
                        message.id,
                        setMessages
                      )}
                    </div>
                    <p className="text-xs opacity-70 mt-2 text-right font-medium relative z-10">
                      {message.timestamp.toLocaleTimeString([], {
                        hour: "2-digit",
                        minute: "2-digit",
                      })}
                    </p>
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
              );
            })}

            {/* Thinking indicator */}
            {isThinking && (
              <div className="flex justify-start animate-messageIn">
                <div className="w-9 h-9 rounded-full bg-gradient-to-r from-cyan-400 to-cyan-600 flex items-center justify-center text-white text-xs font-bold mr-2 flex-shrink-0 self-start mt-1 shadow-lg ring-2 ring-white relative overflow-hidden">
                  <div className="absolute inset-0 bg-gradient-to-br from-blue-400/30 to-purple-500/30 backdrop-blur-sm"></div>
                  <span className="text-sm relative z-10">AI</span>
                </div>
                <div className="bg-white/90 backdrop-blur-md border border-gray-100 shadow-md rounded-3xl rounded-tl-md p-4 flex items-center relative overflow-hidden group">
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

            {/* Loading indicator - Only show if processingState is not active */}
            {isLoading && !processingState.active && (
              <div className="flex justify-start animate-messageIn">
                <div className="w-9 h-9 rounded-full bg-gradient-to-r from-cyan-400 to-cyan-600 flex items-center justify-center text-white text-xs font-bold mr-2 flex-shrink-0 self-start mt-1 shadow-lg ring-2 ring-white relative overflow-hidden">
                  <div className="absolute inset-0 bg-gradient-to-br from-blue-400/30 to-purple-500/30 backdrop-blur-sm"></div>
                  <span className="text-sm relative z-10">AI</span>
                </div>
                <div className="bg-white/90 backdrop-blur-md border border-gray-100 shadow-md rounded-3xl rounded-tl-md p-4 flex items-center relative overflow-hidden group">
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
                      accept={hbrUploadStage === "pdf" ? ".pdf" : ".xlsx,.xls"}
                    />
                  </label>
                </div>
              </div>
            )}

            {/* Empty state for first visit */}
            {messages.length === 0 && !isThinking && !isFirstVisit && (
              <div className="flex flex-col items-center justify-center text-center py-12 animate-fadeIn">
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
                <h3 className="text-xl font-medium text-gray-900 mb-1">
                  Document Extraction Assistant
                </h3>
                <p className="text-gray-500 mb-6 max-w-sm">
                  I can help you with information about:
                </p>
                <div className="flex flex-wrap justify-center gap-4">
                  <button
                    onClick={() => {
                      const message = "What is a Certificate of Analysis?";
                      handleSendMessage(message);
                    }}
                    className="flex items-center gap-2 text-cyan-600 hover:text-white bg-white hover:bg-cyan-600 text-sm font-medium px-4 py-2 rounded-full border border-cyan-200 shadow-sm hover:shadow-md transition-all duration-300 transform hover:scale-105"
                  >
                    <span className="text-lg">🧪</span>
                    Certificate of Analysis
                  </button>
                  <button
                    onClick={() => {
                      const message = "What is a Handwritten Batch Record?";
                      handleSendMessage(message);
                    }}
                    className="flex items-center gap-2 text-cyan-600 hover:text-white bg-white hover:bg-cyan-600 text-sm font-medium px-4 py-2 rounded-full border border-cyan-200 shadow-sm hover:shadow-md transition-all duration-300 transform hover:scale-105"
                  >
                    <span className="text-lg">📄</span>
                    Handwritten Batch Records
                  </button>
                  <button
                    onClick={() => {
                      const message =
                        "What types of information can you extract?";
                      handleSendMessage(message);
                    }}
                    className="flex items-center gap-2 text-cyan-600 hover:text-white bg-white hover:bg-cyan-600 text-sm font-medium px-4 py-2 rounded-full border border-cyan-200 shadow-sm hover:shadow-md transition-all duration-300 transform hover:scale-105"
                  >
                    <span className="text-lg">ℹ️</span>
                    Capabilities
                  </button>
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
                            processingState.progress >= item.completeThreshold;

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
                {messages.filter((msg) => msg.isNew).length}
              </span>
            )}
          </button>
        )}

        {/* Input area - Fixed at bottom */}
        <div className="border-t border-gray-200/50 bg-white/80 backdrop-blur-md px-4 py-4 shadow-lg relative z-10">
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
            <p className="text-xs text-gray-500 mt-2 text-center">
              Specialized in extracting information from 📄 Handwritten Batch
              Records and 🧪 Certificate of Analysis
            </p>
          </div>
        </div>
      </div>

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
      `}</style>

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
                    </p>
                  </div>
                </div>
              ))}
              {coaChatLoading && (
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
                    "input"
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
    </div>
  );
}
