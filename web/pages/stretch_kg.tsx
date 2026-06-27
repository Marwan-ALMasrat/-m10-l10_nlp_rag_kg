import { useState } from "react";
import { useRouter } from "next/router";
import { KGResponse } from "../lib/types";
import { API_URL, authFetch } from "../lib/api";

export default function KgPage() {
    const router = useRouter();
    const [question, setQuestion] = useState("");
    const [result, setResult] = useState<KGResponse | null>(null);
    const [error, setError] = useState<string | null>(null);
    const [supportedPatterns, setSupportedPatterns] = useState<string[] | null>(null);
    const [loading, setLoading] = useState(false);

    async function submit() {
        setError(null);
        setResult(null);
        setSupportedPatterns(null);
        setLoading(true);
        try {
            const res = await authFetch(`${API_URL}/kg/query`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ question }),
            });

            if (res.status === 401) {
                router.push("/login");
                return;
            }
            if (res.status === 403) {
                setError("Insufficient scope — you do not have access to this resource.");
                return;
            }
            if (res.status === 422) {
                const body = await res.json();
                if (body.detail?.reason === "unsupported_question") {
                    setError("Unsupported question. Try one of the patterns below:");
                    setSupportedPatterns(body.detail.supported_patterns ?? []);
                } else {
                    setError(`Validation error: ${JSON.stringify(body.detail)}`);
                }
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

            const data: KGResponse = await res.json();
            setResult(data);
        } catch {
            setError("Could not reach the backend.");
        } finally {
            setLoading(false);
        }
    }

    const columns =
        result && result.rows.length > 0 ? Object.keys(result.rows[0]) : [];

    return (
        <main>
            <h1>Knowledge Graph — Recipe Query</h1>
            <input
                value={question}
                onChange={(e) => setQuestion(e.target.value)}
                placeholder="e.g. Find Sichuan recipes"
                onKeyDown={(e) => e.key === "Enter" && question && submit()}
            />
            <button onClick={submit} disabled={!question || loading}>
                {loading ? "Querying…" : "Ask"}
            </button>

            {error && <p style={{ color: "red" }}>{error}</p>}

            {supportedPatterns && (
                <ul>
                    {supportedPatterns.map((p) => (
                        <li key={p}>{p}</li>
                    ))}
                </ul>
            )}

            {result && (
                <div style={{ marginTop: "1rem" }}>
                    <h2>Cypher</h2>
                    <pre style={{ background: "#f4f4f4", padding: "0.75rem", overflowX: "auto" }}>
                        {result.cypher}
                    </pre>
                    <h2>Results ({result.count} row{result.count !== 1 ? "s" : ""})</h2>
                    {result.rows.length === 0 ? (
                        <p>No rows returned.</p>
                    ) : (
                        <table>
                            <thead>
                                <tr>
                                    {columns.map((col) => (
                                        <th key={col}>{col}</th>
                                    ))}
                                </tr>
                            </thead>
                            <tbody>
                                {result.rows.map((row, i) => (
                                    <tr key={i} data-testid="kg-row">
                                        {columns.map((col) => (
                                            <td key={col}>{String(row[col] ?? "")}</td>
                                        ))}
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    )}
                </div>
            )}
        </main>
    );
}