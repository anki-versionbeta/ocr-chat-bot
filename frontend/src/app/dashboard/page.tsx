"use client";
import { useEffect, useState, useRef } from "react";
import React from "react";
import { useRouter } from "next/navigation";

// Environment Configuration - Comment/Uncomment as needed
//const API_BASE_URL = "http://localhost:5000"; // Local development
const API_BASE_URL = "http://10.242.190.41:5000"; // Dev environment

// Import the agent service and file utilities
import { agent } from "../../services/agent";
import { extractTextFromFile } from "../../services/fileUtils";

type Message = {
  id: string;
  content: string;
  role: "user" | "assistant";
  timestamp: Date;
  isNew?: boolean;
};

// Function to render message with formatted links
const renderMessageWithLinks = (text: string, messageId: string) => {
  // First, let's extract all download links and replace them with special markers
  const downloadLinks: Array<{ text: string; url: string }> = [];
  let linkCounter = 0;

  // Process download section headers
  text = text.replace(
    /### Download Processed Files/g,
    '<div class="download-section-header">📥 Download Processed Files</div>'
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
    !text.includes("<download-button-placeholder")
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
  }>({
    active: false,
    stage: "uploading",
    fileName: "",
    progress: 0,
  });

  // HBR-specific state
  const [currentDocumentType, setCurrentDocumentType] = useState<
    "coa" | "hbr" | null
  >(null);
  const [hbrProcessId, setHbrProcessId] = useState<string | null>(null);
  const [showHbrUploadUI, setShowHbrUploadUI] = useState(false);
  const [hbrUploadStage, setHbrUploadStage] = useState<"pdf" | "excel">("pdf");

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

    // Variable to track if the user has manually scrolled
    let hasUserScrolled = false;

    // Function to detect when user is scrolling up
    const handleScroll = () => {
      if (!chatContainer) return;

      // Calculate distance from bottom
      const distanceFromBottom =
        chatContainer.scrollHeight -
        chatContainer.scrollTop -
        chatContainer.clientHeight;

      // If user has scrolled up more than 100px, consider them as actively scrolling
      if (distanceFromBottom > 100) {
        hasUserScrolled = true;
        setUserScrolling(true);

        // Clear any existing timeout
        if (scrollTimeoutRef.current) {
          clearTimeout(scrollTimeoutRef.current);
        }

        // Set a timeout to reset userScrolling after user stops scrolling
        // Using a much longer timeout to prevent auto-scrolling while reading
        scrollTimeoutRef.current = setTimeout(() => {
          // Only reset if the user has scrolled back to near bottom
          const newDistanceFromBottom =
            chatContainer.scrollHeight -
            chatContainer.scrollTop -
            chatContainer.clientHeight;

          if (newDistanceFromBottom < 50) {
            setUserScrolling(false);
            hasUserScrolled = false;
          }
        }, 300000); // 5 minutes - give plenty of time to read
      } else {
        // Only reset if very close to bottom AND they didn't manually scroll up earlier
        if (distanceFromBottom < 20 && !hasUserScrolled) {
          setUserScrolling(false);
        }
      }
    };

    chatContainer.addEventListener("scroll", handleScroll);

    return () => {
      chatContainer.removeEventListener("scroll", handleScroll);
      if (scrollTimeoutRef.current) {
        clearTimeout(scrollTimeoutRef.current);
      }
    };
  }, []);

  // Create a separate effect for auto-scrolling for new messages
  useEffect(() => {
    // Don't auto-scroll if user is viewing history
    if (userScrolling) {
      // If user is scrolling up, don't interfere at all
      return;
    }

    // Find any new messages
    const hasNewMessages = messages.some((msg) => msg.isNew);

    // Only auto-scroll if there are new messages and user isn't scrolling
    if (hasNewMessages) {
      // Use a very slight delay to ensure DOM has updated
      const scrollTimeout = setTimeout(() => {
        // Double-check user hasn't started scrolling during the timeout
        if (!userScrolling) {
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

  // Check local storage for first visit and set welcome messages only on first visit
  useEffect(() => {
    const hasVisitedBefore = localStorage.getItem("hasVisitedDashboard");

    if (
      !loading &&
      user &&
      (!hasVisitedBefore || hasVisitedBefore === "false")
    ) {
      // Show welcome overlay
      setShowWelcomeOverlay(true);

      // Hide overlay after 1 second (was 2 seconds)
      setTimeout(() => {
        setShowWelcomeOverlay(false);

        // Add initial agent welcome messages with minimal delay
        setIsThinking(true);
        setTimeout(() => {
          const initialMessages: Message[] = [
            {
              id: "1",
              content: `Hi ${user.username}! I'm your document extraction assistant. I can provide information about Certificates of Analysis and Paperbatch Records.`,
              role: "assistant",
              timestamp: new Date(),
              isNew: true,
            },
          ];
          setMessages(initialMessages);
          setIsThinking(false);

          // Second message with minimal delay
          setTimeout(() => {
            setIsThinking(true);
            setTimeout(() => {
              setIsThinking(false);
              setMessages((prev) => [
                ...prev,
                {
                  id: "2",
                  content:
                    "You can ask me questions about these document types, or type 'capabilities' to learn more about what I can do.",
                  role: "assistant",
                  timestamp: new Date(),
                  isNew: true,
                },
              ]);

              // Set visited flag in localStorage
              localStorage.setItem("hasVisitedDashboard", "true");
              setIsFirstVisit(false);
            }, 300);
          }, 300);
        }, 300);
      }, 1000); // Reduced from 2000ms to 1000ms
    } else {
      setIsFirstVisit(false);
    }
  }, [loading, user]);

  useEffect(() => {
    const checkAuth = async () => {
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
        setUser(data);

        // Remove the automatic welcome message
        // The welcome message will only appear when user says "hi" or similar
      } catch (error) {
        console.error("Auth check error:", error);
        router.push("/login");
      } finally {
        setLoading(false);
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

      // Reset the first visit flag in localStorage
      localStorage.setItem("hasVisitedDashboard", "false");

      // Redirect to login page
      router.push("/login");
    } catch (error) {
      console.error("Logout error:", error);
    }
  };

  /**
   * Check if a message is related to HBR processing
   */
  const isHbrRelatedMessage = (
    message: string,
    isAssistantResponse: boolean = false
  ): boolean => {
    const lowerMessage = message.toLowerCase();

    // Keywords related to HBR
    const hbrKeywords = [
      "hbr",
      "health based requirement",
      "health-based requirement",
      "health based requirements",
      "health-based requirements",
    ];

    // Check if any HBR keyword is in the message
    const containsHbrKeyword = hbrKeywords.some((keyword) =>
      lowerMessage.includes(keyword)
    );

    // For user messages, just check for HBR keywords
    if (!isAssistantResponse) {
      return containsHbrKeyword;
    }

    // For assistant responses, check for HBR keywords and upload instructions
    return (
      containsHbrKeyword ||
      (lowerMessage.includes("upload") && lowerMessage.includes("hbr")) ||
      (lowerMessage.includes("upload") &&
        lowerMessage.includes("health based requirement"))
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

    // Hide upload UI while waiting for response
    setShowUploadUI(false);
    setShowHbrUploadUI(false);

    // Show loading indicator only if we're not already showing processing state
    if (!processingState.active) {
      setIsLoading(true);
    }

    // Check if the message is a greeting
    const isUserGreeting = isGreeting(message);

    // Process the message through the agent
    try {
      const response = await agent.processMessage(message);
      const agentMessage: Message = {
        id: (Date.now() + 1).toString(),
        content: response,
        role: "assistant",
        timestamp: new Date(),
      };
      setMessages((prev) => [...prev, agentMessage]);

      // Check if the message is related to HBR
      if (isHbrRelatedMessage(message) && isHbrRelatedMessage(response, true)) {
        setCurrentDocumentType("hbr");
        setHbrUploadStage("pdf");
        setShowHbrUploadUI(true);
        setShowUploadUI(false);
      }
      // Check if the message is related to COA upload
      else if (
        isUploadRelatedMessage(message) &&
        isUploadRelatedMessage(response, true)
      ) {
        setCurrentDocumentType("coa");
        setShowUploadUI(true);
        setShowHbrUploadUI(false);
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
      const errorMessage: Message = {
        id: (Date.now() + 1).toString(),
        content:
          "Sorry, I encountered an error processing your message. Please try again.",
        role: "assistant",
        timestamp: new Date(),
      };
      setMessages((prev) => [...prev, errorMessage]);
    } finally {
      setIsLoading(false);
    }
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
      // Show upload progress
      setUploadProgress(0);
      setUploadStage("uploading");

      // Show processing state with file information
      setProcessingState({
        active: true,
        stage: "uploading",
        fileName: file.name,
        progress: 0,
      });

      let extractedText = "";

      // Handle different document types
      if (currentDocumentType === "hbr") {
        // For HBR documents, we need to handle PDF and Excel files differently
        if (hbrUploadStage === "pdf") {
          // Process HBR PDF file
          extractedText = await extractTextFromFile(
            file,
            (stage, progress) => {
              setUploadStage(stage);
              setUploadProgress(progress);

              // Update processing state with current progress
              setProcessingState({
                active: true,
                stage: stage,
                fileName: file.name,
                progress: progress,
              });

              // When complete, show completed state for 2 seconds
              if (stage === "analyzing" && progress === 100) {
                setTimeout(() => {
                  setProcessingState({
                    active: true,
                    stage: "completed",
                    fileName: file.name,
                    progress: 100,
                  });

                  // Hide the processing state after 2 seconds
                  setTimeout(() => {
                    setProcessingState({
                      active: false,
                      stage: "uploading",
                      fileName: "",
                      progress: 0,
                    });
                  }, 2000);
                }, 500);
              }
            },
            "hbr_pdf"
          );

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
        } else if (hbrUploadStage === "excel" && hbrProcessId) {
          // Process HBR Excel file with process ID
          extractedText = await extractTextFromFile(
            file,
            (stage, progress) => {
              setUploadStage(stage);
              setUploadProgress(progress);

              // Update processing state with current progress
              setProcessingState({
                active: true,
                stage: stage,
                fileName: file.name,
                progress: progress,
              });

              // When complete, show completed state for 2 seconds
              if (stage === "analyzing" && progress === 100) {
                setTimeout(() => {
                  setProcessingState({
                    active: true,
                    stage: "completed",
                    fileName: file.name,
                    progress: 100,
                  });

                  // Hide the processing state after 2 seconds
                  setTimeout(() => {
                    setProcessingState({
                      active: false,
                      stage: "uploading",
                      fileName: "",
                      progress: 0,
                    });
                  }, 2000);
                }, 500);
              }
            },
            "hbr_excel",
            hbrProcessId
          );

          // Reset HBR state after processing both files
          setHbrProcessId(null);
          setHbrUploadStage("pdf");
          setShowHbrUploadUI(false);
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

            // Update processing state with current progress
            setProcessingState({
              active: true,
              stage: stage,
              fileName: file.name,
              progress: progress,
            });

            // When complete, show completed state for 2 seconds
            if (stage === "analyzing" && progress === 100) {
              setTimeout(() => {
                setProcessingState({
                  active: true,
                  stage: "completed",
                  fileName: file.name,
                  progress: 100,
                });

                // Hide the processing state after 2 seconds
                setTimeout(() => {
                  setProcessingState({
                    active: false,
                    stage: "uploading",
                    fileName: "",
                    progress: 0,
                  });
                }, 2000);
              }, 500);
            }
          },
          "coa"
        );
      }

      // Add extracted text to chat
      const extractedMessage: Message = {
        id: (Date.now() + 1).toString(),
        content: extractedText,
        role: "assistant",
        timestamp: new Date(),
      };
      setMessages((prev) => [...prev, extractedMessage]);

      // Only hide the upload UI for COA or after completing the HBR Excel upload
      if (currentDocumentType !== "hbr" || hbrUploadStage !== "pdf") {
        setShowUploadUI(false);
      }
    } catch (error) {
      console.error("Error uploading file:", error);
      const errorMessage: Message = {
        id: (Date.now() + 1).toString(),
        content: `Error uploading ${file.name}: ${(error as Error).message}`,
        role: "assistant",
        timestamp: new Date(),
      };
      setMessages((prev) => [...prev, errorMessage]);

      // Reset processing state on error
      setProcessingState({
        active: false,
        stage: "uploading",
        fileName: "",
        progress: 0,
      });
    } finally {
      setUploadProgress(0);
      setUploadStage("uploading");
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
            Loading OCR Chatbot...
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
        <div className="fixed inset-0 bg-gradient-to-br from-blue-600/90 to-purple-700/90 z-50 flex items-center justify-center animate-fadeIn">
          <div className="text-center">
            <div className="flex items-center justify-center mb-6">
              <div className="w-16 h-16 bg-white rounded-full flex items-center justify-center">
                <svg
                  xmlns="http://www.w3.org/2000/svg"
                  className="h-10 w-10 text-blue-600"
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
                <h1 className="text-3xl font-bold text-white">OCR Chatbot</h1>
                <p className="text-blue-100">Document analysis assistant</p>
              </div>
            </div>
            <p className="text-xl text-white mb-2">
              Welcome, {user?.username}!
            </p>
            <p className="text-blue-100">Getting things ready for you...</p>
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
              <div className="w-8 h-8 rounded-full bg-gradient-to-r from-blue-500 to-purple-600 flex items-center justify-center text-white mr-2 shadow-md hover:shadow-lg transition-shadow duration-300">
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
              <h1 className="text-xl font-bold text-transparent bg-clip-text bg-gradient-to-r from-blue-600 to-purple-600 hover:scale-105 transition-transform duration-300 cursor-default">
                OCR Chatbot
              </h1>
            </div>

            {/* Right side - User welcome & logout */}
            <div className="flex items-center">
              {user && (
                <div className="flex items-center mr-4 bg-blue-50 rounded-full py-1 px-3 border border-blue-100 shadow-sm hover:shadow-md transition-shadow duration-300">
                  <div className="w-6 h-6 rounded-full bg-gradient-to-r from-blue-500 to-blue-700 flex items-center justify-center text-white text-xs font-bold mr-2">
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
            {messages.map((message) => (
              <div
                key={message.id}
                className={`flex ${
                  message.role === "user" ? "justify-end" : "justify-start"
                } ${message.isNew ? "animate-messageIn" : ""}`}
              >
                {message.role === "assistant" && (
                  <div className="w-9 h-9 rounded-full bg-gradient-to-r from-blue-500 to-purple-600 flex items-center justify-center text-white text-xs font-bold mr-2 flex-shrink-0 self-start mt-1 shadow-lg ring-2 ring-white relative overflow-hidden group">
                    <div className="absolute inset-0 bg-gradient-to-br from-blue-400/30 to-purple-500/30 backdrop-blur-sm group-hover:scale-110 transition-all duration-500"></div>
                    <span className="text-sm relative z-10">AI</span>
                  </div>
                )}
                <div
                  className={`max-w-md p-4 ${
                    message.role === "user"
                      ? "bg-gradient-to-br from-blue-500 to-blue-700 text-white rounded-3xl rounded-br-md shadow-lg hover:shadow-xl border border-blue-400/50 hover:border-blue-300 transition-all duration-300"
                      : "bg-white/90 backdrop-blur-md border border-gray-100 hover:border-gray-200 shadow-md hover:shadow-lg text-gray-800 rounded-3xl rounded-tl-md transition-all duration-300"
                  } relative overflow-hidden group`}
                >
                  <div
                    className={`absolute inset-0 ${
                      message.role === "user"
                        ? "bg-gradient-to-br from-blue-400/20 via-transparent to-purple-500/20"
                        : "bg-gradient-to-br from-blue-50/50 via-transparent to-purple-50/30"
                    } opacity-0 group-hover:opacity-100 transition-opacity duration-700`}
                  ></div>
                  <div className="whitespace-pre-wrap break-words relative z-10">
                    {renderMessageWithLinks(message.content, message.id)}
                  </div>
                  <p className="text-xs opacity-70 mt-2 text-right font-medium relative z-10">
                    {message.timestamp.toLocaleTimeString([], {
                      hour: "2-digit",
                      minute: "2-digit",
                    })}
                  </p>
                </div>
                {message.role === "user" && (
                  <div className="w-9 h-9 rounded-full bg-gradient-to-br from-blue-600 to-blue-800 flex items-center justify-center text-white text-xs font-bold ml-2 flex-shrink-0 self-start mt-1 shadow-lg ring-2 ring-white relative overflow-hidden group">
                    <div className="absolute inset-0 bg-gradient-to-br from-blue-500/30 to-blue-700/30 backdrop-blur-sm group-hover:scale-110 transition-all duration-500"></div>
                    <span className="text-sm relative z-10">
                      {user?.username.substring(0, 2).toUpperCase() || "U"}
                    </span>
                  </div>
                )}
              </div>
            ))}

            {/* Thinking indicator */}
            {isThinking && (
              <div className="flex justify-start animate-messageIn">
                <div className="w-9 h-9 rounded-full bg-gradient-to-r from-blue-500 to-purple-600 flex items-center justify-center text-white text-xs font-bold mr-2 flex-shrink-0 self-start mt-1 shadow-lg ring-2 ring-white relative overflow-hidden">
                  <div className="absolute inset-0 bg-gradient-to-br from-blue-400/30 to-purple-500/30 backdrop-blur-sm"></div>
                  <span className="text-sm relative z-10">AI</span>
                </div>
                <div className="bg-white/90 backdrop-blur-md border border-gray-100 shadow-md rounded-3xl rounded-tl-md p-4 flex items-center relative overflow-hidden group">
                  <div className="absolute inset-0 bg-gradient-to-br from-blue-50/50 via-transparent to-purple-50/30 animate-pulse"></div>
                  <div className="flex space-x-2 relative z-10">
                    <div
                      className="w-2.5 h-2.5 rounded-full bg-gradient-to-r from-blue-400 to-blue-600 animate-bounce shadow-sm"
                      style={{ animationDelay: "0ms" }}
                    ></div>
                    <div
                      className="w-2.5 h-2.5 rounded-full bg-gradient-to-r from-blue-400 to-blue-600 animate-bounce shadow-sm"
                      style={{ animationDelay: "300ms" }}
                    ></div>
                    <div
                      className="w-2.5 h-2.5 rounded-full bg-gradient-to-r from-blue-400 to-blue-600 animate-bounce shadow-sm"
                      style={{ animationDelay: "600ms" }}
                    ></div>
                  </div>
                </div>
              </div>
            )}

            {/* Loading indicator - Only show if processingState is not active */}
            {isLoading && !processingState.active && (
              <div className="flex justify-start animate-messageIn">
                <div className="w-9 h-9 rounded-full bg-gradient-to-r from-blue-500 to-purple-600 flex items-center justify-center text-white text-xs font-bold mr-2 flex-shrink-0 self-start mt-1 shadow-lg ring-2 ring-white relative overflow-hidden">
                  <div className="absolute inset-0 bg-gradient-to-br from-blue-400/30 to-purple-500/30 backdrop-blur-sm"></div>
                  <span className="text-sm relative z-10">AI</span>
                </div>
                <div className="bg-white/90 backdrop-blur-md border border-gray-100 shadow-md rounded-3xl rounded-tl-md p-4 flex items-center relative overflow-hidden group">
                  <div className="absolute inset-0 bg-gradient-to-br from-blue-50/50 via-transparent to-purple-50/30 animate-pulse"></div>
                  <div className="flex space-x-2 relative z-10">
                    <div
                      className="w-2.5 h-2.5 rounded-full bg-gradient-to-r from-blue-400 to-blue-600 animate-bounce shadow-sm"
                      style={{ animationDelay: "0ms" }}
                    ></div>
                    <div
                      className="w-2.5 h-2.5 rounded-full bg-gradient-to-r from-blue-400 to-blue-600 animate-bounce shadow-sm"
                      style={{ animationDelay: "300ms" }}
                    ></div>
                    <div
                      className="w-2.5 h-2.5 rounded-full bg-gradient-to-r from-blue-400 to-blue-600 animate-bounce shadow-sm"
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
                  <label className="flex items-center justify-center gap-2 px-4 py-2 bg-gradient-to-r from-blue-500 to-blue-600 text-white text-sm rounded-lg cursor-pointer hover:from-blue-600 hover:to-blue-700 transition-all duration-300 shadow-sm hover:shadow-md transform hover:scale-105">
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
                  <label className="flex items-center justify-center gap-2 px-4 py-2 bg-gradient-to-r from-purple-500 to-purple-600 text-white text-sm rounded-lg cursor-pointer hover:from-purple-600 hover:to-purple-700 transition-all duration-300 shadow-sm hover:shadow-md transform hover:scale-105">
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
                <div className="w-20 h-20 bg-blue-100 rounded-full flex items-center justify-center mb-4 shadow-inner">
                  <svg
                    xmlns="http://www.w3.org/2000/svg"
                    className="h-10 w-10 text-blue-600"
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
                    onClick={() =>
                      setInputMessage("What is a Certificate of Analysis?")
                    }
                    className="flex items-center gap-2 text-blue-600 hover:text-white bg-white hover:bg-blue-600 text-sm font-medium px-4 py-2 rounded-full border border-blue-200 shadow-sm hover:shadow-md transition-all duration-300 transform hover:scale-105"
                  >
                    <span className="text-lg">🧪</span>
                    Certificates of Analysis
                  </button>
                  <button
                    onClick={() =>
                      setInputMessage("What is a Paperbatch Record?")
                    }
                    className="flex items-center gap-2 text-blue-600 hover:text-white bg-white hover:bg-blue-600 text-sm font-medium px-4 py-2 rounded-full border border-blue-200 shadow-sm hover:shadow-md transition-all duration-300 transform hover:scale-105"
                  >
                    <span className="text-lg">📄</span>
                    Paperbatch Records
                  </button>
                  <button
                    onClick={() =>
                      setInputMessage(
                        "What types of information can you extract?"
                      )
                    }
                    className="flex items-center gap-2 text-purple-600 hover:text-white bg-white hover:bg-purple-600 text-sm font-medium px-4 py-2 rounded-full border border-purple-200 shadow-sm hover:shadow-md transition-all duration-300 transform hover:scale-105"
                  >
                    <span className="text-lg">ℹ️</span>
                    Capabilities
                  </button>
                </div>
              </div>
            )}

            {/* Processing indicator - Single centered loading block */}
            {processingState.active && (
              <div className="fixed top-1/2 left-1/2 transform -translate-x-1/2 -translate-y-1/2 z-50 animate-fadeIn">
                <div className="bg-white p-6 rounded-xl shadow-2xl border border-blue-100 max-w-md mx-auto">
                  <div className="flex flex-col items-center">
                    {/* Different icons for different stages */}
                    {processingState.stage === "uploading" && (
                      <div className="w-16 h-16 bg-blue-100 rounded-full flex items-center justify-center mb-4 animate-pulse">
                        <svg
                          xmlns="http://www.w3.org/2000/svg"
                          className="h-8 w-8 text-blue-600"
                          fill="none"
                          viewBox="0 0 24 24"
                          stroke="currentColor"
                        >
                          <path
                            strokeLinecap="round"
                            strokeLinejoin="round"
                            strokeWidth={2}
                            d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12"
                          />
                        </svg>
                      </div>
                    )}

                    {processingState.stage === "extracting" && (
                      <div className="w-16 h-16 bg-indigo-100 rounded-full flex items-center justify-center mb-4">
                        <svg
                          xmlns="http://www.w3.org/2000/svg"
                          className="h-8 w-8 text-indigo-600 animate-spin"
                          fill="none"
                          viewBox="0 0 24 24"
                          stroke="currentColor"
                        >
                          <path
                            strokeLinecap="round"
                            strokeLinejoin="round"
                            strokeWidth={2}
                            d="M8 7v8a2 2 0 002 2h6M8 7V5a2 2 0 012-2h4.586a1 1 0 01.707.293l4.414 4.414a1 1 0 01.293.707V15a2 2 0 01-2 2h-2M8 7H6a2 2 0 00-2 2v10a2 2 0 002 2h8a2 2 0 002-2v-2"
                          />
                        </svg>
                      </div>
                    )}

                    {processingState.stage === "analyzing" && (
                      <div className="w-16 h-16 bg-purple-100 rounded-full flex items-center justify-center mb-4">
                        <svg
                          xmlns="http://www.w3.org/2000/svg"
                          className="h-8 w-8 text-purple-600 animate-bounce"
                          fill="none"
                          viewBox="0 0 24 24"
                          stroke="currentColor"
                        >
                          <path
                            strokeLinecap="round"
                            strokeLinejoin="round"
                            strokeWidth={2}
                            d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2m-3 7h3m-3 4h3m-6-4h.01M9 16h.01"
                          />
                        </svg>
                      </div>
                    )}

                    {processingState.stage === "completed" && (
                      <div className="w-16 h-16 bg-green-100 rounded-full flex items-center justify-center mb-4 animate-bounce">
                        <svg
                          xmlns="http://www.w3.org/2000/svg"
                          className="h-8 w-8 text-green-600"
                          fill="none"
                          viewBox="0 0 24 24"
                          stroke="currentColor"
                        >
                          <path
                            strokeLinecap="round"
                            strokeLinejoin="round"
                            strokeWidth={2}
                            d="M5 13l4 4L19 7"
                          />
                        </svg>
                      </div>
                    )}

                    <h3 className="text-xl font-semibold text-gray-800 mb-2">
                      {processingState.stage === "uploading" &&
                        "Uploading Document"}
                      {processingState.stage === "extracting" &&
                        "Extracting Data"}
                      {processingState.stage === "analyzing" &&
                        "Analyzing Content"}
                      {processingState.stage === "completed" &&
                        "Processing Complete"}
                    </h3>

                    <p className="text-gray-600 mb-4 text-center">
                      {processingState.stage === "uploading" &&
                        "Transferring your file to our secure servers..."}
                      {processingState.stage === "extracting" &&
                        "Using OCR to extract text and tables from your document..."}
                      {processingState.stage === "analyzing" &&
                        "Interpreting data with our AI to identify key information..."}
                      {processingState.stage === "completed" &&
                        "Your document has been successfully processed!"}
                    </p>

                    <div className="w-full bg-gray-200 rounded-full h-2.5 mb-2">
                      <div
                        className="bg-gradient-to-r from-blue-500 to-purple-600 h-2.5 rounded-full transition-all duration-500 ease-out"
                        style={{ width: `${processingState.progress}%` }}
                      ></div>
                    </div>

                    <p className="text-sm text-gray-500">
                      Processing: {processingState.fileName}
                    </p>
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
            <div className="flex items-center rounded-xl border border-gray-300/70 bg-white/80 backdrop-blur-sm shadow-md hover:shadow-lg transition-all duration-300 focus-within:ring-2 focus-within:ring-blue-400 focus-within:border-blue-400 overflow-hidden">
              <input
                type="text"
                value={inputMessage}
                onChange={(e) => setInputMessage(e.target.value)}
                onKeyPress={handleKeyPress}
                placeholder="Ask about your documents or upload a file..."
                className="flex-1 py-3.5 px-4 outline-none rounded-l-xl text-gray-700 placeholder-gray-500 bg-transparent backdrop-blur-sm"
                disabled={isThinking}
                ref={inputRef}
              />
              <div className="flex pr-2">
                <button
                  onClick={() => fileInputRef.current?.click()}
                  className="p-2 text-gray-500 hover:text-blue-600 hover:bg-blue-50/80 backdrop-blur-sm rounded-full transition-all mr-1.5 transform hover:scale-110 duration-200"
                  title="Upload document"
                  disabled={isThinking}
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
                  onClick={() => {
                    handleSendMessage(inputMessage);
                    setInputMessage("");
                  }}
                  className={`p-2.5 rounded-full transition-all duration-300 transform ${
                    inputMessage.trim() && !isThinking
                      ? "bg-gradient-to-r from-blue-500 to-blue-700 text-white hover:shadow-xl hover:scale-110 shadow-md relative overflow-hidden group"
                      : "bg-gray-200 text-gray-400 cursor-not-allowed"
                  }`}
                  disabled={!inputMessage.trim() || isThinking}
                  title="Send message"
                >
                  {inputMessage.trim() && !isThinking && (
                    <div className="absolute inset-0 bg-gradient-to-br from-blue-400/20 via-transparent to-purple-500/20 opacity-0 group-hover:opacity-100 transition-opacity duration-700"></div>
                  )}
                  <svg
                    xmlns="http://www.w3.org/2000/svg"
                    className="h-5 w-5 relative z-10"
                    viewBox="0 0 20 20"
                    fill="currentColor"
                  >
                    <path d="M10.894 2.553a1 1 0 00-1.788 0l-7 14a1 1 0 001.169 1.409l5-1.429A1 1 0 009 15.571V11a1 1 0 112 0v4.571a1 1 0 00.725.962l5 1.428a1 1 0 001.17-1.408l-7-14z" />
                  </svg>
                </button>
              </div>
            </div>
            <p className="text-xs text-gray-500 mt-2 text-center">
              Specialized in extracting information from 📄 Paperbatch Records
              and 🧪 Certificates of Analysis
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
    </div>
  );
}
