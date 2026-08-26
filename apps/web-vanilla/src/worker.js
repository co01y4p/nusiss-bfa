// Facilities AI Assistant — vanilla demo Worker (M1 slice: save-before-AI).
// Site-wide gate: every page and API route requires a signed-in Google account
// (see /login.html), except the small pre-auth allowlist below. Sign-in itself
// is restricted to the MANAGER_EMAILS allow-list — any other Google account is
// rejected at /api/v1/auth/google, before a session is ever minted.
//
// Local dev: set DISABLE_LOGIN=true in .dev.vars to skip Google sign-in
// entirely and act as a manager. Off by default (login enforced).
//
//   GET   /api/v1/auth/config                      (public)  {google_client_id}
//   POST  /api/v1/auth/google                      (public)  verify Google ID token, mint session
//   GET   /api/v1/auth/me                           (session) {email, role}
//   POST  /api/v1/auth/logout                       (public)  clear session
//   POST  /api/v1/chat                              (session) chat with Gemini 3.5 Flash Lite
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

// Local-dev escape hatch: set DISABLE_LOGIN=true in .dev.vars to skip the
// Google sign-in gate entirely and act as a manager. Defaults to unset
// (login enforced) so it must be opted into — never set this in production.
const DEV_SESSION = { email: "angyupin159753@gmail.com", role: "MANAGER" };

function authDisabled(env) {
  return (env.DISABLE_LOGIN ?? "").toString().trim().toLowerCase() === "true";
}

async function handleAuthConfig(env) {
  if (authDisabled(env)) return json({ disable_login: true });
  if (!env.GOOGLE_CLIENT_ID) return json({ error: "Google sign-in not configured" }, 500);
  return json({ google_client_id: env.GOOGLE_CLIENT_ID, disable_login: false });
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

  // Access to this app is restricted to the team allow-list, not just any
  // Google account — MANAGER_EMAILS doubles as the access gate for now.
  if (!managerEmailSet(env).has(payload.email.toLowerCase())) {
    return json({ error: "This Google account is not authorized to access this app" }, 403);
  }

  const { jwt, role } = await mintSession(payload.email, env);
  return json(
    { email: payload.email, role },
    200,
    { "set-cookie": sessionCookieHeader(jwt, SESSION_MAX_AGE_SECONDS) }
  );
}

async function handleAuthMe(session) {
  if (!session) return json({ error: "Unauthorized" }, 401);
  return json({ email: session.email, role: session.role });
}

async function handleAuthLogout() {
  return json({ ok: true }, 200, { "set-cookie": sessionCookieHeader("", 0) });
}

async function handleChat(request, env) {
  let body;
  try {
    body = await request.json();
  } catch {
    return json({ error: "Invalid JSON body" }, 400);
  }

  const message = (body.message ?? "").toString().trim();
  if (!message) {
    return json({ error: "message is required" }, 422);
  }
  if (message.length > 2000) {
    return json({ error: "message too long (max 2000 chars)" }, 422);
  }

  const apiKey = env.GEMINI_API_KEY;
  if (!apiKey) {
    return json(
      {
        error: "Gemini API is not configured. Please set GEMINI_API_KEY in .dev.vars (locally) or Cloudflare secrets.",
      },
      503
    );
  }

  const model = env.GEMINI_MODEL || "gemini-3.5-flash-lite";

  // Build conversation history if provided
  const contents = [];
  if (Array.isArray(body.history)) {
    for (const item of body.history.slice(-10)) {
      if (
        item &&
        (item.role === "user" || item.role === "model") &&
        typeof item.content === "string" &&
        item.content.trim()
      ) {
        contents.push({
          role: item.role,
          parts: [{ text: item.content.slice(0, 2000) }],
        });
      }
    }
  }

  // Add the current user message
  contents.push({
    role: "user",
    parts: [{ text: message }],
  });

  const systemInstruction = {
    parts: [
      {
        text: `You are the Facilities AI Assistant for the NUS-ISS Building Facilities Management system (nusiss-bfa).
Your goal is to answer simple facilities and building-related questions for building occupants and guide them on reporting issues or tracking requests.

Key guidelines:
1. Tone: Friendly, professional, clear, concise, and helpful.
2. Building Facilities Scope:
   - Reporting issues: Users can report facility defects (e.g., air conditioning leaks, broken lighting, plumbing issues, elevator faults, restroom supplies) via the "Report an issue" form. Once submitted, they receive an opaque reference code (e.g. BFA-XXXXXXXX).
   - Tracking: Users can check incident status (RECEIVED, IN_PROGRESS, RESOLVED, CLOSED) using their reference code on the "Track a report" page.
   - Operating Hours: General building access is 07:00 - 22:00 Monday to Saturday. Facilities management office is available 08:30 - 18:00 on weekdays.
   - Amenities: Meeting rooms, study areas, pantries with hot/cold water, restrooms on all levels, lift lobbies at core A and B.
3. Critical Emergencies:
   - If an occupant reports a dangerous emergency (e.g. fire, active smoke, gas leak smell, exposed live electric wires, elevator entrapment, severe structural flood), advise them immediately to evacuate if necessary and contact campus emergency services / security hotline (995 / Campus Security: 6874-1616) before filing a ticket.
4. Keep answers focused on facility assistance. If asked general knowledge questions outside facility operations, give a polite, brief answer and remind them of your facilities assistant role.`,
      },
    ],
  };

  const payload = {
    system_instruction: systemInstruction,
    contents,
    generationConfig: {
      temperature: 0.7,
      maxOutputTokens: 1000,
    },
  };

  try {
    const geminiUrl = `https://generativelanguage.googleapis.com/v1beta/models/${encodeURIComponent(
      model
    )}:generateContent?key=${encodeURIComponent(apiKey)}`;

    const res = await fetch(geminiUrl, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(payload),
      signal: AbortSignal.timeout(25000),
    });

    const data = await res.json();
    if (!res.ok) {
      const errMsg = data.error?.message || `Gemini API error (status ${res.status})`;
      return json({ error: errMsg }, 502);
    }

    const reply =
      data.candidates?.[0]?.content?.parts?.[0]?.text ||
      "I'm sorry, I couldn't generate a response at this moment. Please try again.";

    return json({ reply, model });
  } catch (err) {
    return json({ error: "Failed to communicate with Gemini API", detail: `${err}` }, 500);
  }
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
      const bypassAuth = authDisabled(env);
      const session = bypassAuth
        ? DEV_SESSION
        : PRE_AUTH_PATHS.has(path)
        ? null
        : await verifySession(request, env);
      if (!bypassAuth && !PRE_AUTH_PATHS.has(path) && !session) {
        if (path.startsWith("/api/")) return json({ error: "Unauthorized" }, 401);
        const next = encodeURIComponent(path + url.search);
        return Response.redirect(`${url.origin}/login?next=${next}`, 302);
      }

      if (path === "/api/v1/auth/me" && method === "GET") return handleAuthMe(session);
      if (path === "/api/v1/chat" && method === "POST") return handleChat(request, env);

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
