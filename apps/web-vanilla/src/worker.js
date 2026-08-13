// Facilities AI Assistant — vanilla demo Worker (M1 slice: save-before-AI).
// API mirrors the plan's endpoint contract:
//   POST  /api/v1/incidents                       (public)  create incident
//   GET   /api/v1/incidents/track/:reference_code (public)  status lookup
//   GET   /api/v1/incidents                       (manager) list
//   PATCH /api/v1/incidents/:id/status            (manager) update status

const STATUSES = ["RECEIVED", "IN_PROGRESS", "RESOLVED", "CLOSED"];

const json = (data, status = 200) =>
  new Response(JSON.stringify(data), {
    status,
    headers: { "content-type": "application/json" },
  });

function makeReferenceCode() {
  const alphabet = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"; // no confusable chars
  const bytes = crypto.getRandomValues(new Uint8Array(8));
  let code = "";
  for (const b of bytes) code += alphabet[b % alphabet.length];
  return `BFA-${code}`;
}

function isManager(request, env) {
  return request.headers.get("x-manager-passcode") === env.MANAGER_PASSCODE;
}

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    const path = url.pathname;
    const method = request.method;

    try {
      if (path === "/api/v1/incidents" && method === "POST") {
        let body;
        try {
          body = await request.json();
        } catch {
          return json({ error: "Invalid JSON body" }, 400);
        }
        const description = (body.description ?? "").toString().trim();
        const location = (body.location ?? "").toString().trim();
        if (!description || !location) {
          return json({ error: "description and location are required" }, 422);
        }
        if (description.length > 4000 || location.length > 200) {
          return json({ error: "description or location too long" }, 422);
        }

        const id = crypto.randomUUID();
        const referenceCode = makeReferenceCode();
        const now = new Date().toISOString();
        await env.DB.prepare(
          `INSERT INTO incidents (id, reference_code, description, location, status, created_at, updated_at)
           VALUES (?, ?, ?, ?, 'RECEIVED', ?, ?)`
        )
          .bind(id, referenceCode, description, location, now, now)
          .run();

        return json({ reference_code: referenceCode, status: "RECEIVED" }, 201);
      }

      const trackMatch = path.match(/^\/api\/v1\/incidents\/track\/([A-Za-z0-9-]+)$/);
      if (trackMatch && method === "GET") {
        const row = await env.DB.prepare(
          `SELECT reference_code, status, location, created_at, updated_at
           FROM incidents WHERE reference_code = ?`
        )
          .bind(trackMatch[1].toUpperCase())
          .first();
        if (!row) return json({ error: "Not found" }, 404);
        return json(row);
      }

      if (path === "/api/v1/incidents" && method === "GET") {
        if (!isManager(request, env)) return json({ error: "Unauthorized" }, 401);
        const { results } = await env.DB.prepare(
          `SELECT id, reference_code, description, location, status, created_at, updated_at
           FROM incidents ORDER BY created_at DESC LIMIT 200`
        ).all();
        return json({ incidents: results });
      }

      const statusMatch = path.match(/^\/api\/v1\/incidents\/([0-9a-f-]{36})\/status$/);
      if (statusMatch && method === "PATCH") {
        if (!isManager(request, env)) return json({ error: "Unauthorized" }, 401);
        let body;
        try {
          body = await request.json();
        } catch {
          return json({ error: "Invalid JSON body" }, 400);
        }
        const status = (body.status ?? "").toString().toUpperCase();
        if (!STATUSES.includes(status)) {
          return json({ error: `status must be one of ${STATUSES.join(", ")}` }, 422);
        }
        const result = await env.DB.prepare(
          `UPDATE incidents SET status = ?, updated_at = ? WHERE id = ?`
        )
          .bind(status, new Date().toISOString(), statusMatch[1])
          .run();
        if (result.meta.changes === 0) return json({ error: "Not found" }, 404);
        return json({ id: statusMatch[1], status });
      }

      if (path.startsWith("/api/")) return json({ error: "Not found" }, 404);

      // Non-API paths fall through to static assets.
      return env.ASSETS.fetch(request);
    } catch (err) {
      return json({ error: "Internal error", detail: `${err}` }, 500);
    }
  },
};
