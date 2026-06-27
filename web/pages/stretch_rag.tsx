import { useState } from "react";
import { useRouter } from "next/router";
import { RAGResponse } from "../lib/types";
import { API_URL, authFetch } from "../lib/api";

export default function RagPage() {
    const router = useRouter();
    const [question, setQuestion] = useState("");
    const [result, setResult] = useState<RAGResponse | null>(null);
    const [error, setError] = useState<string | null>(null);
    const [loading, setLoading] = useState(false);

    async function submit() {
        setError(null);
        setResult(null);
        setLoading(true);
        try {
            const res = await authFetch(`${API_URL}/rag/answer`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ question, k: 4 }),
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
                setError(`Validation error: ${JSON.stringify(body.detail)}`);
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

            const data: RAGResponse = await res.json();
            setResult(data);
        } catch {
            setError("Could not reach the backend.");
        } finally {
            setLoading(false);
        }
    }

    return (
        <main>
            <h1>RAG — Cited Answer</h1>
            <input
                value={question}
                onChange={(e) => setQuestion(e.target.value)}
                placeholder="Ask a recipe question…"
                onKeyDown={(e) => e.key === "Enter" && question && submit()}
            />
            <button onClick={submit} disabled={!question || loading}>
                {loading ? "Thinking…" : "Ask"}
            </button>

            {error && <p style={{ color: "red" }}>{error}</p>}

            {result && (
                <div style={{ marginTop: "1rem" }}>
                    <h2>Answer</h2>
                    <p>{renderCitedAnswer(result.answer)}</p>

                    {result.citations.length > 0 && (
                        <>
                            <h2>
                                Citations (confidence: {(result.confidence * 100).toFixed(1)}%)
                            </h2>
                            <ul>
                                {result.citations.map((c) => (
                                    <li key={c.chunk_id}>
                                        Chunk #{c.chunk_id} — score: {c.score.toFixed(3)}
                                    </li>
                                ))}
                            </ul>
                        </>
                    )}
                </div>
            )}
        </main>
    );
}

function renderCitedAnswer(answer: string): React.ReactNode[] {
    const parts = answer.split(/(\[\d+\])/g);
    return parts.map((part, i) => {
        if (/^\[\d+\]$/.test(part)) {
            return (
                <span
                    key={i}
                    data-testid="citation-marker"
                    style={{
                        background: "#ddf",
                        borderRadius: "3px",
                        padding: "0 0.2rem",
                        fontWeight: "bold",
                    }}
                >
                    {part}
                </span>
            );
        }
        return part;
    });
}