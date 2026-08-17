"use client";

import { FormEvent, useState } from "react";

import { apiRequest } from "@/lib/api";

type AssistantResult = {
  outcome: string;
  message: string;
  reference_code: string | null;
};

export default function AssistantPage() {
  const [result, setResult] = useState<AssistantResult | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setError("");
    const form = new FormData(event.currentTarget);
    try {
      setResult(
        await apiRequest<AssistantResult>("/assistant/messages", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            message: form.get("message"),
            location: form.get("location") || null,
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

  return (
    <>
      <section className="card">
        <h1>Facility assistant</h1>
        <p className="lede">
          This M2 build uses deterministic fake agent responses. Routing and
          safety priority rules are real application code.
        </p>
        <form onSubmit={submit}>
          <label htmlFor="message">Message</label>
          <textarea
            id="message"
            name="message"
            placeholder="There is a gas smell near the level 2 lift lobby."
            maxLength={8000}
            required
          />
          <label htmlFor="location">Location, if known</label>
          <input id="location" name="location" maxLength={200} />
          <button disabled={busy}>
            {busy ? "Running workflow..." : "Send"}
          </button>
        </form>
        {error && <div className="notice error">{error}</div>}
      </section>

      {result && (
        <section className="card">
          <div className="actions">
            <h2>Outcome</h2>
            <span className="pill">{result.outcome}</span>
          </div>
          <p>{result.message}</p>
          {result.reference_code && <p>Reference: {result.reference_code}</p>}
          <p className="lede">
            Managers can inspect the protected workflow trace from the queue.
          </p>
        </section>
      )}
    </>
  );
}
