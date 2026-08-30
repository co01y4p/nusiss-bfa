"use client";

import { FormEvent, useState } from "react";

import { apiRequest } from "@/lib/api";

type TrackedIncident = {
  reference_code: string;
  status: string;
  location: string;
  created_at: string;
  updated_at: string;
};

export default function TrackPage() {
  const [incident, setIncident] = useState<TrackedIncident | null>(null);
  const [error, setError] = useState("");

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    setIncident(null);
    const code = String(
      new FormData(event.currentTarget).get("code") ?? "",
    ).trim();
    try {
      setIncident(
        await apiRequest<TrackedIncident>(
          `/incidents/track/${encodeURIComponent(code)}`,
        ),
      );
    } catch (caught) {
      setError(
        caught instanceof Error ? caught.message : "Unable to find the report",
      );
    }
  }

  return (
    <section className="card">
      <h1>Track a report</h1>
      <form onSubmit={submit}>
        <label htmlFor="code">Reference code</label>
        <input id="code" name="code" placeholder="BFA-XXXXXXXXXX" required />
        <button>Check status</button>
      </form>
      {incident && (
        <div className="notice success">
          <strong>{incident.reference_code}</strong>
          <p>Status: {incident.status.replaceAll("_", " ")}</p>
          <p>Location: {incident.location}</p>
          <p>Last updated: {new Date(incident.updated_at).toLocaleString()}</p>
        </div>
      )}
      {error && <div className="notice error">{error}</div>}
    </section>
  );
}
