import { useApp } from "@modelcontextprotocol/ext-apps/react";
import { StrictMode, useCallback, useState } from "react";
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

  const handleGetStatus = useCallback(async () => {
    if (!app) return;
    try {
      setStatusMessage("Loading status...");
      await app.sendMessage({
        role: "user",
        content: [
          {
            type: "text",
            text: "Can you get the system status?",
          },
        ],
      });
    } catch (e) {
      console.error("Failed to send message:", e);
      setStatusMessage("Error fetching status");
    }
  }, [app]);

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
