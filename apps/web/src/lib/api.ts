export const API_URL =
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000/api/v1";

export async function apiRequest<T>(
  path: string,
  init?: RequestInit,
): Promise<T> {
  const response = await fetch(`${API_URL}${path}`, init);
  const data = (await response.json()) as T & { detail?: string };
  if (!response.ok) {
    throw new Error(data.detail ?? "Request failed");
  }
  return data;
}

export function managerHeaders(): HeadersInit {
  const token =
    typeof window === "undefined"
      ? null
      : localStorage.getItem("bfa_manager_token");
  return token ? { Authorization: `Bearer ${token}` } : {};
}
