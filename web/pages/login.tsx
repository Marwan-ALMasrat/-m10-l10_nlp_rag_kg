import { useState } from "react";
import { useRouter } from "next/router";
import { API_URL } from "../lib/api";

export default function LoginPage() {
    const router = useRouter();
    const [username, setUsername] = useState("");
    const [password, setPassword] = useState("");
    const [error, setError] = useState<string | null>(null);
    const [loading, setLoading] = useState(false);

    async function handleSubmit() {
        setError(null);
        setLoading(true);
        try {
            const res = await fetch(`${API_URL}/auth/login`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ username, password }),
            });

            if (res.status === 401) {
                setError("Invalid username or password.");
                return;
            }
            if (res.status === 503) {
                setError("The backend is starting up — please try again in a moment.");
                return;
            }
            if (!res.ok) {
                setError(`Unexpected error: ${res.status}`);
                return;
            }

            const data = await res.json();
            // Store token in localStorage — runs only in the browser (inside handler)
            localStorage.setItem("access_token", data.access_token);
            router.push("/extract");
        } catch {
            setError("Could not reach the backend.");
        } finally {
            setLoading(false);
        }
    }

    return (
        <main>
            <h1>Login</h1>
            <input
                type="text"
                placeholder="Username"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
            />
            <input
                type="password"
                placeholder="Password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && username && password && handleSubmit()}
            />
            <button onClick={handleSubmit} disabled={!username || !password || loading}>
                {loading ? "Logging in…" : "Login"}
            </button>

            {error && <p style={{ color: "red" }}>{error}</p>}

            <p style={{ marginTop: "1rem", color: "#666", fontSize: "0.9rem" }}>
                Dev credentials: <strong>admin</strong> / <strong>secret</strong>
            </p>
        </main>
    );
}