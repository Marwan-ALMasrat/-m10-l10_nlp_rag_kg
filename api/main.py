"""FastAPI application — recipe service.

This module wires the path operations, lifespan, and CORS middleware.

Discipline gates the autograder enforces:
- Neo4j driver, Weaviate client, spaCy pipeline, and the flan-t5-base
  generator are constructed exactly once per process inside `lifespan`.
- `CORSMiddleware` is registered with `allow_origins=[WEB_ORIGIN]`.
- `/extract`, `/kg/query`, `/rag/answer` use Pydantic shapes from
  `models.py` (no anonymous dicts; use Pydantic v2 idioms (model_dump, not the deprecated v1 serialization shortcut)).
- `/kg/query` converts `UnsupportedQueryError` to 422 with structured
  detail (`{"reason": "unsupported_question", "supported_patterns": [...]}`).
- `/readyz` probes Neo4j (`RETURN 1`) AND Weaviate (`client.is_ready()`)
  within 2 seconds; failure → 503.
- `/healthz` does NOT touch Neo4j or Weaviate.
"""
import os
from contextlib import asynccontextmanager

import spacy
import weaviate
from fastapi import Depends, FastAPI, HTTPException, Security
from .auth import api_key_header
from neo4j import GraphDatabase
from sentence_transformers import SentenceTransformer
from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel
from .auth import api_key_header, oauth2_scheme

from .auth import (
    authenticate_user,
    create_access_token,
    verify_api_key_or_jwt,
    verify_jwt,
)
from .deps import get_embedder, get_generator, get_nlp, get_session, get_weaviate
from .kg import wrap_kg_query
from .m8_rag import load_generator
from .models import (
    ExtractRequest,
    ExtractResponse,
    HealthResponse,
    KGRequest,
    KGResponse,
    RAGRequest,
    RAGResponse,
    ReadyDetail,
    UnsupportedQueryDetail,
)
from .nlp import extract_entities
from .rag import compose_rag
from .settings import Settings
from .w9b_mapper.errors import UnsupportedQueryError
from .w9b_mapper.shapes import SUPPORTED_PATTERNS


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Process-scoped resource setup and teardown."""
    settings = Settings()

    app.state.neo4j_driver = GraphDatabase.driver(
        settings.neo4j_uri,
        auth=(settings.neo4j_user, settings.neo4j_password),
    )
    app.state.weaviate_client = weaviate.Client(settings.weaviate_url)
    app.state.nlp = spacy.load("en_core_web_sm")
    app.state.generator = load_generator()
    app.state.embedder = SentenceTransformer(
        "sentence-transformers/all-MiniLM-L6-v2"
    )

    yield

    app.state.neo4j_driver.close()


app = FastAPI(title="M10 Recipe Service", lifespan=lifespan)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Auth models
# ---------------------------------------------------------------------------

class LoginRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


# ---------------------------------------------------------------------------
# Auth endpoints
# ---------------------------------------------------------------------------

@app.post("/auth/login", response_model=TokenResponse)
def login(req: LoginRequest):
    """Issue a JWT for valid credentials."""
    user = authenticate_user(req.username, req.password)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid username or password")
    token = create_access_token(subject=user["username"])
    return TokenResponse(access_token=token, token_type="bearer")


@app.get("/admin/echo")
def admin_echo(
    api_key: str = Security(api_key_header),
    token: str = Depends(oauth2_scheme),
):
    """JWT-only endpoint — returns the decoded token payload."""
    valid_key = os.environ.get("API_KEY_VALID", "")
    
    # API key present and valid but no JWT → 403 (valid credential, wrong scope)
    if api_key and api_key == valid_key:
        raise HTTPException(status_code=403, detail="Insufficient scope — JWT required")
    
    # No valid credential at all → 401
    if not token:
        raise HTTPException(status_code=401, detail="Missing credentials")
    
    # Verify JWT
    from .auth import verify_jwt as _verify_jwt
    return _verify_jwt(token)


# ---------------------------------------------------------------------------
# Lab endpoints — now require API-key OR JWT
# ---------------------------------------------------------------------------

@app.post("/extract", response_model=ExtractResponse)
def extract(
    req: ExtractRequest,
    nlp=Depends(get_nlp),
    _auth=Depends(verify_api_key_or_jwt),
):
    """Run spaCy NER on the input text; return entities ordered by `start`."""
    entities = extract_entities(req.text, nlp)
    return ExtractResponse(entities=entities)


@app.post("/kg/query", response_model=KGResponse)
def kg_query(
    req: KGRequest,
    session=Depends(get_session),
    _auth=Depends(verify_api_key_or_jwt),
):
    """Run the W9B mapper and execute the resulting Cypher."""
    try:
        cypher, params = wrap_kg_query(req.question)
    except UnsupportedQueryError:
        detail = UnsupportedQueryDetail(
            reason="unsupported_question",
            supported_patterns=list(SUPPORTED_PATTERNS),
        )
        raise HTTPException(status_code=422, detail=detail.model_dump())

    result = session.run(cypher, **params)
    rows = [record.data() for record in result]
    return KGResponse(cypher=cypher, rows=rows, count=len(rows))


@app.post("/rag/answer", response_model=RAGResponse)
def rag_answer(
    req: RAGRequest,
    weaviate_client=Depends(get_weaviate),
    generator=Depends(get_generator),
    embedder=Depends(get_embedder),
    _auth=Depends(verify_api_key_or_jwt),
):
    """Retrieve → assemble → generate → cite → grounding check."""
    result = compose_rag(
        question=req.question,
        embedder=embedder,
        weaviate_client=weaviate_client,
        generator=generator,
        k=req.k,
    )
    return RAGResponse(
        answer=result["answer"],
        citations=result["citations"],
        confidence=result["confidence"],
    )


# ---------------------------------------------------------------------------
# Health endpoints — no auth required
# ---------------------------------------------------------------------------

@app.get("/healthz", response_model=HealthResponse)
def healthz():
    """Liveness probe. Must NOT touch Neo4j or Weaviate."""
    return HealthResponse(status="ok")


@app.get("/readyz")
def readyz(session=Depends(get_session), weaviate_client=Depends(get_weaviate)):
    """Readiness probe."""
    neo4j_status = "ok"
    weaviate_status = "ok"

    try:
        session.run("RETURN 1 AS ok").single()
    except Exception:
        neo4j_status = "unavailable"

    try:
        if not weaviate_client.is_ready():
            weaviate_status = "unavailable"
    except Exception:
        weaviate_status = "unavailable"

    detail = ReadyDetail(neo4j=neo4j_status, weaviate=weaviate_status)

    if neo4j_status != "ok" or weaviate_status != "ok":
        raise HTTPException(status_code=503, detail=detail.model_dump())

    return detail