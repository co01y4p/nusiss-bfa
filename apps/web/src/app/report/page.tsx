"use client";

import { FormEvent, useRef, useState } from "react";

import { apiRequest } from "@/lib/api";

import BuildingMap, { SelectedFacility } from "./building-map";

type CreatedIncident = { id: string; reference_code: string; status: string };

export default function ReportPage() {
  const [location, setLocation] = useState("");
  const [description, setDescription] = useState("");
  const [selectedFacilityId, setSelectedFacilityId] = useState<string | null>(
    null,
  );
  const [result, setResult] = useState<CreatedIncident | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const descriptionRef = useRef<HTMLTextAreaElement>(null);

  function selectFacility(facility: SelectedFacility) {
    setSelectedFacilityId(facility.facilityId);
    setLocation(facility.locationLabel);
    setDescription((prev) => (prev.trim() ? prev : facility.example));
    descriptionRef.current?.focus();
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      const created = await apiRequest<CreatedIncident>("/incidents", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ location, description }),
      });
      setResult(created);
      setLocation("");
      setDescription("");
      setSelectedFacilityId(null);
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
        Click a facility in the building below to auto-fill the location and
        a sample description — the classification agent then routes reports
        by area (HVAC, lift, electrical, plumbing, access, general).
      </p>
      <BuildingMap selectedId={selectedFacilityId} onSelect={selectFacility} />
      <form onSubmit={submit}>
        <label htmlFor="location">Location</label>
        <input
          id="location"
          name="location"
          maxLength={200}
          required
          value={location}
          onChange={(event) => setLocation(event.target.value)}
        />
        <label htmlFor="description">Description</label>
        <textarea
          id="description"
          name="description"
          maxLength={4000}
          required
          ref={descriptionRef}
          value={description}
          onChange={(event) => setDescription(event.target.value)}
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
