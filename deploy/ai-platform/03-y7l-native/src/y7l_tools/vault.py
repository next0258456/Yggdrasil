"""Zero-Chunking Obsidian Vault loader, [[Wikilinks]] graph walker, and vault linter."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path

import yaml

_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n?", re.DOTALL)
_WIKILINK_RE = re.compile(r"\[\[([^\[\]|]+)(?:\|[^\[\]]+)?\]\]")
_DATA_TRAP_RE = re.compile(r"DATA_TRAP:\s*([^\n]+)")


def _normalize_text(value: str) -> str:
    """Fold Vietnamese accents and lowercase for robust keyword matching."""
    nfkd = unicodedata.normalize("NFKD", value.replace("đ", "d").replace("Đ", "D"))
    ascii_only = "".join(ch for ch in nfkd if not unicodedata.combining(ch))
    return ascii_only.lower()


@dataclass(slots=True)
class VaultNote:
    """Represents one whole atomic Obsidian Markdown note (never chunked)."""

    entity: str
    note_type: str
    path: Path
    relative_path: str
    content: str
    byte_size: int
    frontmatter: dict
    wikilinks: list[str] = field(default_factory=list)
    data_traps: list[str] = field(default_factory=list)


def parse_note(path: Path, vault_root: Path) -> VaultNote:
    """Parse an Obsidian Markdown note with YAML frontmatter, [[Wikilinks]], and DATA_TRAP rules."""
    content = path.read_text(encoding="utf-8")
    byte_size = len(content.encode("utf-8"))

    frontmatter: dict = {}
    fm_match = _FRONTMATTER_RE.match(content)
    if fm_match:
        loaded = yaml.safe_load(fm_match.group(1))
        if isinstance(loaded, dict):
            frontmatter = loaded

    entity = str(frontmatter.get("entity") or path.stem)
    note_type = str(frontmatter.get("type") or path.parent.name)

    links = list(dict.fromkeys(link.strip() for link in _WIKILINK_RE.findall(content)))
    traps = list(dict.fromkeys(trap.strip() for trap in _DATA_TRAP_RE.findall(content)))

    return VaultNote(
        entity=entity,
        note_type=note_type,
        path=path,
        relative_path=path.relative_to(vault_root).as_posix(),
        content=content,
        byte_size=byte_size,
        frontmatter=frontmatter,
        wikilinks=links,
        data_traps=traps,
    )


def load_vault(vault_root: Path) -> dict[str, VaultNote]:
    """Load all Markdown notes in the Obsidian Vault keyed by lowercase entity name."""
    if not vault_root.exists():
        return {}
    notes: dict[str, VaultNote] = {}
    for md_file in sorted(vault_root.rglob("*.md")):
        note = parse_note(md_file, vault_root)
        notes[note.entity.lower()] = note
    return notes


def list_entities(vault_root: Path) -> list[dict]:
    """Return summary metadata for every note in the Obsidian Vault."""
    notes = load_vault(vault_root)
    return [
        {
            "entity": note.entity,
            "type": note.note_type,
            "path": note.relative_path,
            "byte_size": note.byte_size,
            "wikilinks": note.wikilinks,
            "data_traps": note.data_traps,
        }
        for note in notes.values()
    ]


def _score_note(note: VaultNote, normalized_tokens: list[str], raw_query_lower: str) -> int:
    score = 0
    entity_norm = _normalize_text(note.entity)
    content_norm = _normalize_text(note.content)

    if note.entity.lower() in raw_query_lower or entity_norm.replace("_", " ") in _normalize_text(raw_query_lower):
        score += 10

    for tok in normalized_tokens:
        if len(tok) < 2:
            continue
        if tok in entity_norm:
            score += 4
        elif tok in content_norm:
            score += 1

    # Prefer structured SQL notes (glossary + table) over general SOP notes for SQL context.
    if score > 0 and note.note_type in {"table", "glossary"}:
        score += 3
    return score


def read_context(
    vault_root: Path,
    query: str = "",
    entities: list[str] | None = None,
    max_depth: int = 1,
    max_bytes: int = 12000,
) -> dict:
    """
    Read whole Obsidian Markdown files (Zero-Chunking) and traverse [[Wikilinks]] up to max_depth.
    """
    notes = load_vault(vault_root)
    if not notes:
        return {
            "zero_chunking": True,
            "entities": [],
            "files": [],
            "total_bytes": 0,
            "data_traps": [],
            "context_markdown": "",
        }

    seeds: list[str] = []
    if entities:
        for ent in entities:
            key = ent.strip().lower()
            if key in notes:
                seeds.append(key)

    if not seeds and query:
        norm_q = _normalize_text(query)
        tokens = re.findall(r"[a-z0-9_]+", norm_q)
        scored = [
            (key, _score_note(note, tokens, query.lower()))
            for key, note in notes.items()
            if note.note_type in {"table", "glossary"}
        ]
        scored.sort(key=lambda item: item[1], reverse=True)
        seeds = [key for key, score in scored if score > 0][:2]

    if not seeds:
        # Default fallback for general analytical prompts: include glossary + tables.
        seeds = [k for k, n in notes.items() if n.note_type in {"table", "glossary"}][:3]

    selected_keys: list[str] = []
    visited: set[str] = set()
    frontier: list[tuple[str, int]] = [(seed, 0) for seed in seeds]
    total_bytes = 0

    while frontier:
        key, depth = frontier.pop(0)
        if key in visited or key not in notes:
            continue
        note = notes[key]
        if selected_keys and total_bytes + note.byte_size > max_bytes:
            continue
        visited.add(key)
        selected_keys.append(key)
        total_bytes += note.byte_size

        if depth < max_depth:
            for link in note.wikilinks:
                target_key = link.lower()
                if target_key not in visited and target_key in notes:
                    frontier.append((target_key, depth + 1))

    selected_notes = [notes[k] for k in selected_keys]
    all_traps = list(
        dict.fromkeys(trap for note in selected_notes for trap in note.data_traps)
    )
    combined_markdown = "\n\n---\n\n".join(note.content.strip() for note in selected_notes)

    return {
        "zero_chunking": True,
        "entities": [note.entity for note in selected_notes],
        "files": [
            {
                "entity": note.entity,
                "type": note.note_type,
                "path": note.relative_path,
                "byte_size": note.byte_size,
                "wikilinks": note.wikilinks,
                "data_traps": note.data_traps,
            }
            for note in selected_notes
        ],
        "total_bytes": total_bytes,
        "data_traps": all_traps,
        "context_markdown": combined_markdown,
    }


def lint_vault(vault_root: Path, max_file_bytes: int = 16384) -> dict:
    """Validate Obsidian Vault invariants: frontmatter, [[Wikilinks]], DATA_TRAPs, byte limits."""
    notes = load_vault(vault_root)
    errors: list[str] = []
    warnings: list[str] = []

    if not notes:
        errors.append(f"Vault directory is empty or missing: {vault_root}")
        return {"ok": False, "note_count": 0, "errors": errors, "warnings": warnings}

    known_entities = set(notes.keys())

    for key, note in notes.items():
        if not note.frontmatter:
            errors.append(f"[{note.relative_path}] Missing YAML frontmatter.")
        else:
            if "entity" not in note.frontmatter:
                errors.append(f"[{note.relative_path}] Frontmatter missing 'entity'.")
            if "type" not in note.frontmatter:
                errors.append(f"[{note.relative_path}] Frontmatter missing 'type'.")

        for link in note.wikilinks:
            if link.lower() not in known_entities:
                errors.append(f"[{note.relative_path}] Broken wikilink: [[{link}]]")

        if note.note_type == "table" and not note.data_traps:
            errors.append(
                f"[{note.relative_path}] Table note must declare at least one DATA_TRAP warning."
            )

        if note.byte_size > max_file_bytes:
            warnings.append(
                f"[{note.relative_path}] Size {note.byte_size} bytes exceeds recommended {max_file_bytes} bytes."
            )

    return {
        "ok": len(errors) == 0,
        "note_count": len(notes),
        "entities": [note.entity for note in notes.values()],
        "errors": errors,
        "warnings": warnings,
    }
