"""Domain services — pure business logic with no infrastructure dependencies."""

from __future__ import annotations

import re

from domain.value_objects import ConversionResult, PageDetail

# Regex to extract <body> content from Docling's well-formed HTML output.
_BODY_RE = re.compile(r"<body[^>]*>(.*)</body>", re.DOTALL | re.IGNORECASE)

# Canonical VLM JSON sections, used by both per-page merge
# (`infra/local_converter._merge_vlm_json_pages`) and cross-batch merge
# (`_merge_content_json` below). Order matters only for visual stability —
# matching is longest-prefix-first, so a key like `"Addressee"` would NOT be
# bucketed under `"Address"` because there is no such section here.
#
# Phone / Fax were removed — they showed up in a few early batches but
# turned out to be noisy duplicates of Address content; the user wants
# the trade-document sections only.
VLM_JSON_SECTIONS: tuple[str, ...] = (
    "Company Name",
    "Address",
    "Shipping Information",
    "Goods Description",
)


def extract_html_body(html: str) -> str:
    """Extract content between <body> tags.

    Docling produces well-formed HTML — regex is safe for this controlled output.
    Returns raw html as fallback if no <body> tag is found.
    """
    match = _BODY_RE.search(html)
    return match.group(1).strip() if match else html


# Docling self_ref prefixes for the per-batch renumbering. Matches the
# top-level lists in a DoclingDocument JSON payload.
_SELF_REF_LISTS: tuple[str, ...] = ("texts", "tables", "pictures", "groups", "key_value_items", "form_items")


def _renumber_batch_doc(doc: dict, offset_texts: int, offset_tables: int, offset_pictures: int, offset_groups: int) -> dict:
    """Renumber ``self_ref`` and ``$ref`` pointers in a single batch's document.

    Each batch's Docling document starts its ``texts``/``tables``/``pictures``/
    ``groups`` arrays at index 0, so a naive concat produces duplicate
    ``(self_ref)`` values across batches — which violates the Neo4j composite
    uniqueness constraint ``(doc_id, self_ref)`` and crashes the graph write
    (see infra/neo4j/schema.py). This function shifts each batch's indices by
    the running totals from prior batches, and rewrites all internal ``$ref``
    pointers (body.children, item.parent, item.children) to match.

    Args:
        doc: The batch's parsed DoclingDocument dict.
        offset_texts / offset_tables / offset_pictures / offset_groups:
            Running count of items already in the merged doc for each list.

    Returns:
        The same dict, mutated in place, with all refs renumbered.
    """
    offsets = {
        "texts": offset_texts,
        "tables": offset_tables,
        "pictures": offset_pictures,
        "groups": offset_groups,
    }

    def _shift_ref(ref: str) -> str:
        """Shift a ``#/list/N`` reference by the appropriate offset. Leaves
        ``#/body`` and any other non-list refs alone."""
        if not isinstance(ref, str) or not ref.startswith("#/"):
            return ref
        rest = ref[2:]
        parts = rest.split("/", 1)
        if len(parts) != 2 or parts[0] not in offsets:
            return ref
        try:
            idx = int(parts[1])
        except ValueError:
            return ref
        return f"#/{parts[0]}/{idx + offsets[parts[0]]}"

    def _shift_node(node, skip_keys: set[str] | None = None):
        """Recursively shift ``$ref`` / ``self_ref`` inside an item dict.

        ``skip_keys`` lets the caller exclude keys the outer loop already
        processed (e.g. the top-level item's own ``self_ref`` — shifting it
        again would compound the offset).
        """
        skip = skip_keys or set()
        if isinstance(node, dict):
            for k, v in list(node.items()):
                if k in skip:
                    continue
                if k in ("$ref", "self_ref") and isinstance(v, str):
                    node[k] = _shift_ref(v)
                else:
                    _shift_node(v, skip)
        elif isinstance(node, list):
            for v in node:
                _shift_node(v, skip)

    # Renumber self_ref on every top-level list item, then walk the same
    # items to shift any internal $ref pointers they carry (e.g. a Picture's
    # `children` that reference its caption Texts).
    #
    # We use a per-iteration "skip set" so the walk doesn't re-shift
    # ``self_ref``/``$ref`` keys we already processed — otherwise a
    # top-level Text item would get its self_ref shifted twice (once here,
    # once when the recursive walk encounters the same key).
    for list_name in _SELF_REF_LISTS:
        for item in doc.get(list_name) or []:
            if isinstance(item, dict):
                # Shift the item's own self_ref first.
                if "self_ref" in item and isinstance(item["self_ref"], str):
                    item["self_ref"] = _shift_ref(item["self_ref"])
                # Then walk the rest of the item, but skip keys the
                # recursive walk would otherwise re-shift (self_ref, $ref)
                # AND any key whose value we already handled explicitly.
                _shift_node(item, skip_keys={"self_ref"})

    # body.children is a list of {"$ref": "..."} pointers — shift each one.
    body = doc.get("body") or {}
    for child in body.get("children") or []:
        if isinstance(child, dict) and "$ref" in child and isinstance(child["$ref"], str):
            child["$ref"] = _shift_ref(child["$ref"])  # no skip needed — only key is $ref

    return doc


def _merge_document_json(results: list[ConversionResult]) -> str | None:
    """Merge document_json across batches by concatenating texts/body children.

    Each batch produces an independent DoclingDocument. We merge by appending
    their ``texts``, ``tables``, ``pictures``, ``groups`` lists and their
    ``body.children`` refs, producing a single flat document that covers all
    pages. To keep the merged doc's ``self_ref`` values globally unique (the
    Neo4j writer enforces a ``(doc_id, self_ref)`` composite uniqueness
    constraint — see ``infra/neo4j/schema.py``), each batch's indices are
    shifted by the running totals from prior batches. Structural nesting
    within a batch is preserved; cross-batch heading hierarchy is not, but
    that is acceptable for a batched conversion.
    """
    import json as _json

    merged_texts: list = []
    merged_tables: list = []
    merged_pictures: list = []
    merged_groups: list = []
    merged_body_children: list = []
    merged_pages: dict = {}
    first_doc: dict | None = None

    # Running counts so each batch's self_ref indices are globally unique
    # in the merged document.
    n_texts = n_tables = n_pictures = n_groups = 0

    for r in results:
        if not r.document_json:
            continue
        try:
            doc = _json.loads(r.document_json)
        except Exception:
            continue
        if first_doc is None:
            first_doc = doc

        # Renumber this batch's refs before appending, so the merged doc's
        # $ref pointers are consistent within each batch's contribution.
        # The first batch keeps its original indices (offset 0); later
        # batches are shifted by the running totals.
        if n_texts + n_tables + n_pictures + n_groups > 0:
            _renumber_batch_doc(
                doc,
                offset_texts=n_texts,
                offset_tables=n_tables,
                offset_pictures=n_pictures,
                offset_groups=n_groups,
            )

        texts = doc.get("texts") or []
        tables = doc.get("tables") or []
        pictures = doc.get("pictures") or []
        groups = doc.get("groups") or []

        merged_texts.extend(texts)
        merged_tables.extend(tables)
        merged_pictures.extend(pictures)
        merged_groups.extend(groups)
        merged_body_children.extend((doc.get("body") or {}).get("children") or [])
        merged_pages.update(doc.get("pages") or {})

        n_texts += len(texts)
        n_tables += len(tables)
        n_pictures += len(pictures)
        n_groups += len(groups)

    if first_doc is None:
        return None

    merged_doc = dict(first_doc)
    merged_doc["texts"] = merged_texts
    merged_doc["tables"] = merged_tables
    merged_doc["pictures"] = merged_pictures
    merged_doc["groups"] = merged_groups
    merged_doc["pages"] = merged_pages
    merged_doc["body"] = {
        "self_ref": "#/body",
        "children": merged_body_children,
        "content_layer": "body",
    }
    return _json.dumps(merged_doc)


def merge_results(results: list[ConversionResult]) -> ConversionResult:
    """Merge multiple batch ConversionResults into a single consolidated result."""
    if not results:
        return ConversionResult(page_count=0, content_markdown="", content_html="", pages=[])

    all_pages: list[PageDetail] = []
    all_md: list[str] = []
    html_bodies: list[str] = []
    total_skipped = 0

    for r in results:
        all_pages.extend(r.pages)
        all_md.append(r.content_markdown)
        html_bodies.append(extract_html_body(r.content_html))
        total_skipped += r.skipped_items

    merged_body = "\n".join(html_bodies)
    merged_html = (
        f'<!DOCTYPE html><html><head><meta charset="utf-8"></head><body>{merged_body}</body></html>'
    )

    return ConversionResult(
        page_count=sum(r.page_count for r in results),
        content_markdown="\n\n".join(all_md),
        content_html=merged_html,
        pages=all_pages,
        skipped_items=total_skipped,
        document_json=_merge_document_json(results),
        content_json=_merge_content_json(results),
    )


def _merge_content_json(results):
    """Merge per-batch VLM JSON extractions into a single canonical JSON.
    Each batch produces a JSON object with the canonical key prefixes defined in
    `VLM_JSON_SECTIONS` (e.g. "Company Name<n>", "Address<n>",
    "Shipping Information<n>", "Goods Description<n>", "Phone<n>", "Fax<n>").
    Re-bucket by section, dedupe, and renumber.

    Dedup is **exact-match only** (see `_dedup_exact_only` for the
    rationale). Per-batch VLM calls sometimes produce the same value
    in multiple batches; we keep one. Whitespace and case variants
    are also collapsed.
    """
    import json
    sections = {name: [] for name in VLM_JSON_SECTIONS}
    # Match longest prefix first so we never bucket a key under a shorter
    # sibling (e.g. "Goods Description" before "Address" — defensive, the
    # current set has no overlap, but cheap insurance).
    ordered = sorted(VLM_JSON_SECTIONS, key=len, reverse=True)
    for r in results:
        cj = getattr(r, "content_json", None)
        if not cj:
            continue
        try:
            data = json.loads(cj)
        except (json.JSONDecodeError, ValueError):
            continue
        if not isinstance(data, dict):
            continue
        for key, value in data.items():
            if not isinstance(key, str):
                continue
            for prefix in ordered:
                if key.startswith(prefix):
                    if value is not None:
                        s = str(value).strip()
                        if s:
                            sections[prefix].append(s)
                    break
    merged = {}
    for section_name in VLM_JSON_SECTIONS:
        deduped = _dedup_exact_only(sections[section_name])
        for i, v in enumerate(deduped, start=1):
            merged[f"{section_name}{i}"] = v
    if not merged:
        return None
    return json.dumps(merged, indent=2, ensure_ascii=False)


def merge_extractions(*json_blobs: str | None) -> str | None:
    """Merge two or more 4-section JSON extractions into a single canonical JSON.

    Used by the "Deep Extract" mode: standard-pipeline+Ask JSON and
    VLM-direct JSON for the same document are unioned by section.

    Dedup strategy (v2, 2026-06-13): **exact-match only**. Two values
    are considered duplicates only when they normalise to the same
    string (case-insensitive, whitespace-collapsed). Substring variants
    (e.g. "FLUID LIMITED" vs "FLUID LIMITED, KAWASAKI",
    "Wilhelminakade" vs "Wilhelmijnakade") are kept as SEPARATE
    entries — losing one is worse than keeping a near-duplicate. The
    downstream `content_json` is a flat record so users can decide
    which value to trust; the merge's job is to PRESERVE, not to
    NORMALISE.

    Returns the merged JSON as a string, or None if nothing was extractable.
    """
    import json

    sections: dict[str, list[str]] = {name: [] for name in VLM_JSON_SECTIONS}
    ordered = sorted(VLM_JSON_SECTIONS, key=len, reverse=True)

    for blob in json_blobs:
        if not blob:
            continue
        try:
            data = json.loads(blob)
        except (json.JSONDecodeError, ValueError):
            continue
        if not isinstance(data, dict):
            continue
        for key, value in data.items():
            if not isinstance(key, str):
                continue
            for prefix in ordered:
                if key.startswith(prefix):
                    if value is not None:
                        s = str(value).strip()
                        if s:
                            sections[prefix].append(s)
                    break

    return _finalise_merged_sections(sections)


def _normalise_for_dedup(s: str) -> str:
    """Whitespace-collapse + lowercase for the exact-match check."""
    return " ".join(s.split()).lower()


def _dedup_exact_only(values: list[str]) -> list[str]:
    """Exact-match dedup only — preserve substring and case variants.

    Two values are considered duplicates iff their normalised form
    (lowercase + whitespace-collapsed) is identical. Everything else
    is kept as a separate entry, preserving first-seen order. This
    is the v2 strategy (2026-06-13); the v1 substring/longer-wins
    logic dropped legitimate data (e.g. address fragments that the
    VLM and Ask disagreed on), so the bar for "duplicate" was raised
    to exact-only. Some duplication is acceptable; missing data is
    not.
    """
    kept: list[str] = []
    kept_n: list[str] = []
    for v in values:
        nv = _normalise_for_dedup(v)
        if not nv:
            continue
        if nv in kept_n:
            continue
        kept.append(v)
        kept_n.append(nv)
    return kept


def _finalise_merged_sections(sections: dict[str, list[str]]) -> str | None:
    """Dedup each section (exact-match only) and renumber to
    `<Section>1..N`. Returns the JSON string or None when empty."""
    import json

    merged: dict[str, str] = {}
    for section_name in VLM_JSON_SECTIONS:
        deduped = _dedup_exact_only(sections[section_name])
        for i, v in enumerate(deduped, start=1):
            merged[f"{section_name}{i}"] = v
    if not merged:
        return None
    return json.dumps(merged, indent=2, ensure_ascii=False)

def classify_error(exc: Exception) -> str:
    """Return a user-friendly error message based on the exception type/content."""
    msg = str(exc).lower()

    if "invalidcxxcompiler" in msg or "no working c++ compiler" in msg:
        return "Missing C++ compiler — set TORCHDYNAMO_DISABLE=1 to work around this"

    if "out of memory" in msg or "oom" in msg:
        return "Out of memory — try a smaller document or disable table structure analysis"

    if "could not acquire converter lock" in msg:
        return "Server busy — a previous conversion is still running. Please retry later"

    if "pipeline" in msg and "failed" in msg:
        return "Document processing failed — the document may be corrupted or unsupported"

    if "timeout" in msg:
        return "Processing took too long — try with fewer pages or simpler options"

    # Fallback: truncate raw error to something reasonable
    raw = str(exc)
    if len(raw) > 200:
        raw = raw[:200] + "…"
    return raw
