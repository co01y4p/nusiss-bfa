export const API_URL =
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000/api/v1";

export async function apiRequest<T>(
  path: string,
  init?: RequestInit,
): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${API_URL}${path}`, init);
  } catch (caught) {
    throw new Error(
      caught instanceof Error
        ? `Connection error: ${caught.message}`
        : "Failed to connect to backend server",
    );
  }

  const contentType = response.headers.get("content-type") || "";
  let data: unknown = null;
  if (contentType.includes("application/json")) {
    try {
      data = await response.json();
    } catch {
      data = null;
    }
  } else {
    try {
      data = await response.text();
    } catch {
      data = null;
    }
  }

  if (!response.ok) {
    let errorMessage = `Request failed (${response.status} ${response.statusText})`;
    if (data && typeof data === "object") {
      const rec = data as Record<string, unknown>;
      if (typeof rec.detail === "string") {
        errorMessage = rec.detail;
      } else if (Array.isArray(rec.detail)) {
        errorMessage = rec.detail
          .map((item) =>
            typeof item === "object" && item !== null && "msg" in item
              ? String((item as { msg: unknown }).msg)
              : JSON.stringify(item),
          )
          .join("; ");
      } else if (typeof rec.message === "string") {
        errorMessage = rec.message;
      }
    } else if (typeof data === "string" && data.trim()) {
      errorMessage = data.slice(0, 300);
    }
    throw new Error(errorMessage);
  }

  return data as T;
}

export function managerHeaders(): HeadersInit {
  const token =
    typeof window === "undefined"
      ? null
      : localStorage.getItem("bfa_manager_token");
  return token ? { Authorization: `Bearer ${token}` } : {};
}
