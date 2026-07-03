from __future__ import annotations

import logging
import time

import structlog
from sentence_transformers import SentenceTransformer

from rag.config import EMBEDDING_DIMENSION, EMBEDDING_MODEL_NAME

logging.basicConfig(format="%(message)s", level=logging.INFO)
structlog.configure(
    processors=[
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.processors.add_log_level,
        structlog.processors.JSONRenderer(),
    ],
    wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
    cache_logger_on_first_use=True,
)
logger = structlog.get_logger()


def load_embedding_model() -> SentenceTransformer:
    started_at = time.perf_counter()
    try:
        model = SentenceTransformer(EMBEDDING_MODEL_NAME)
        dimension = model.get_sentence_embedding_dimension()
    except Exception:
        logger.exception("embedding_model_load_failed", model_name=EMBEDDING_MODEL_NAME)
        raise

    if dimension != EMBEDDING_DIMENSION:
        elapsed_ms = round((time.perf_counter() - started_at) * 1000, 2)
        logger.error(
            "embedding_dimension_mismatch",
            model_name=EMBEDDING_MODEL_NAME,
            expected_dimension=EMBEDDING_DIMENSION,
            actual_dimension=dimension,
            duration_ms=elapsed_ms,
        )
        raise ValueError(
            f"{EMBEDDING_MODEL_NAME} produced {dimension} dimensions; "
            f"expected {EMBEDDING_DIMENSION}."
        )

    elapsed_ms = round((time.perf_counter() - started_at) * 1000, 2)
    logger.info(
        "embedding_model_loaded",
        model_name=EMBEDDING_MODEL_NAME,
        dimension=dimension,
        duration_ms=elapsed_ms,
    )
    return model


model = load_embedding_model()


def _coerce_vector(raw_vector: object) -> list[float]:
    vector = [float(value) for value in raw_vector]
    if len(vector) != EMBEDDING_DIMENSION:
        logger.error(
            "embedding_dimension_mismatch",
            model_name=EMBEDDING_MODEL_NAME,
            expected_dimension=EMBEDDING_DIMENSION,
            actual_dimension=len(vector),
        )
        raise ValueError(
            f"Embedding produced {len(vector)} dimensions; expected {EMBEDDING_DIMENSION}."
        )
    return vector


def embed_text(text: str) -> list[float]:
    if not text.strip():
        raise ValueError("Cannot embed empty text.")

    started_at = time.perf_counter()
    try:
        raw_vector = model.encode(text, normalize_embeddings=True)
        vector = _coerce_vector(raw_vector)
    except Exception:
        logger.exception(
            "text_embedding_failed",
            model_name=EMBEDDING_MODEL_NAME,
            input_chars=len(text),
        )
        raise

    elapsed_ms = round((time.perf_counter() - started_at) * 1000, 2)
    logger.info(
        "text_embedded",
        model_name=EMBEDDING_MODEL_NAME,
        input_chars=len(text),
        dimension=len(vector),
        duration_ms=elapsed_ms,
    )
    return vector


def embed_batch(texts: list[str]) -> list[list[float]]:
    if any(not text.strip() for text in texts):
        raise ValueError("Cannot embed empty text inside a batch.")

    if not texts:
        logger.info("batch_embedded", batch_size=0, dimension=EMBEDDING_DIMENSION, duration_ms=0)
        return []

    started_at = time.perf_counter()
    try:
        raw_vectors = model.encode(texts, normalize_embeddings=True)
        vectors = [_coerce_vector(raw_vector) for raw_vector in raw_vectors]
    except Exception:
        logger.exception(
            "batch_embedding_failed",
            model_name=EMBEDDING_MODEL_NAME,
            batch_size=len(texts),
        )
        raise

    elapsed_ms = round((time.perf_counter() - started_at) * 1000, 2)
    logger.info(
        "batch_embedded",
        model_name=EMBEDDING_MODEL_NAME,
        batch_size=len(texts),
        dimension=EMBEDDING_DIMENSION,
        duration_ms=elapsed_ms,
        duration_per_text_ms=round(elapsed_ms / len(texts), 2),
    )
    return vectors
