"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { apiRequest, managerHeaders } from "@/lib/api";

type PromptSummary = {
  name: string;
  title: string;
  role: string;
  description: string;
  default_model: string;
  output_schema_summary: string;
  sample_input: Record<string, unknown>;
  system_prompt: string;
  default_prompt: string;
  is_customized: boolean;
  version: string;
  updated_at: string | null;
  change_summary: string | null;
  char_count: number;
  line_count: number;
};

type PromptListResponse = {
  agents: PromptSummary[];
  total_count: number;
  customized_count: number;
};

type TestPromptResponse = {
  status: string;
  agent_name: string;
  model: string;
  latency_ms: number;
  output: Record<string, unknown>;
  schema_name: string;
};

export default function PromptsPage() {
  const [agents, setAgents] = useState<PromptSummary[]>([]);
  const [selectedName, setSelectedName] = useState<string>("security");
  const [editedPrompt, setEditedPrompt] = useState<string>("");
  const [changeSummary, setChangeSummary] = useState<string>("");
  const [showDiff, setShowDiff] = useState<boolean>(false);
  const [testPayloadText, setTestPayloadText] = useState<string>("");
  const [testResult, setTestResult] = useState<TestPromptResponse | null>(null);
  const [testError, setTestError] = useState<string>("");

  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [isSaving, setIsSaving] = useState<boolean>(false);
  const [isTesting, setIsTesting] = useState<boolean>(false);
  const [isResetting, setIsResetting] = useState<boolean>(false);
  const [confirmReset, setConfirmReset] = useState<boolean>(false);

  const [notice, setNotice] = useState<{
    type: "success" | "error";
    text: string;
  } | null>(null);

  const selectedAgent = useMemo(() => {
    return agents.find((a) => a.name === selectedName) ?? agents[0] ?? null;
  }, [agents, selectedName]);

  const isDirty = useMemo(() => {
    if (!selectedAgent) return false;
    return editedPrompt.trim() !== selectedAgent.system_prompt.trim();
  }, [selectedAgent, editedPrompt]);

  const loadPrompts = useCallback(async (preferredAgentName?: string) => {
    setIsLoading(true);
    setNotice(null);
    try {
      const data = await apiRequest<PromptListResponse>("/prompts", {
        headers: managerHeaders(),
      });
      setAgents(data.agents);
      const targetName = preferredAgentName || selectedName;
      const current =
        data.agents.find((a) => a.name === targetName) || data.agents[0];
      if (current) {
        setSelectedName(current.name);
        setEditedPrompt(current.system_prompt);
        setTestPayloadText(JSON.stringify(current.sample_input, null, 2));
      }
    } catch (err) {
      setNotice({
        type: "error",
        text:
          err instanceof Error
            ? err.message
            : "Failed to load agent prompts. Ensure backend is running.",
      });
    } finally {
      setIsLoading(false);
    }
  }, [selectedName]);

  useEffect(() => {
    const task = window.setTimeout(() => void loadPrompts(), 0);
    return () => window.clearTimeout(task);
  }, [loadPrompts]);


  function handleSelectAgent(agent: PromptSummary) {
    setSelectedName(agent.name);
    setEditedPrompt(agent.system_prompt);
    setChangeSummary("");
    setShowDiff(false);
    setTestResult(null);
    setTestError("");
    setConfirmReset(false);
    setTestPayloadText(JSON.stringify(agent.sample_input, null, 2));
    setNotice(null);
  }

  async function handleSave() {
    if (!selectedAgent) return;
    if (!editedPrompt.trim()) {
      setNotice({ type: "error", text: "System prompt cannot be empty." });
      return;
    }
    setIsSaving(true);
    setNotice(null);
    try {
      const updated = await apiRequest<PromptSummary>(
        `/prompts/${selectedAgent.name}`,
        {
          method: "PATCH",
          headers: {
            ...managerHeaders(),
            "Content-Type": "application/json",
          },
          body: JSON.stringify({
            system_prompt: editedPrompt,
            change_summary: changeSummary.trim() || undefined,
          }),
        },
      );
      setNotice({
        type: "success",
        text: `Prompt for ${updated.title} saved successfully. It is now active in workflow runs.`,
      });
      setChangeSummary("");
      await loadPrompts(updated.name);
    } catch (err) {
      setNotice({
        type: "error",
        text: err instanceof Error ? err.message : "Failed to save prompt",
      });
    } finally {
      setIsSaving(false);
    }
  }

  async function handleReset() {
    if (!selectedAgent) return;
    setIsResetting(true);
    setNotice(null);
    try {
      const resetAgent = await apiRequest<PromptSummary>(
        `/prompts/${selectedAgent.name}/reset`,
        {
          method: "POST",
          headers: managerHeaders(),
        },
      );
      setEditedPrompt(resetAgent.system_prompt);
      setConfirmReset(false);
      setNotice({
        type: "success",
        text: `${resetAgent.title} prompt reset to factory default (v1.yaml).`,
      });
      await loadPrompts(resetAgent.name);
    } catch (err) {
      setNotice({
        type: "error",
        text: err instanceof Error ? err.message : "Failed to reset prompt",
      });
    } finally {
      setIsResetting(false);
    }
  }

  async function handleRunTest() {
    if (!selectedAgent) return;
    setTestError("");
    setTestResult(null);

    let parsedPayload: Record<string, unknown>;
    try {
      parsedPayload = JSON.parse(testPayloadText) as Record<string, unknown>;
    } catch (parseErr) {
      setTestError(
        `Invalid JSON in test payload: ${parseErr instanceof Error ? parseErr.message : "Parse error"}`,
      );
      return;
    }

    setIsTesting(true);
    try {
      const result = await apiRequest<TestPromptResponse>(
        `/prompts/${selectedAgent.name}/test`,
        {
          method: "POST",
          headers: {
            ...managerHeaders(),
            "Content-Type": "application/json",
          },
          body: JSON.stringify({
            system_prompt: editedPrompt,
            test_input: parsedPayload,
          }),
        },
      );
      setTestResult(result);
    } catch (err) {
      setTestError(
        err instanceof Error ? err.message : "Agent test execution failed",
      );
    } finally {
      setIsTesting(false);
    }
  }

  function handleLoadSample() {
    if (!selectedAgent) return;
    setTestPayloadText(JSON.stringify(selectedAgent.sample_input, null, 2));
    setTestResult(null);
    setTestError("");
  }

  const customizedCount = agents.filter((a) => a.is_customized).length;

  return (
    <div>
      <section className="card" style={{ marginBottom: "20px" }}>
        <div className="editor-header-top">
          <div>
            <h1>Agent Prompt Control Studio</h1>
            <p className="lede">
              Fine-tune, govern, and live-test system prompts for each of the 8
              bounded multi-agent workflow components. Custom prompts take effect
              immediately in live assistant triage.
            </p>
          </div>
          <div style={{ display: "flex", gap: "10px", alignItems: "center" }}>
            <span className="badge-pill badge-builtin">
              {agents.length} Total Agents
            </span>
            <span
              className={`badge-pill ${
                customizedCount > 0 ? "badge-custom" : "badge-builtin"
              }`}
            >
              {customizedCount} Customized
            </span>
            <button
              className="btn-secondary"
              onClick={() => void loadPrompts()}
              disabled={isLoading}
            >
              {isLoading ? "Refreshing..." : "Refresh"}
            </button>
          </div>
        </div>

        {notice && (
          <div
            className={`notice ${notice.type === "error" ? "error" : "success"}`}
            style={{ marginTop: "16px" }}
          >
            {notice.text}
          </div>
        )}
      </section>

      <div className="prompts-studio-layout">
        {/* Sidebar: 8 Agents List */}
        <aside className="agents-sidebar">
          {agents.map((agent) => {
            const isSelected = agent.name === selectedName;
            return (
              <button
                key={agent.name}
                type="button"
                className={`agent-nav-item ${isSelected ? "active" : ""}`}
                onClick={() => handleSelectAgent(agent)}
              >
                <div className="agent-nav-header">
                  <span className="agent-nav-title">{agent.title}</span>
                  <span
                    className={`badge-pill ${
                      agent.is_customized ? "badge-custom" : "badge-builtin"
                    }`}
                  >
                    {agent.is_customized ? "Custom" : "v1"}
                  </span>
                </div>
                <span className="agent-nav-role">{agent.role}</span>
              </button>
            );
          })}
        </aside>

        {/* Main Editor & Playground Area */}
        <section>
          {selectedAgent ? (
            <div>
              {/* Agent Top Details & Action Toolbar */}
              <div className="editor-header-card">
                <div className="editor-header-top">
                  <div>
                    <div
                      style={{
                        display: "flex",
                        alignItems: "center",
                        gap: "10px",
                      }}
                    >
                      <h2 style={{ margin: 0, fontSize: "1.35rem" }}>
                        {selectedAgent.title}
                      </h2>
                      <span
                        className={`badge-pill ${
                          selectedAgent.is_customized
                            ? "badge-custom"
                            : "badge-builtin"
                        }`}
                      >
                        {selectedAgent.is_customized
                          ? "Custom Override Active"
                          : "Factory Default (v1.yaml)"}
                      </span>
                      <span className="badge-pill badge-model">
                        Model: {selectedAgent.default_model}
                      </span>
                    </div>
                    <p
                      style={{
                        fontSize: "0.86rem",
                        color: "var(--muted)",
                        margin: "6px 0 0 0",
                      }}
                    >
                      {selectedAgent.description}
                    </p>
                  </div>

                  <div className="editor-actions-bar">
                    {isDirty && (
                      <span className="unsaved-indicator">
                        ● Unsaved edits
                      </span>
                    )}

                    <button
                      type="button"
                      className="btn-secondary"
                      onClick={() => setShowDiff(!showDiff)}
                    >
                      {showDiff ? "Hide Diff" : "Compare with Default"}
                    </button>

                    {selectedAgent.is_customized && !confirmReset && (
                      <button
                        type="button"
                        className="btn-danger-outline"
                        onClick={() => setConfirmReset(true)}
                        disabled={isResetting}
                      >
                        Reset to Default
                      </button>
                    )}

                    {confirmReset && (
                      <div
                        style={{
                          display: "inline-flex",
                          gap: "6px",
                          alignItems: "center",
                        }}
                      >
                        <button
                          type="button"
                          className="btn-danger-outline"
                          style={{
                            background: "#fef2f2",
                            borderColor: "var(--danger)",
                          }}
                          onClick={() => void handleReset()}
                          disabled={isResetting}
                        >
                          {isResetting ? "Resetting..." : "Confirm Revert to v1"}
                        </button>
                        <button
                          type="button"
                          className="btn-secondary"
                          onClick={() => setConfirmReset(false)}
                        >
                          Cancel
                        </button>
                      </div>
                    )}

                    <button
                      type="button"
                      onClick={() => void handleSave()}
                      disabled={isSaving || !isDirty}
                      style={{ minWidth: "120px" }}
                    >
                      {isSaving ? "Saving..." : "Save Prompt"}
                    </button>
                  </div>
                </div>

                {/* Expected Output Schema Reference */}
                <div
                  style={{
                    marginTop: "14px",
                    padding: "10px 14px",
                    borderRadius: "8px",
                    background: "#f8fafc",
                    border: "1px solid var(--line)",
                    fontSize: "0.82rem",
                  }}
                >
                  <strong style={{ color: "#334155" }}>Contract Output Schema:</strong>{" "}
                  <code style={{ color: "var(--brand-dark)" }}>
                    {selectedAgent.output_schema_summary}
                  </code>
                </div>
              </div>

              {/* Diff Viewer (if toggled) */}
              {showDiff && (
                <div
                  className="card"
                  style={{ padding: "18px", marginBottom: "20px" }}
                >
                  <div
                    style={{
                      display: "flex",
                      justifyContent: "space-between",
                      alignItems: "center",
                      marginBottom: "10px",
                    }}
                  >
                    <h3 style={{ margin: 0, fontSize: "1rem" }}>
                      Side-by-Side Comparison
                    </h3>
                    <span
                      style={{ fontSize: "0.78rem", color: "var(--muted)" }}
                    >
                      Original v1.yaml vs Current Editor Draft
                    </span>
                  </div>
                  <div className="prompt-diff-grid">
                    <div className="diff-box">
                      <div className="diff-box-header">
                        <span>Original Factory Prompt (v1.yaml)</span>
                        <span>{selectedAgent.default_prompt.length} chars</span>
                      </div>
                      <pre className="diff-content">
                        {selectedAgent.default_prompt}
                      </pre>
                    </div>
                    <div className="diff-box">
                      <div className="diff-box-header">
                        <span style={{ color: "var(--brand)" }}>
                          Current Working Prompt
                        </span>
                        <span>{editedPrompt.length} chars</span>
                      </div>
                      <pre className="diff-content">{editedPrompt}</pre>
                    </div>
                  </div>
                </div>
              )}

              {/* Prompt Textarea Editor */}
              <div className="card" style={{ padding: "20px" }}>
                <div
                  style={{
                    display: "flex",
                    justifyContent: "space-between",
                    alignItems: "center",
                    marginBottom: "8px",
                  }}
                >
                  <label
                    htmlFor="promptEditor"
                    style={{ fontWeight: 700, fontSize: "0.92rem", margin: 0 }}
                  >
                    System Prompt Instructions
                  </label>
                  <div style={{ display: "flex", gap: "12px", alignItems: "center" }}>
                    <span style={{ fontSize: "0.8rem", color: "var(--muted)" }}>
                      Approx. {Math.round(editedPrompt.length / 4)} tokens
                    </span>
                    <span style={{ fontSize: "0.8rem", color: "var(--muted)" }}>
                      {editedPrompt.length} characters
                    </span>
                  </div>
                </div>

                <textarea
                  id="promptEditor"
                  className="prompt-textarea"
                  value={editedPrompt}
                  onChange={(e) => setEditedPrompt(e.target.value)}
                  placeholder="Enter system prompt instructions..."
                  spellCheck={false}
                />

                <div className="editor-footer-stats">
                  <div>
                    {selectedAgent.updated_at && (
                      <span>
                        Last updated:{" "}
                        {new Date(selectedAgent.updated_at).toLocaleString()}
                        {selectedAgent.change_summary
                          ? ` (${selectedAgent.change_summary})`
                          : ""}
                      </span>
                    )}
                  </div>
                  <div style={{ display: "flex", gap: "8px", alignItems: "center" }}>
                    <input
                      type="text"
                      placeholder="Optional version note (e.g. Added safety rule)"
                      value={changeSummary}
                      onChange={(e) => setChangeSummary(e.target.value)}
                      style={{
                        padding: "6px 10px",
                        fontSize: "0.82rem",
                        width: "280px",
                      }}
                    />
                  </div>
                </div>
              </div>

              {/* Live Playground & Testing Panel */}
              <div className="playground-container">
                <div className="playground-header">
                  <div>
                    <h3 style={{ margin: 0, fontSize: "1.1rem" }}>
                      Live Playground & Schema Verification
                    </h3>
                    <p
                      style={{
                        margin: "4px 0 0 0",
                        fontSize: "0.82rem",
                        color: "var(--muted)",
                      }}
                    >
                      Run this agent with sample payload or test an ad-hoc draft
                      prompt before committing changes.
                    </p>
                  </div>
                  <div style={{ display: "flex", gap: "8px" }}>
                    <button
                      type="button"
                      className="btn-secondary"
                      onClick={handleLoadSample}
                      style={{ fontSize: "0.82rem", padding: "6px 12px" }}
                    >
                      Reset Sample
                    </button>
                    <button
                      type="button"
                      onClick={() => void handleRunTest()}
                      disabled={isTesting}
                      style={{
                        fontSize: "0.82rem",
                        padding: "6px 16px",
                        background: "var(--brand)",
                      }}
                    >
                      {isTesting ? "Executing..." : "Run Test"}
                    </button>
                  </div>
                </div>

                {testError && (
                  <div
                    className="notice error"
                    style={{ marginBottom: "16px", fontSize: "0.84rem" }}
                  >
                    {testError}
                  </div>
                )}

                <div className="playground-grid">
                  <div>
                    <div
                      style={{
                        fontSize: "0.8rem",
                        fontWeight: 700,
                        marginBottom: "6px",
                        color: "#334155",
                      }}
                    >
                      Test Input Payload (JSON)
                    </div>
                    <textarea
                      className="payload-textarea"
                      value={testPayloadText}
                      onChange={(e) => setTestPayloadText(e.target.value)}
                      spellCheck={false}
                    />
                  </div>

                  <div>
                    <div
                      style={{
                        fontSize: "0.8rem",
                        fontWeight: 700,
                        marginBottom: "6px",
                        display: "flex",
                        justifyContent: "space-between",
                        color: "#334155",
                      }}
                    >
                      <span>Structured Agent Output</span>
                      {testResult && (
                        <span>
                          Latency: <strong>{testResult.latency_ms} ms</strong> |{" "}
                          Status:{" "}
                          <span
                            style={{
                              color:
                                testResult.status === "success"
                                  ? "var(--success)"
                                  : "var(--warning)",
                            }}
                          >
                            {testResult.status.toUpperCase()}
                          </span>
                        </span>
                      )}
                    </div>
                    <pre className="test-output-box">
                      {isTesting
                        ? "Calling LLM model gateway..."
                        : testResult
                          ? JSON.stringify(testResult.output, null, 2)
                          : "// Click 'Run Test' above to execute the agent with the current prompt"}
                    </pre>
                  </div>
                </div>
              </div>
            </div>
          ) : (
            <div className="card">Loading agent details...</div>
          )}
        </section>
      </div>
    </div>
  );
}
