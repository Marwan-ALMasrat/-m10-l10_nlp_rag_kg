/**
 * Auth-aware fetch wrapper.
 *
 * Reads the JWT from localStorage (browser only) and attaches it as a
 * Bearer token on every request. Falls back gracefully on the server
 * (SSR) where localStorage is not available.
 */

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export { API_URL };

export async function authFetch(
    url: string,
    init: RequestInit = {}
): Promise<Response> {
    const token =
        typeof window !== "undefined" ? localStorage.getItem("access_token") : null;
    const headers = new Headers(init.headers);
    if (token) {
        headers.set("Authorization", `Bearer ${token}`);
    }
    return fetch(url, { ...init, headers });
}