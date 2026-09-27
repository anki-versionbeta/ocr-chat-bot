"use client";
import { useState, FormEvent, ChangeEvent } from "react";
import { useRouter } from "next/navigation";

// Environment Configuration - Comment/Uncomment as needed
const API_BASE_URL = "http://localhost:5000"; // Local development
//const API_BASE_URL =
//"https://dev.aiparser.ir-bioprocess-poc.awscloud.abbvienet.com"; // prod

interface FormElements extends HTMLFormControlsCollection {
  username: HTMLInputElement;
  password: HTMLInputElement;
}

interface LoginFormElement extends HTMLFormElement {
  readonly elements: FormElements;
}

export default function LoginPage() {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const router = useRouter();

  const handleSubmit = async (e: FormEvent<LoginFormElement>) => {
    e.preventDefault();
    setLoading(true);
    setError(null);

    try {
      const res = await fetch(`${API_BASE_URL}` + "/api/login", {
        method: "POST",
        headers: {
          Accept: "application/json",
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ username, password }),
        credentials: "include",
      });

      const data = await res.json();
      console.log("Login response:", data);

      if (res.ok) {
        router.push("/chat"); // Redirect to the dashboard page after login
      } else {
        setError("Invalid username or password");
      }
    } catch (error) {
      console.error("Login error:", error);
      setError("An error occurred. Please try again.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div
      className="flex h-screen items-center justify-center relative overflow-hidden"
      style={{
        background:
          "linear-gradient(135deg, #ecfeff 0%, #ffffff 40%, #cffafe 100%)",
      }}
    >
      <div
        className="w-full max-w-md p-8 rounded-lg"
        style={{
          background: "rgba(255, 255, 255, 0.95)",
          backdropFilter: "blur(20px)",
          WebkitBackdropFilter: "blur(20px)",
          border: "1px solid rgba(255, 255, 255, 0.8)",
          boxShadow:
            "0 20px 40px rgba(6, 182, 212, 0.1), 0 0 0 1px rgba(6, 182, 212, 0.1)",
        }}
      >
        {/* AI Logo */}
        <div
          className="mx-auto mb-6 flex items-center justify-center"
          style={{
            width: "72px",
            height: "72px",
            background: "linear-gradient(135deg, #06b6d4 0%, #0891b2 100%)",
            borderRadius: "18px",
            boxShadow: "0 8px 24px rgba(6, 182, 212, 0.25)",
            fontSize: "32px",
            fontWeight: "bold",
            color: "white",
            fontFamily: "sans-serif",
          }}
        >
          AI
        </div>

        <h1 className="text-3xl font-extrabold mb-2 text-center text-gray-800">
          AI Document Parser
        </h1>

        {/* Subtitle */}
        <p
          className="text-center mb-8"
          style={{
            fontSize: "15px",
            fontWeight: 400,
            color: "#6b7280",
            marginBottom: "32px",
          }}
        >
          Intelligent Document Extraction
        </p>
        <form onSubmit={handleSubmit} className="space-y-6">
          <input
            type="text"
            placeholder="Username"
            value={username}
            onChange={(e: ChangeEvent<HTMLInputElement>) =>
              setUsername(e.target.value)
            }
            className="w-full p-3 rounded-lg focus:outline-none"
            style={{
              border: "2px solid #e5e7eb",
              transition: "all 0.3s",
            }}
            onFocus={(e) => {
              e.target.style.borderColor = "#06b6d4";
              e.target.style.boxShadow = "0 0 0 4px rgba(6, 182, 212, 0.1)";
              e.target.style.transform = "translateY(-1px)";
            }}
            onBlur={(e) => {
              e.target.style.borderColor = "#e5e7eb";
              e.target.style.boxShadow = "none";
              e.target.style.transform = "translateY(0)";
            }}
            required
          />
          <input
            type="password"
            placeholder="Password"
            value={password}
            onChange={(e: ChangeEvent<HTMLInputElement>) =>
              setPassword(e.target.value)
            }
            className="w-full p-3 rounded-lg focus:outline-none"
            style={{
              border: "2px solid #e5e7eb",
              transition: "all 0.3s",
            }}
            onFocus={(e) => {
              e.target.style.borderColor = "#06b6d4";
              e.target.style.boxShadow = "0 0 0 4px rgba(6, 182, 212, 0.1)";
              e.target.style.transform = "translateY(-1px)";
            }}
            onBlur={(e) => {
              e.target.style.borderColor = "#e5e7eb";
              e.target.style.boxShadow = "none";
              e.target.style.transform = "translateY(0)";
            }}
            required
          />
          {error && <p className="text-red-600 text-sm text-center">{error}</p>}
          <div className="flex justify-center">
            <button
              type="submit"
              className="text-white p-3 rounded-lg font-semibold transition duration-300"
              disabled={loading}
              style={{
                height: "60px",
                width: "220px",
                borderRadius: "30px",
                position: "relative",
                display: "grid",
                color: "#fff",
                placeContent: "center",
                fontWeight: 600,
                fontSize: "25px",
                textTransform: "uppercase",
                textDecoration: "none",
                boxSizing: "border-box",
                background: "linear-gradient(135deg, #06b6d4 0%, #0891b2 100%)",
                boxShadow: "0 4px 16px rgba(6, 182, 212, 0.3)",
                transition: "all 0.3s ease",
                transform: "translateY(0px)",
                cursor: "pointer",
                letterSpacing: "2px",
              }}
              onMouseEnter={(e) => {
                (e.target as HTMLButtonElement).style.background =
                  "linear-gradient(135deg, #0891b2 0%, #0e7490 100%)";
                (e.target as HTMLButtonElement).style.transform =
                  "translateY(-2px)";
                (e.target as HTMLButtonElement).style.boxShadow =
                  "0 8px 24px rgba(6, 182, 212, 0.4)";
              }}
              onMouseLeave={(e) => {
                (e.target as HTMLButtonElement).style.background =
                  "linear-gradient(135deg, #06b6d4 0%, #0891b2 100%)";
                (e.target as HTMLButtonElement).style.transform =
                  "translateY(0)";
                (e.target as HTMLButtonElement).style.boxShadow =
                  "0 4px 16px rgba(6, 182, 212, 0.3)";
              }}
            >
              {loading ? (
                <div className="flex justify-center items-center">
                  <div className="w-5 h-5 border-2 border-white border-t-transparent rounded-full animate-spin"></div>
                  <span className="ml-2">Loading...</span>
                </div>
              ) : (
                "Login"
              )}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
