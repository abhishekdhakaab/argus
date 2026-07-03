from __future__ import annotations

import re
import time

import structlog

logger = structlog.get_logger()

MIN_CHUNK_WORDS = 20
SENTENCE_BOUNDARY = re.compile(r"(?<=[.!?])\s+|\n+")

# A conservative word limit stays below the embedder's 512-token window without
# loading its tokenizer during ingestion.


def split_sentences(text: str) -> list[str]:
    normalized = re.sub(r"\s+", " ", text.strip())
    if not normalized:
        return []
    return [sentence.strip() for sentence in SENTENCE_BOUNDARY.split(normalized) if sentence.strip()]


def chunk_text(text: str, chunk_size: int = 380, overlap: int = 50) -> list[str]:
    if chunk_size <= 0:
        raise ValueError("chunk_size must be positive.")
    if overlap < 0:
        raise ValueError("overlap must be zero or positive.")
    if overlap >= chunk_size:
        raise ValueError("overlap must be smaller than chunk_size.")

    started_at = time.perf_counter()
    sentences = split_sentences(text)
    chunks: list[str] = []
    current_words: list[str] = []

    def finish_current_chunk() -> None:
        if len(current_words) < MIN_CHUNK_WORDS:
            return
        chunks.append(" ".join(current_words))

    for sentence in sentences:
        sentence_words = sentence.split()
        if not sentence_words:
            continue

        if len(sentence_words) > chunk_size:
            finish_current_chunk()
            current_words = []
            for start in range(0, len(sentence_words), chunk_size - overlap):
                window = sentence_words[start : start + chunk_size]
                if len(window) >= MIN_CHUNK_WORDS:
                    chunks.append(" ".join(window))
            continue

        would_overflow = current_words and len(current_words) + len(sentence_words) > chunk_size
        if would_overflow:
            finish_current_chunk()
            current_words = current_words[-overlap:] if overlap else []

        current_words.extend(sentence_words)

    finish_current_chunk()

    elapsed_ms = round((time.perf_counter() - started_at) * 1000, 2)
    logger.info(
        "chunk_text_complete",
        input_chars=len(text),
        input_words=len(text.split()),
        sentence_count=len(sentences),
        chunk_count=len(chunks),
        chunk_size=chunk_size,
        overlap=overlap,
        duration_ms=elapsed_ms,
    )
    return chunks
