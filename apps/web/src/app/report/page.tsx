"use client";

import { FormEvent, useState } from "react";

import { apiRequest } from "@/lib/api";

type CreatedIncident = { id: string; reference_code: string; status: string };

export default function ReportPage() {
  const [result, setResult] = useState<CreatedIncident | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setError("");
    const form = new FormData(event.currentTarget);
    try {
      const created = await apiRequest<CreatedIncident>("/incidents", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          location: form.get("location"),
          description: form.get("description"),
        }),
      });
      setResult(created);
      event.currentTarget.reset();
    } catch (caught) {
      setError(
        caught instanceof Error
          ? caught.message
          : "Unable to submit the report",
      );
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="card">
      <h1>Report a facility issue</h1>
      <p className="lede">
        Reports are saved immediately and do not depend on the AI workflow.
      </p>
      <form onSubmit={submit}>
        <label htmlFor="location">Location</label>
        <input id="location" name="location" maxLength={200} required />
        <label htmlFor="description">Description</label>
        <textarea
          id="description"
          name="description"
          maxLength={4000}
          required
        />
        <button disabled={busy}>
          {busy ? "Submitting..." : "Submit report"}
        </button>
      </form>
      {result && (
        <div className="notice success">
          Report saved. Reference: <strong>{result.reference_code}</strong>
        </div>
      )}
      {error && <div className="notice error">{error}</div>}
    </section>
  );
}
