"""RAG composer — retrieve → assemble → generate → cite → grounding check.

Per the Evaluation Methodology Rule, the grounding criterion is:
`len(citations) > 0` is required when `answer` is not the empty-
retrieval sentinel. Every cited `chunk_id` must correspond to a
chunk in the top-`k` retrieved from Weaviate.

The generator call uses `do_sample=False` so retrieval and metric
reproducibility hold across runs.
"""
import re
from typing import Tuple

PROMPT_TEMPLATE = """\
You are answering a recipe question. Use ONLY the numbered sources below.
Cite each claim with the source number in square brackets, e.g. [1].
If the sources do not contain the answer, say: I cannot answer this from the available sources.

Sources:
{sources}

Question: {question}
Answer:"""

SENTINEL = "I cannot answer this from the available sources"
CITATION_PATTERN = re.compile(r"\[(\d+)\]")


def assemble_prompt(question: str, chunks: list[dict]) -> Tuple[str, dict[int, dict]]:
    """Number the retrieved chunks 1..k and substitute into the prompt template.

    Returns (prompt_str, {citation_index: chunk_dict}).
    """
    numbered: dict[int, dict] = {}
    source_lines = []
    for i, chunk in enumerate(chunks, start=1):
        numbered[i] = chunk
        source_lines.append(f"[{i}] {chunk['text']}")
    sources = "\n".join(source_lines)
    prompt = PROMPT_TEMPLATE.format(sources=sources, question=question)
    return prompt, numbered


def extract_citations(answer: str, numbered: dict[int, dict]) -> list[dict]:
    """Pull [N]-style markers from `answer` and resolve to retrieved chunks.

    Each return value is shaped {"chunk_id": int, "score": float}. Only
    indices that are present in `numbered` are returned; duplicates are
    de-duplicated.
    """
    seen: set[int] = set()
    citations: list[dict] = []
    for m in CITATION_PATTERN.finditer(answer):
        idx = int(m.group(1))
        if idx in numbered and idx not in seen:
            seen.add(idx)
            chunk = numbered[idx]
            distance = chunk.get("_additional", {}).get("distance", 0.0)
            score = max(0.0, min(1.0, 1.0 - distance))
            citations.append({"chunk_id": chunk["chunk_id"], "score": score})
    return citations


def compose_rag(question: str, embedder, weaviate_client, generator, k: int = 4) -> dict:
    """Run the four-stage RAG pipeline.

    Returns a dict {"answer": str, "citations": list[dict], "confidence": float}.

    Grounding contract:
    - If Weaviate returns zero chunks → return SENTINEL with citations=[]
      and confidence=0.0.
    - If the generator returns text with no resolvable citation
      markers → also return SENTINEL with citations=[] and
      confidence=0.0. (This is the "refuse rather than hallucinate"
      rule the autograder enforces.)
    """
    # 1. Encode question and retrieve top-k chunks from Weaviate
    vector = embedder.encode(question).tolist()
    result = (
        weaviate_client.query
        .get("Chunk", ["text", "chunk_id"])
        .with_near_vector({"vector": vector})
        .with_additional(["distance"])
        .with_limit(k)
        .do()
    )
    retrieved = result.get("data", {}).get("Get", {}).get("Chunk", [])

    # 2. Grounding refusal: no chunks retrieved
    if not retrieved:
        return {"answer": SENTINEL, "citations": [], "confidence": 0.0}

    # Flatten _additional into each chunk dict for easier access
    chunks: list[dict] = []
    for obj in retrieved:
        chunk = {
            "chunk_id": obj["chunk_id"],
            "text": obj["text"],
            "_additional": obj.get("_additional", {}),
        }
        chunks.append(chunk)

    # 3. Assemble prompt
    prompt, numbered = assemble_prompt(question, chunks)

    # 4. Generate with flan-t5-base, deterministic
    gen_result = generator(prompt, max_new_tokens=256, do_sample=False)
    raw: str = gen_result[0]["generated_text"]

    # 5. Extract citations
    citations = extract_citations(raw, numbered)

    # 6. Grounding refusal: no valid citation markers
    if not citations:
        return {"answer": SENTINEL, "citations": [], "confidence": 0.0}

    # 7. Confidence = mean of citation scores, clipped to [0, 1]
    confidence = sum(c["score"] for c in citations) / len(citations)
    confidence = max(0.0, min(1.0, confidence))

    # 8. Return grounded response
    return {"answer": raw, "citations": citations, "confidence": confidence}