"use client";

import Link from "next/link";
import { FormEvent, useState } from "react";

import { apiRequest } from "@/lib/api";

type AssistantResult = {
  outcome: string;
  message: string;
  reference_code: string | null;
};

export default function AssistantPage() {
  const [messageText, setMessageText] = useState("");
  const [locationText, setLocationText] = useState("");
  const [result, setResult] = useState<AssistantResult | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!messageText.trim()) return;
    setBusy(true);
    setError("");
    try {
      setResult(
        await apiRequest<AssistantResult>("/assistant/messages", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            message: messageText.trim(),
            location: locationText.trim() || null,
          }),
        }),
      );
    } catch (caught) {
      setError(
        caught instanceof Error
          ? caught.message
          : "The assistant is unavailable",
      );
    } finally {
      setBusy(false);
    }
  }

  function setPreset(msg: string, loc: string = "") {
    setMessageText(msg);
    setLocationText(loc);
    setResult(null);
    setError("");
  }

  return (
    <>
      <section className="card">
        <h1>Facility Assistant (RAG)</h1>
        <p className="lede">
          Bounded multi-agent workflow grounded in approved facility documents.
          Answers factual questions with document citations and refuses
          unapproved topics.
        </p>

        {/* Quick Presets */}
        <div style={{ marginBottom: "1rem" }}>
          <div
            style={{
              fontSize: "0.85rem",
              fontWeight: 600,
              marginBottom: "0.5rem",
              color: "#555",
            }}
          >
            Quick Test Scenarios:
          </div>
          <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap" }}>
            <button
              type="button"
              className="small"
              onClick={() =>
                setPreset("What are the general building operating hours?")
              }
            >
              🏢 Building Hours (Approved QA)
            </button>
            <button
              type="button"
              className="small"
              onClick={() =>
                setPreset("What are the aircon temperature setpoints?")
              }
            >
              ❄️ Aircon Policy (Approved QA)
            </button>
            <button
              type="button"
              className="small"
              onClick={() =>
                setPreset(
                  "What number should I call for an elevator breakdown?",
                )
              }
            >
              🚨 Lift Emergency (Approved QA)
            </button>
            <button
              type="button"
              className="small"
              onClick={() =>
                setPreset("What is the secret wifi password on the 10th floor?")
              }
            >
              🔒 Unapproved Topic (Safe Fallback)
            </button>
            <button
              type="button"
              className="small"
              onClick={() =>
                setPreset(
                  "There is water dripping from the ceiling near the lifts",
                  "Level 2 Lobby",
                )
              }
            >
              ⚠️ Water Leak (Incident Report)
            </button>
          </div>
        </div>

        <form onSubmit={submit}>
          <label htmlFor="message">Message</label>
          <textarea
            id="message"
            name="message"
            value={messageText}
            onChange={(e) => setMessageText(e.target.value)}
            placeholder="e.g. What are the building operating hours?"
            maxLength={8000}
            required
          />
          <label htmlFor="location">Location, if applicable</label>
          <input
            id="location"
            name="location"
            value={locationText}
            onChange={(e) => setLocationText(e.target.value)}
            placeholder="e.g. Block B Level 2"
            maxLength={200}
          />
          <div
            style={{
              display: "flex",
              gap: "1rem",
              alignItems: "center",
              marginTop: "0.5rem",
            }}
          >
            <button
              type="submit"
              disabled={busy}
              style={{ width: "auto", padding: "0.5rem 1.5rem" }}
            >
              {busy ? "Running agent graph..." : "Send to Assistant"}
            </button>
            <Link href="/knowledge" style={{ fontSize: "0.9rem" }}>
              Manage Knowledge Documents &rarr;
            </Link>
          </div>
        </form>
        {error && (
          <div className="notice error" style={{ marginTop: "1rem" }}>
            {error}
          </div>
        )}
      </section>

      {result && (
        <section className="card">
          <div
            className="actions"
            style={{
              display: "flex",
              justifyContent: "space-between",
              alignItems: "center",
            }}
          >
            <h2>Response</h2>
            <span
              className="pill"
              style={{
                background:
                  result.outcome === "FINALIZED" ? "#2e7d32" : "#e65100",
                color: "#fff",
              }}
            >
              {result.outcome}
            </span>
          </div>

          <div
            style={{
              padding: "1rem",
              background: "#f9f9f9",
              borderRadius: "6px",
              border: "1px solid #e0e0e0",
              margin: "0.75rem 0",
              fontSize: "1.05rem",
              lineHeight: 1.5,
            }}
          >
            {result.message}
          </div>

          {result.reference_code && (
            <div style={{ margin: "0.5rem 0" }}>
              <strong>Tracking Reference Code:</strong>{" "}
              <code style={{ fontSize: "1rem", fontWeight: "bold" }}>
                {result.reference_code}
              </code>{" "}
              (<Link href="/track">Track incident</Link>)
            </div>
          )}

          <p className="lede" style={{ marginTop: "0.75rem" }}>
            Review full citation validation and retrieval trace in the{" "}
            <Link href="/manager">Manager Queue</Link> or test raw vector
            similarities in the <Link href="/knowledge">Knowledge Studio</Link>.
          </p>
        </section>
      )}
    </>
  );
}
