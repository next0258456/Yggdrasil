"""Minimal Vietnamese Voice (STT/TTS) and lightweight CPU document/PDF extractor."""

from __future__ import annotations

import io
import uuid
from pathlib import Path
from typing import Any

import edge_tts
import httpx
from pypdf import PdfReader


async def synthesize_tts(text: str, voice: str, out_dir: Path) -> Path:
    """Synthesize Vietnamese speech MP3 using edge-tts without GPU overhead."""
    clean_text = text.strip()
    if not clean_text:
        raise ValueError("TTS text must not be empty.")
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"y7l_voice_{uuid.uuid4().hex[:12]}.mp3"
    communicator = edge_tts.Communicate(clean_text, voice)
    await communicator.save(str(out_path))
    return out_path


async def transcribe_stt(
    audio_bytes: bytes,
    filename: str,
    llm_api_base: str,
    llm_api_key: str,
    model: str = "whisper-1",
) -> str:
    """Proxy audio transcription to OpenAI-compatible /audio/transcriptions (via LiteLLM)."""
    if not audio_bytes:
        raise ValueError("Audio payload must not be empty.")
    endpoint = f"{llm_api_base.rstrip('/')}/audio/transcriptions"
    headers = {"Authorization": f"Bearer {llm_api_key}"}
    files = {"file": (filename or "voice.ogg", audio_bytes, "application/octet-stream")}
    data = {"model": model, "language": "vi"}
    async with httpx.AsyncClient(timeout=60.0) as client:
        resp = await client.post(endpoint, headers=headers, files=files, data=data)
        resp.raise_for_status()
        body = resp.json()
    return str(body.get("text", "")).strip()


def _chunk_text(text: str, max_chars: int = 900, overlap: int = 100) -> list[str]:
    clean = "\n".join(line.rstrip() for line in text.splitlines()).strip()
    if not clean:
        return []
    if len(clean) <= max_chars:
        return [clean]

    chunks: list[str] = []
    start = 0
    step = max(1, max_chars - overlap)
    while start < len(clean):
        end = min(len(clean), start + max_chars)
        piece = clean[start:end].strip()
        if piece:
            chunks.append(piece)
        if end >= len(clean):
            break
        start += step
    return chunks


def extract_document_text(
    file_bytes: bytes,
    filename: str,
    max_chars: int = 900,
    overlap: int = 100,
) -> dict[str, Any]:
    """Extract UTF-8 text from .md/.txt or .pdf and split into chunks for WF-03 SOP ingest."""
    suffix = Path(filename).suffix.lower()
    if suffix in {".md", ".txt", ".csv", ".log"}:
        text = file_bytes.decode("utf-8", errors="replace")
        source_type = "text"
    elif suffix == ".pdf":
        reader = PdfReader(io.BytesIO(file_bytes))
        pages = [page.extract_text() or "" for page in reader.pages]
        text = "\n\n".join(p.strip() for p in pages if p.strip())
        source_type = "pdf"
    else:
        raise ValueError(
            f"Unsupported file extension '{suffix}'. Supported: .md, .txt, .csv, .pdf (use vision LLM via LiteLLM for raw scanned images)."
        )

    chunks = _chunk_text(text, max_chars=max_chars, overlap=overlap)
    return {
        "filename": Path(filename).name,
        "source_type": source_type,
        "char_count": len(text),
        "chunk_count": len(chunks),
        "text": text,
        "chunks": [
            {"chunk_index": idx, "content": chunk}
            for idx, chunk in enumerate(chunks)
        ],
    }
