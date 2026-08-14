// Facilities AI Assistant — vanilla demo Worker (M1 slice: save-before-AI).
// Site-wide gate: every page and API route requires a signed-in Google account
// (see /login.html), except the small pre-auth allowlist below. Manager-only
// routes additionally require the signed-in email to be on MANAGER_EMAILS.
//
//   GET   /api/v1/auth/config                      (public)  {google_client_id}
//   POST  /api/v1/auth/google                      (public)  verify Google ID token, mint session
//   GET   /api/v1/auth/me                           (session) {email, role}
//   POST  /api/v1/auth/logout                       (public)  clear session
//   POST  /api/v1/incidents                        (session)  create incident
//   GET   /api/v1/incidents/track/:reference_code  (session)  status lookup
//   GET   /api/v1/incidents                        (manager)  list
//   PATCH /api/v1/incidents/:id/status             (manager)  update status

import { SignJWT, jwtVerify, createRemoteJWKSet } from "jose";

const STATUSES = ["RECEIVED", "IN_PROGRESS", "RESOLVED", "CLOSED"];
const SESSION_COOKIE = "bfa_session";
const SESSION_MAX_AGE_SECONDS = 7 * 24 * 60 * 60; // 7 days

// Paths reachable with no session — must stay small, this is the auth bootstrap surface.
const PRE_AUTH_PATHS = new Set([
  "/login.html",
  "/login", // Cloudflare asset serving canonicalizes /login.html -> /login
  "/styles.css",
  "/api/v1/auth/config",
  "/api/v1/auth/google",
  "/api/v1/auth/logout",
]);

const GOOGLE_JWKS = createRemoteJWKSet(
  new URL("https://www.googleapis.com/oauth2/v3/certs")
);

const json = (data, status = 200, headers = {}) =>
  new Response(JSON.stringify(data), {
    status,
    headers: { "content-type": "application/json", ...headers },
  });

function makeReferenceCode() {
  const alphabet = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"; // no confusable chars
  const bytes = crypto.getRandomValues(new Uint8Array(8));
  let code = "";
  for (const b of bytes) code += alphabet[b % alphabet.length];
  return `BFA-${code}`;
}

function readCookie(request, name) {
  const header = request.headers.get("cookie");
  if (!header) return null;
  for (const part of header.split(";")) {
    const eq = part.indexOf("=");
    if (eq === -1) continue;
    if (part.slice(0, eq).trim() === name) return part.slice(eq + 1).trim();
  }
  return null;
}

function sessionCookieHeader(value, maxAgeSeconds) {
  return `${SESSION_COOKIE}=${value}; HttpOnly; Secure; SameSite=Lax; Path=/; Max-Age=${maxAgeSeconds}`;
}

function managerEmailSet(env) {
  return new Set(
    (env.MANAGER_EMAILS ?? "")
      .split(",")
      .map((e) => e.trim().toLowerCase())
      .filter(Boolean)
  );
}

// Returns null if unconfigured — callers MUST treat that as "no session possible"
// rather than falling back to an empty/undefined key, which would make session
// JWTs trivially forgeable (TextEncoder().encode(undefined) silently yields "").
function getSessionSecret(env) {
  if (!env.SESSION_SECRET) return null;
  return new TextEncoder().encode(env.SESSION_SECRET);
}

async function mintSession(email, env) {
  const secret = getSessionSecret(env);
  if (!secret) throw new Error("SESSION_SECRET is not configured");
  const role = managerEmailSet(env).has(email.toLowerCase()) ? "MANAGER" : "USER";
  const jwt = await new SignJWT({ email, role })
    .setProtectedHeader({ alg: "HS256" })
    .setIssuedAt()
    .setExpirationTime(`${SESSION_MAX_AGE_SECONDS}s`)
    .sign(secret);
  return { jwt, role };
}

async function verifySession(request, env) {
  const token = readCookie(request, SESSION_COOKIE);
  if (!token) return null;
  const secret = getSessionSecret(env);
  if (!secret) return null; // fail closed: unconfigured secret means nobody has a session
  try {
    const { payload } = await jwtVerify(token, secret, { algorithms: ["HS256"] });
    if (typeof payload.email !== "string" || typeof payload.role !== "string") return null;
    return { email: payload.email, role: payload.role };
  } catch {
    return null;
  }
}

function isManager(session) {
  return session?.role === "MANAGER";
}

async function handleAuthConfig(env) {
  if (!env.GOOGLE_CLIENT_ID) return json({ error: "Google sign-in not configured" }, 500);
  return json({ google_client_id: env.GOOGLE_CLIENT_ID });
}

async function handleAuthGoogle(request, env) {
  if (!env.GOOGLE_CLIENT_ID) return json({ error: "Google sign-in not configured" }, 500);

  let body;
  try {
    body = await request.json();
  } catch {
    return json({ error: "Invalid JSON body" }, 400);
  }
  const credential = (body.credential ?? "").toString();
  if (!credential) return json({ error: "credential is required" }, 422);

  let payload;
  try {
    ({ payload } = await jwtVerify(credential, GOOGLE_JWKS, {
      issuer: ["https://accounts.google.com", "accounts.google.com"],
      audience: env.GOOGLE_CLIENT_ID,
    }));
  } catch (err) {
    return json({ error: "Invalid Google credential", detail: `${err}` }, 401);
  }

  if (!payload.email || payload.email_verified !== true) {
    return json({ error: "Google account email not verified" }, 401);
  }

  const { jwt, role } = await mintSession(payload.email, env);
  return json(
    { email: payload.email, role },
    200,
    { "set-cookie": sessionCookieHeader(jwt, SESSION_MAX_AGE_SECONDS) }
  );
}

async function handleAuthMe(request, env) {
  const session = await verifySession(request, env);
  if (!session) return json({ error: "Unauthorized" }, 401);
  return json({ email: session.email, role: session.role });
}

async function handleAuthLogout() {
  return json({ ok: true }, 200, { "set-cookie": sessionCookieHeader("", 0) });
}

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    const path = url.pathname;
    const method = request.method;

    try {
      // --- Pre-auth bootstrap routes (reachable with no session) ---
      if (path === "/api/v1/auth/config" && method === "GET") return handleAuthConfig(env);
      if (path === "/api/v1/auth/google" && method === "POST") return handleAuthGoogle(request, env);
      if (path === "/api/v1/auth/logout" && method === "POST") return handleAuthLogout();

      // --- Site-wide session gate ---
      const session = PRE_AUTH_PATHS.has(path) ? null : await verifySession(request, env);
      if (!PRE_AUTH_PATHS.has(path) && !session) {
        if (path.startsWith("/api/")) return json({ error: "Unauthorized" }, 401);
        const next = encodeURIComponent(path + url.search);
        return Response.redirect(`${url.origin}/login?next=${next}`, 302);
      }

      if (path === "/api/v1/auth/me" && method === "GET") return handleAuthMe(request, env);

      // --- Incident routes (any signed-in session) ---
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
        if (!isManager(session)) return json({ error: "Forbidden" }, 403);
        const { results } = await env.DB.prepare(
          `SELECT id, reference_code, description, location, status, created_at, updated_at
           FROM incidents ORDER BY created_at DESC LIMIT 200`
        ).all();
        return json({ incidents: results });
      }

      const statusMatch = path.match(/^\/api\/v1\/incidents\/([0-9a-f-]{36})\/status$/);
      if (statusMatch && method === "PATCH") {
        if (!isManager(session)) return json({ error: "Forbidden" }, 403);
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
