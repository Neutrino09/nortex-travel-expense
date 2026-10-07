"""python -m app.ingest.build_cache  — extract the whole sample pack with the real model (CLAUDE.md §9).

Run once from backend/ with OPENAI_API_KEY and OPENAI_MODEL set; commit the resulting fixtures.
Overwrites existing (e.g. handwritten) fixtures. Pass --missing to only fill gaps. Never prints the key.
"""
import sys

from ..config import get_settings
from . import extract as ex
from .eml import IMAGE_EXTS, parse_eml


def pack_documents() -> list[tuple[str, bytes, str | None, bytes | None, str]]:
    """(filename, raw bytes, text for the model, image bytes, mime) for every document in the pack."""
    pack = get_settings().pack_dir
    docs, seen = [], set()
    for p in sorted((pack / "sample_emails").glob("*.eml")):
        raw = p.read_bytes()
        parsed = parse_eml(raw)
        docs.append((p.name, raw, parsed.as_text(), None, "text/plain"))
        for a in parsed.attachments:
            if ex.sha256_of(a.content) not in seen:
                seen.add(ex.sha256_of(a.content))
                docs.append((a.filename, a.content, None, a.content, a.mime))
    for p in sorted((pack / "receipts").iterdir()):
        if p.suffix.lower() in IMAGE_EXTS and ex.sha256_of(p.read_bytes()) not in seen:
            raw = p.read_bytes()
            docs.append((p.name, raw, None, raw, IMAGE_EXTS[p.suffix.lower()]))
    return docs


def main() -> int:
    only_missing = "--missing" in sys.argv
    if not ex.llm_available():
        print("Set OPENAI_API_KEY and OPENAI_MODEL first (in the environment or .env).")
        return 1
    for name, raw, text, image, mime in pack_documents():
        sha = ex.sha256_of(raw)
        if only_missing and ex.cache_path(sha).is_file():
            print(f"skip   {name}")
            continue
        result = ex.call_llm(text, image, mime)  # let errors surface: the user must see them
        ex.save_cached(sha, result, name)
        print(f"cached {name} -> {sha[:12]}.json ({result.doc_type})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
