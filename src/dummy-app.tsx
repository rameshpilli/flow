import { useApp } from "@modelcontextprotocol/ext-apps/react";
import { StrictMode, useCallback, useMemo, useState } from "react";
import { createRoot } from "react-dom/client";

const IMPLEMENTATION = {
  name: "Dummy Dashboard",
  version: "1.0.0",
};

function DummyDashboard() {
  const { app, error } = useApp({
    appInfo: IMPLEMENTATION,
    capabilities: {},
  });

  const [statusMessage, setStatusMessage] = useState(
    "Click button to fetch status"
  );
  const [prompt, setPrompt] = useState("");
  const [llmStatus, setLlmStatus] = useState("Ready to chat.");
  const [llmResponse, setLlmResponse] = useState("");

  const extractText = useMemo(
    () =>
      (result: { content?: Array<{ type: string; text?: string }> }) => {
        if (!result?.content) return "No response content.";
        return result.content
          .filter((item) => item.type === "text")
          .map((item) => item.text || "")
          .filter(Boolean)
          .join("\n");
      },
    []
  );

  const handleGetStatus = useCallback(async () => {
    if (!app) return;
    try {
      setStatusMessage("Loading status...");
      const result = await app.callServerTool({
        name: "get-status",
        arguments: {},
      });
      setStatusMessage(extractText(result));
    } catch (e) {
      console.error("Failed to send message:", e);
      setStatusMessage("Error fetching status");
    }
  }, [app, extractText]);

  const handleChat = useCallback(async () => {
    if (!app) return;
    if (!prompt.trim()) {
      setLlmStatus("Please enter a prompt.");
      return;
    }
    try {
      setLlmStatus("Sending to LLM gateway...");
      const result = await app.callServerTool({
        name: "llm-chat",
        arguments: { prompt: prompt.trim() },
      });
      setLlmResponse(extractText(result));
      setLlmStatus("Response received.");
    } catch (e) {
      console.error("Failed to call LLM gateway:", e);
      setLlmStatus("Error calling LLM gateway.");
    }
  }, [app, extractText, prompt]);

  if (error) {
    return (
      <div style={{ padding: "20px", color: "red" }}>
        <strong>ERROR:</strong> {error.message}
      </div>
    );
  }

  if (!app) {
    return <div style={{ padding: "20px" }}>Loading MCPJam Dashboard...</div>;
  }

  return (
    <main
      style={{
        padding: "20px",
        fontFamily: "system-ui, -apple-system, sans-serif",
        maxWidth: "600px",
        margin: "0 auto",
        backgroundColor: "#f5f5f5",
        borderRadius: "8px",
      }}
    >
      <h1 style={{ fontSize: "24px", marginBottom: "16px", color: "#333" }}>
        📊 MCPJam Dummy Dashboard
      </h1>

      <div
        style={{
          backgroundColor: "white",
          padding: "16px",
          borderRadius: "6px",
          marginBottom: "16px",
          border: "1px solid #ddd",
        }}
      >
        <h2 style={{ fontSize: "16px", marginBottom: "12px", color: "#666" }}>
          Status
        </h2>
        <p style={{ fontSize: "14px", margin: "0", color: "#999" }}>
          {statusMessage}
        </p>
      </div>

      <button
        onClick={handleGetStatus}
        style={{
          padding: "12px 24px",
          fontSize: "16px",
          backgroundColor: "#007bff",
          color: "white",
          border: "none",
          borderRadius: "6px",
          cursor: "pointer",
          fontWeight: "500",
          transition: "background-color 0.2s",
        }}
        onMouseEnter={(e) => {
          (e.target as HTMLButtonElement).style.backgroundColor = "#0056b3";
        }}
        onMouseLeave={(e) => {
          (e.target as HTMLButtonElement).style.backgroundColor = "#007bff";
        }}
      >
        Get System Status
      </button>

      <div
        style={{
          backgroundColor: "white",
          padding: "16px",
          borderRadius: "6px",
          marginTop: "20px",
          border: "1px solid #ddd",
        }}
      >
        <h2 style={{ fontSize: "16px", marginBottom: "12px", color: "#666" }}>
          LLM Gateway Chat
        </h2>
        <textarea
          value={prompt}
          onChange={(e) => setPrompt(e.target.value)}
          placeholder="Ask your internal model..."
          rows={4}
          style={{
            width: "100%",
            borderRadius: "6px",
            border: "1px solid #ddd",
            padding: "10px",
            fontSize: "14px",
            marginBottom: "10px",
          }}
        />
        <button
          onClick={handleChat}
          style={{
            padding: "10px 18px",
            fontSize: "14px",
            backgroundColor: "#0f766e",
            color: "white",
            border: "none",
            borderRadius: "6px",
            cursor: "pointer",
            fontWeight: "600",
          }}
        >
          Send to LLM Gateway
        </button>
        <p style={{ fontSize: "12px", color: "#777", marginTop: "10px" }}>
          {llmStatus}
        </p>
        {llmResponse ? (
          <pre
            style={{
              whiteSpace: "pre-wrap",
              backgroundColor: "#f8fafc",
              border: "1px solid #e2e8f0",
              borderRadius: "6px",
              padding: "12px",
              fontSize: "13px",
              color: "#111827",
            }}
          >
            {llmResponse}
          </pre>
        ) : null}
      </div>

      <p
        style={{
          fontSize: "12px",
          color: "#999",
          marginTop: "24px",
          borderTop: "1px solid #eee",
          paddingTop: "12px",
        }}
      >
        This is a dummy MCPJam dashboard for testing MCP Apps in MCPJam
        Inspector.
      </p>
    </main>
  );
}

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <DummyDashboard />
  </StrictMode>
);
