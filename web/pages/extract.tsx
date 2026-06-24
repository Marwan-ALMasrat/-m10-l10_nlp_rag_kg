import { useState } from "react";
import { ExtractResponse } from "../lib/types";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export default function ExtractPage() {
  const [text, setText] = useState("");
  const [result, setResult] = useState<ExtractResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function submit() {
    setError(null);
    setResult(null);
    setLoading(true);
    try {
      const res = await fetch(`${API_URL}/extract`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text }),
      });

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

      const data: ExtractResponse = await res.json();
      setResult(data);
    } catch {
      setError("Could not reach the backend.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <main>
      <h1>Extract — Named Entity Recognition</h1>
      <textarea
        value={text}
        onChange={(e) => setText(e.target.value)}
        rows={5}
        placeholder="Paste text here (max 5000 characters)…"
      />
      <button onClick={submit} disabled={!text || loading}>
        {loading ? "Extracting…" : "Extract"}
      </button>

      {error && <p style={{ color: "red" }}>{error}</p>}

      {result && result.entities.length === 0 && (
        <p>No entities found.</p>
      )}

      {result && result.entities.length > 0 && (
        <div style={{ marginTop: "1rem" }}>
          <h2>Entities</h2>
          <p>
            {/* Render highlighted spans inline */}
            {renderHighlighted(text, result.entities)}
          </p>
          <table>
            <thead>
              <tr>
                <th>Text</th>
                <th>Label</th>
                <th>Start</th>
                <th>End</th>
              </tr>
            </thead>
            <tbody>
              {result.entities.map((ent, i) => (
                <tr key={i}>
                  <td>
                    <span
                      className="entity-span"
                      data-testid="entity-span"
                    >
                      {ent.text}
                    </span>
                  </td>
                  <td>{ent.label}</td>
                  <td>{ent.start}</td>
                  <td>{ent.end}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </main>
  );
}

/** Render the original text with entity spans highlighted inline. */
function renderHighlighted(
  text: string,
  entities: ExtractResponse["entities"]
) {
  const parts: React.ReactNode[] = [];
  let cursor = 0;
  for (const ent of entities) {
    if (ent.start > cursor) {
      parts.push(text.slice(cursor, ent.start));
    }
    parts.push(
      <mark
        key={`${ent.start}-${ent.end}`}
        className="entity-span"
        data-testid="entity-span"
        title={ent.label}
      >
        {ent.text}
      </mark>
    );
    cursor = ent.end;
  }
  if (cursor < text.length) {
    parts.push(text.slice(cursor));
  }
  return parts;
}