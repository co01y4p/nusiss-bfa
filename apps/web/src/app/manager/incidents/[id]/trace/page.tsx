"use client";

import { useParams, useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { apiRequest, managerHeaders } from "@/lib/api";

type TraceStep = {
  sequence: number;
  node: string;
  input?: Record<string, unknown> | null;
  output: Record<string, unknown>;
  reason_codes: string[];
};

type Trace = {
  id: string;
  incident_id: string;
  outcome: string;
  final_response: string;
  trace: TraceStep[];
  created_at: string;
};

export default function IncidentTracePage() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const [trace, setTrace] = useState<Trace | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    apiRequest<Trace>(`/incidents/${encodeURIComponent(id)}/trace`, {
      headers: managerHeaders(),
    })
      .then(setTrace)
      .catch((caught: unknown) => {
        const message =
          caught instanceof Error ? caught.message : "Unable to load trace";
        setError(message);
        if (message.includes("token")) router.replace("/manager");
      });
  }, [id, router]);

  return (
    <section className="card">
      <h1>Agent trace</h1>
      {error && <div className="notice error">{error}</div>}
      {trace && (
        <>
          <p>
            Outcome: <span className="pill">{trace.outcome}</span>
          </p>
          <p>{trace.final_response}</p>
          <ol className="trace">
            {trace.trace.map((step) => (
              <li key={`${step.sequence}-${step.node}`}>
                <strong>
                  {step.sequence}. {step.node}
                </strong>
                <div>{step.reason_codes.join(" | ")}</div>
                {step.input && (
                  <>
                    <strong>Input</strong>
                    <pre>{JSON.stringify(step.input, null, 2)}</pre>
                  </>
                )}
                <strong>Output</strong>
                <pre>{JSON.stringify(step.output, null, 2)}</pre>
              </li>
            ))}
          </ol>
        </>
      )}
    </section>
  );
}
