"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";

import { apiRequest, managerHeaders } from "@/lib/api";

const statuses = ["RECEIVED", "IN_PROGRESS", "RESOLVED", "CLOSED"];

type Incident = {
  id: string;
  reference_code: string;
  description: string;
  location: string;
  status: string;
  category: string | null;
  priority: string | null;
  assigned_team: string | null;
  requires_human_review: boolean;
  created_at: string;
};

export default function ManagerDashboardPage() {
  const router = useRouter();
  const [incidents, setIncidents] = useState<Incident[]>([]);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    try {
      const data = await apiRequest<{ incidents: Incident[] }>(
        "/incidents?limit=100",
        {
          headers: managerHeaders(),
        },
      );
      setIncidents(data.incidents);
    } catch (caught) {
      const message =
        caught instanceof Error ? caught.message : "Unable to load incidents";
      setError(message);
      if (message.includes("token")) router.replace("/manager");
    }
  }, [router]);

  useEffect(() => {
    const task = window.setTimeout(() => void load(), 0);
    return () => window.clearTimeout(task);
  }, [load]);

  async function updateStatus(id: string, status: string) {
    setError("");
    try {
      await apiRequest(`/incidents/${id}/status`, {
        method: "PATCH",
        headers: { ...managerHeaders(), "Content-Type": "application/json" },
        body: JSON.stringify({ status }),
      });
      await load();
    } catch (caught) {
      setError(
        caught instanceof Error ? caught.message : "Status update failed",
      );
      await load();
    }
  }

  function signOut() {
    localStorage.removeItem("bfa_manager_token");
    router.push("/manager");
  }

  return (
    <section className="card">
      <div className="actions">
        <h1>Incident queue</h1>
        <Link className="button-link button-secondary" href="/manager/building">
          Building setup
        </Link>
        <button onClick={signOut}>Sign out</button>
      </div>
      {error && <div className="notice error">{error}</div>}
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Reference</th>
              <th>Issue</th>
              <th>Triage</th>
              <th>Status</th>
              <th>Trace</th>
            </tr>
          </thead>
          <tbody>
            {incidents.map((incident) => (
              <tr key={incident.id}>
                <td>
                  <strong>{incident.reference_code}</strong>
                  <br />
                  {incident.location}
                </td>
                <td>{incident.description}</td>
                <td>
                  {incident.priority ?? "Pending"} /{" "}
                  {incident.category ?? "Unclassified"}
                  <br />
                  {incident.assigned_team ?? "Unassigned"}
                  {incident.requires_human_review && (
                    <div className="pill">Review</div>
                  )}
                </td>
                <td>
                  <select
                    aria-label={`Status for ${incident.reference_code}`}
                    value={incident.status}
                    onChange={(event) =>
                      void updateStatus(incident.id, event.target.value)
                    }
                  >
                    {statuses.map((status) => (
                      <option key={status}>{status}</option>
                    ))}
                  </select>
                </td>
                <td>
                  {incident.category ? (
                    <Link href={`/manager/incidents/${incident.id}/trace`}>
                      View trace
                    </Link>
                  ) : (
                    "No agent run"
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}
