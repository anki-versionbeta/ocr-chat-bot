"use client";
import { useState, FormEvent, ChangeEvent } from "react";
import { useRouter } from "next/navigation";

// Environment Configuration - Comment/Uncomment as needed
const API_BASE_URL = "http://localhost:5000"; // Local development
//const API_BASE_URL = "http://10.242.190.41:5000"; // Dev environment

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
        router.push("/dashboard"); // Redirect to the dashboard page after login
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
      className="flex h-screen items-center justify-center"
      style={{
        background:
          "linear-gradient(90deg, #03a9f4, #f441a5, #ffeb3b, #03a9f4)",
        backgroundSize: "400%",
      }}
    >
      <div className="w-full max-w-md p-8 bg-white rounded-lg shadow-2xl">
        <h1 className="text-3xl font-extrabold mb-6 text-center text-gray-800">
          OCR Chatbot Login
        </h1>
        <form onSubmit={handleSubmit} className="space-y-6">
          <input
            type="text"
            placeholder="Username"
            value={username}
            onChange={(e: ChangeEvent<HTMLInputElement>) =>
              setUsername(e.target.value)
            }
            className="w-full p-3 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-600"
            required
          />
          <input
            type="password"
            placeholder="Password"
            value={password}
            onChange={(e: ChangeEvent<HTMLInputElement>) =>
              setPassword(e.target.value)
            }
            className="w-full p-3 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-600"
            required
          />
          {error && <p className="text-red-600 text-sm text-center">{error}</p>}
          <div className="flex justify-center">
            <button
              type="submit"
              className="bg-blue-600 text-white p-3 rounded-lg font-semibold hover:bg-blue-700 transition duration-300"
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
                background:
                  "linear-gradient(90deg, #03a9f4, #f441a5, #ffeb3b, #03a9f4)",
                backgroundSize: "400%",
                cursor: "pointer",
                letterSpacing: "2px",
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
