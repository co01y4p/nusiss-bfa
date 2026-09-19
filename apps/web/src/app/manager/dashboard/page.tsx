"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";

import { apiRequest, managerHeaders } from "@/lib/api";

const statuses = ["RECEIVED", "IN_PROGRESS", "RESOLVED", "CLOSED"];

type Meta = { label: string; color: string };

// Colors match the building map's category coding (components/building-map.tsx)
// so a category reads the same way anywhere it shows up in the app.
const CATEGORY_META: Record<string, Meta> = {
  HVAC: { label: "HVAC", color: "#1457d9" },
  ELECTRICAL: { label: "Electrical", color: "#a15c00" },
  PLUMBING: { label: "Plumbing", color: "#0f7a8c" },
  LIFT: { label: "Lift", color: "#6d3fa0" },
  ACCESS: { label: "Access", color: "#167447" },
  GENERAL: { label: "General", color: "#47536b" },
};

const TEAM_META: Record<string, Meta> = {
  HVAC_TEAM: { label: "HVAC Team", color: CATEGORY_META.HVAC.color },
  ELECTRICAL_TEAM: {
    label: "Electrical Team",
    color: CATEGORY_META.ELECTRICAL.color,
  },
  PLUMBING_TEAM: {
    label: "Plumbing Team",
    color: CATEGORY_META.PLUMBING.color,
  },
  LIFT_TEAM: { label: "Lift Team", color: CATEGORY_META.LIFT.color },
  SECURITY_TEAM: { label: "Security Team", color: "#b42318" },
  FACILITIES_DESK: { label: "Facilities Desk", color: "#5e687a" },
};

const PRIORITY_META: Record<string, Meta> = {
  P1: { label: "1", color: "#b42318" },
  P2: { label: "2", color: "#c2410c" },
  P3: { label: "3", color: "#1457d9" },
  P4: { label: "4", color: "#5e687a" },
};

const PRIORITY_LEGEND: Meta[] = [
  { label: "1 · Most urgent", color: PRIORITY_META.P1.color },
  { label: "2", color: PRIORITY_META.P2.color },
  { label: "3", color: PRIORITY_META.P3.color },
  { label: "4 · Least urgent", color: PRIORITY_META.P4.color },
];

const INTENT_META: Record<string, Meta> = {
  INCIDENT_REPORT: { label: "Incident Report", color: "#1457d9" },
  FACILITY_QA: { label: "Facility Q&A", color: "#0f7a8c" },
  STATUS_QUERY: { label: "Status Query", color: "#6d3fa0" },
  FEEDBACK: { label: "Feedback", color: "#167447" },
  OTHER: { label: "Other", color: "#47536b" },
};

const MANUAL_INTENT_META: Meta = { label: "Manual entry", color: "#5e687a" };

function Chip({ label, color }: { label: string; color: string }) {
  return (
    <span className="legend-item">
      <span className="legend-dot" style={{ background: color }} />
      {label}
    </span>
  );
}

function Badge({
  meta,
  fallback,
}: {
  meta: Meta | undefined;
  fallback: string;
}) {
  if (!meta) {
    return (
      <span
        className="badge"
        style={{ color: "#5e687a", background: "#eef1f6" }}
      >
        {fallback}
      </span>
    );
  }
  return (
    <span
      className="badge"
      style={{ color: meta.color, background: `${meta.color}18` }}
    >
      <span className="badge-dot" />
      {meta.label}
    </span>
  );
}

type Incident = {
  id: string;
  reference_code: string;
  description: string;
  location: string;
  status: string;
  category: string | null;
  priority: string | null;
  assigned_team: string | null;
  intent: string | null;
  requires_human_review: boolean;
  override_reason?: string | null;
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
      if (message.includes("token")) {
        localStorage.removeItem("bfa_manager_token");
        router.replace("/manager");
      }
    }
  }, [router]);

  useEffect(() => {
    const task = window.setTimeout(() => void load(), 0);
    return () => window.clearTimeout(task);
  }, [load]);

  const [statusDialog, setStatusDialog] = useState<{
    incident: Incident;
    targetStatus: string;
    reason: string;
  } | null>(null);
  const [isUpdating, setIsUpdating] = useState(false);

  async function confirmStatusUpdate() {
    if (!statusDialog) return;
    const trimmedReason = statusDialog.reason.trim();
    if (!trimmedReason) {
      setError("A documented reason is required to change incident status.");
      return;
    }
    setIsUpdating(true);
    setError("");
    try {
      await apiRequest(`/incidents/${statusDialog.incident.id}/status`, {
        method: "PATCH",
        headers: { ...managerHeaders(), "Content-Type": "application/json" },
        body: JSON.stringify({
          status: statusDialog.targetStatus,
          reason: trimmedReason,
        }),
      });
      setStatusDialog(null);
      await load();
    } catch (caught) {
      setError(
        caught instanceof Error ? caught.message : "Status update failed",
      );
      await load();
    } finally {
      setIsUpdating(false);
    }
  }

  function signOut() {
    localStorage.removeItem("bfa_manager_token");
    router.push("/manager");
  }

  return (
    <section className="card card-wide">
      <div className="actions">
        <h1>Incident queue</h1>
        <Link className="button-link button-secondary" href="/manager/building">
          Building setup
        </Link>
        <button onClick={signOut}>Sign out</button>
      </div>
      {error && <div className="notice error">{error}</div>}

      <div className="legend">
        <div>
          <span className="legend-heading">Classification</span>
          <div className="legend-chips">
            {Object.entries(CATEGORY_META).map(([key, meta]) => (
              <Chip key={key} label={meta.label} color={meta.color} />
            ))}
          </div>
        </div>
        <div>
          <span className="legend-heading">Priority</span>
          <div className="legend-chips">
            {PRIORITY_LEGEND.map((meta) => (
              <Chip key={meta.label} label={meta.label} color={meta.color} />
            ))}
          </div>
        </div>
        <div>
          <span className="legend-heading">Response Team</span>
          <div className="legend-chips">
            {Object.entries(TEAM_META).map(([key, meta]) => (
              <Chip key={key} label={meta.label} color={meta.color} />
            ))}
          </div>
        </div>
        <div>
          <span className="legend-heading">Intent</span>
          <div className="legend-chips">
            {Object.entries(INTENT_META).map(([key, meta]) => (
              <Chip key={key} label={meta.label} color={meta.color} />
            ))}
          </div>
          <p className="legend-note">
            Decided by the assistant before an incident exists — only
            &ldquo;Incident Report&rdquo; messages create a row below. Incidents
            logged without going through the assistant show as &ldquo;Manual
            entry&rdquo;.
          </p>
        </div>
      </div>

      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Reference</th>
              <th>Issue</th>
              <th>Intent</th>
              <th>Classification</th>
              <th>Priority</th>
              <th>Response Team</th>
              <th>Status</th>
              <th>Trace</th>
            </tr>
          </thead>
          <tbody>
            {incidents.length === 0 && (
              <tr>
                <td className="empty-row" colSpan={8}>
                  No incidents yet.
                </td>
              </tr>
            )}
            {incidents.map((incident) => (
              <tr key={incident.id}>
                <td>
                  <strong>{incident.reference_code}</strong>
                  <br />
                  {incident.location}
                </td>
                <td>{incident.description}</td>
                <td>
                  {incident.intent ? (
                    <Badge
                      meta={INTENT_META[incident.intent]}
                      fallback={incident.intent}
                    />
                  ) : (
                    <Badge meta={MANUAL_INTENT_META} fallback="Manual entry" />
                  )}
                </td>
                <td>
                  {incident.category ? (
                    <Badge
                      meta={CATEGORY_META[incident.category]}
                      fallback={incident.category}
                    />
                  ) : (
                    <span
                      className="badge"
                      style={{ color: "#5e687a", background: "#eef1f6" }}
                    >
                      Unclassified
                    </span>
                  )}
                  {incident.requires_human_review && (
                    <div className="review-flag">Needs review</div>
                  )}
                </td>
                <td>
                  {incident.priority ? (
                    <Badge
                      meta={PRIORITY_META[incident.priority]}
                      fallback={incident.priority}
                    />
                  ) : (
                    <span
                      className="badge"
                      style={{ color: "#5e687a", background: "#eef1f6" }}
                    >
                      Pending
                    </span>
                  )}
                </td>
                <td>
                  {incident.assigned_team ? (
                    <Badge
                      meta={TEAM_META[incident.assigned_team]}
                      fallback={incident.assigned_team}
                    />
                  ) : (
                    <span
                      className="badge"
                      style={{ color: "#5e687a", background: "#eef1f6" }}
                    >
                      Unassigned
                    </span>
                  )}
                </td>
                <td>
                  <select
                    aria-label={`Status for ${incident.reference_code}`}
                    value={incident.status}
                    onChange={(event) => {
                      const nextStatus = event.target.value;
                      if (nextStatus !== incident.status) {
                        setStatusDialog({
                          incident,
                          targetStatus: nextStatus,
                          reason: "",
                        });
                      }
                    }}
                  >
                    {statuses.map((status) => (
                      <option key={status}>{status}</option>
                    ))}
                  </select>
                  {incident.override_reason && (
                    <div
                      style={{
                        fontSize: "0.75rem",
                        color: "var(--muted)",
                        marginTop: 4,
                        maxWidth: 160,
                        overflow: "hidden",
                        textOverflow: "ellipsis",
                        whiteSpace: "nowrap",
                      }}
                      title={`Override reason: ${incident.override_reason}`}
                    >
                      Reason: {incident.override_reason}
                    </div>
                  )}
                </td>
                <td>
                  {incident.category ? (
                    <Link href={`/manager/incidents/${incident.id}/trace`}>
                      View
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

      {statusDialog && (
        <div
          role="dialog"
          aria-modal="true"
          aria-labelledby="status-dialog-title"
          style={{
            position: "fixed",
            inset: 0,
            background: "rgba(15, 23, 42, 0.6)",
            backdropFilter: "blur(4px)",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            zIndex: 1000,
            padding: 16,
          }}
        >
          <div
            className="card"
            style={{
              maxWidth: 480,
              width: "100%",
              margin: 0,
              boxShadow: "0 20px 40px rgba(0,0,0,0.2)",
            }}
          >
            <h3 id="status-dialog-title" style={{ marginTop: 0, marginBottom: 12 }}>
              Update Status: {statusDialog.incident.reference_code}
            </h3>
            <p style={{ color: "var(--muted)", fontSize: "0.95rem", marginBottom: 16 }}>
              Transition status from{" "}
              <strong>{statusDialog.incident.status}</strong> to{" "}
              <strong style={{ color: "var(--brand)" }}>
                {statusDialog.targetStatus}
              </strong>
              . A documented reason is required for human oversight and auditability.
            </p>
            <label
              htmlFor="status-reason-input"
              style={{
                display: "block",
                fontWeight: 600,
                marginBottom: 6,
                fontSize: "0.9rem",
              }}
            >
              Override Reason / Operational Note:
            </label>
            <textarea
              id="status-reason-input"
              rows={3}
              value={statusDialog.reason}
              onChange={(e) =>
                setStatusDialog({ ...statusDialog, reason: e.target.value })
              }
              placeholder="e.g. Technician dispatched on-site, issue confirmed resolved, or false report."
              style={{
                width: "100%",
                padding: "8px 12px",
                borderRadius: 8,
                border: "1px solid var(--line)",
                fontFamily: "inherit",
                fontSize: "0.95rem",
                marginBottom: 16,
                resize: "vertical",
              }}
              autoFocus
            />
            <div style={{ display: "flex", justifyContent: "flex-end", gap: 12 }}>
              <button
                type="button"
                className="button-secondary"
                disabled={isUpdating}
                onClick={() => setStatusDialog(null)}
              >
                Cancel
              </button>
              <button
                type="button"
                disabled={isUpdating || !statusDialog.reason.trim()}
                onClick={() => void confirmStatusUpdate()}
              >
                {isUpdating ? "Saving..." : "Confirm Override"}
              </button>
            </div>
          </div>
        </div>
      )}
    </section>
  );
}
