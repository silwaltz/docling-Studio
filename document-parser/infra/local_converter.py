"""Local Docling converter — runs Docling as a Python library in-process.

This adapter implements the DocumentConverter port using the Docling library
directly. It wraps the blocking DocumentConverter in asyncio.to_thread for
non-blocking execution.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import os
import re
import tempfile
import threading
from pathlib import Path

from docling.datamodel.base_models import InputFormat
from docling.datamodel.pipeline_options import (
    EasyOcrOptions,
    PdfPipelineOptions,
    TableFormerMode,
    TableStructureOptions,
    VlmPipelineOptions,
)
from docling.datamodel import vlm_model_specs
from docling.document_converter import DocumentConverter as DoclingConverter
from docling.document_converter import PdfFormatOption
from docling.pipeline.vlm_pipeline import VlmPipeline
from docling_core.types.doc import (
    CodeItem,
    DocItem,
    FloatingItem,
    FormulaItem,
    GroupItem,
    ListItem,
    PictureItem,
    SectionHeaderItem,
    TableItem,
    TextItem,
    TitleItem,
)

from domain.value_objects import (
    DEFAULT_PAGE_HEIGHT,
    DEFAULT_PAGE_WIDTH,
    ConversionOptions,
    ConversionResult,
    PageDetail,
    PageElement,
)
from infra.bbox import to_topleft_list
from infra.settings import settings

logger = logging.getLogger(__name__)

# Thread lock — DoclingConverter is not thread-safe.
# Uses a timeout to prevent a frozen conversion from blocking all others.
_converter_lock = threading.Lock()

# Default converter (lazy-init on first request)
_default_converter: DoclingConverter | None = None


def _preprocess_pdf_to_dpi(file_path: str, dpi: int) -> str:
    """Preprocess PDF by converting to images at specified DPI and back to PDF.

    This improves extraction quality for scanned/image-based PDFs by ensuring
    consistent resolution. Recommended DPI is 300 for scanned documents.

    Args:
        file_path: Path to the original PDF
        dpi: Target DPI for conversion (e.g., 300)

    Returns:
        Path to the preprocessed PDF (temp file)
    """
    try:
        from pdf2image import convert_from_path
        from PIL import Image

        logger.info("Preprocessing PDF to %d DPI: %s", dpi, file_path)

        # Convert PDF pages to images at specified DPI
        images = convert_from_path(file_path, dpi=dpi, fmt='jpeg')

        if not images:
            logger.warning("No pages extracted from PDF during preprocessing")
            return file_path

        # Save images as a new PDF
        temp_dir = tempfile.gettempdir()
        base_name = Path(file_path).stem
        output_path = os.path.join(temp_dir, f"{base_name}_{dpi}dpi.pdf")

        # Convert images to RGB mode if necessary and save as PDF
        rgb_images = []
        for img in images:
            if img.mode != 'RGB':
                rgb_images.append(img.convert('RGB'))
            else:
                rgb_images.append(img)

        if rgb_images:
            rgb_images[0].save(
                output_path,
                'PDF',
                save_all=True,
                append_images=rgb_images[1:],
                resolution=dpi
            )

        logger.info("PDF preprocessed successfully: %s (%d pages at %d DPI)",
                    output_path, len(rgb_images), dpi)
        return output_path

    except ImportError:
        logger.warning("pdf2image not installed, skipping PDF preprocessing. "
                      "Install with: pip install pdf2image pillow")
        return file_path
    except Exception as exc:
        logger.warning("PDF preprocessing failed: %s", exc)
        return file_path


# ---------------------------------------------------------------------------
# Element type detection
# ---------------------------------------------------------------------------

_ELEMENT_TYPE_MAP: list[tuple[type, str]] = [
    (TableItem, "table"),
    (PictureItem, "picture"),
    (TitleItem, "title"),
    (SectionHeaderItem, "section_header"),
    (ListItem, "list"),
    (FormulaItem, "formula"),
    (CodeItem, "code"),
    (FloatingItem, "floating"),
    (TextItem, "text"),
]


def _get_element_type(item: DocItem) -> str:
    for cls, type_name in _ELEMENT_TYPE_MAP:
        if isinstance(item, cls):
            return type_name
    return "text"


# ---------------------------------------------------------------------------
# Pipeline factory
# ---------------------------------------------------------------------------


def _build_docling_converter(options: ConversionOptions) -> DoclingConverter:
    # If VLM Pipeline is forced, use it instead of standard pipeline
    if options.force_vlm_pipeline:
        return _build_vlm_converter(options)

    table_options = TableStructureOptions(
        do_cell_matching=True,
        mode=TableFormerMode.ACCURATE if options.table_mode == "accurate" else TableFormerMode.FAST,
    )

    ocr_options = EasyOcrOptions(
        lang=['en'],
        force_full_page_ocr=options.force_full_page_ocr,
        use_gpu=True,
    )

    pipeline_options = PdfPipelineOptions(
        do_ocr=options.do_ocr,
        ocr_options=ocr_options,
        do_table_structure=options.do_table_structure,
        table_structure_options=table_options,
        do_code_enrichment=options.do_code_enrichment,
        do_formula_enrichment=options.do_formula_enrichment,
        do_picture_classification=options.do_picture_classification,
        do_picture_description=options.do_picture_description,
        generate_page_images=options.generate_page_images,
        generate_picture_images=options.generate_picture_images,
        images_scale=options.images_scale,
        document_timeout=settings.document_timeout,
    )

    return DoclingConverter(
        format_options={
            InputFormat.PDF: PdfFormatOption(pipeline_options=pipeline_options),
        }
    )


def _ensure_default_converter() -> DoclingConverter:
    global _default_converter
    if _default_converter is None:
        try:
            _default_converter = _build_docling_converter(ConversionOptions())
        except Exception:
            raise
    return _default_converter


def _select_converter(options: ConversionOptions) -> DoclingConverter:
    if options.is_default():
        return _ensure_default_converter()
    return _build_docling_converter(options)


# ---------------------------------------------------------------------------
# Page extraction
# ---------------------------------------------------------------------------


def _extract_pages_detail(doc_result) -> tuple[list[PageDetail], int]:
    pages: dict[int, PageDetail] = {}
    document = doc_result.document
    skipped = 0

    for page_key, page_obj in document.pages.items():
        page_no = int(page_key) if isinstance(page_key, str) else page_key
        pages[page_no] = PageDetail(
            page_number=page_no,
            width=page_obj.size.width,
            height=page_obj.size.height,
        )

    for item, level in document.iterate_items():
        ok = _process_content_item(item, level, pages)
        if not ok:
            skipped += 1

    sorted_pages = sorted(pages.values(), key=lambda p: p.page_number)
    return sorted_pages, skipped


def _process_content_item(
    item: DocItem | GroupItem,
    level: int,
    pages: dict[int, PageDetail],
) -> bool:
    if isinstance(item, GroupItem):
        return True

    if not isinstance(item, DocItem) or not item.prov:
        return False

    for prov in item.prov:
        try:
            page_no = prov.page_no
            if page_no not in pages:
                logger.warning(
                    "Page %d not found in document metadata — using US Letter fallback (%sx%s pt)",
                    page_no,
                    DEFAULT_PAGE_WIDTH,
                    DEFAULT_PAGE_HEIGHT,
                )
                pages[page_no] = PageDetail(
                    page_number=page_no, width=DEFAULT_PAGE_WIDTH, height=DEFAULT_PAGE_HEIGHT
                )

            page_height = pages[page_no].height

            bbox = [0.0, 0.0, 0.0, 0.0]
            if prov.bbox:
                bbox = to_topleft_list(prov.bbox, page_height)

            element_type = _get_element_type(item)

            content = getattr(item, "text", "") or ""
            if isinstance(item, TableItem):
                with contextlib.suppress(AttributeError, ValueError):
                    content = item.export_to_markdown()

            pages[page_no].elements.append(
                PageElement(
                    type=element_type,
                    bbox=bbox,
                    content=content,
                    level=level,
                    self_ref=getattr(item, "self_ref", "") or "",
                )
            )
        except (AttributeError, KeyError, TypeError, ValueError):
            logger.warning(
                "Skipping item %s on page %s",
                type(item).__name__,
                getattr(prov, "page_no", "?"),
                exc_info=True,
            )
            return False

    return True


# ---------------------------------------------------------------------------
# Direct OCR fallback for pure image-only PDFs using VLM Pipeline
# ---------------------------------------------------------------------------


def _build_vlm_converter(options: ConversionOptions | None = None) -> DoclingConverter:
    """Build a Docling converter using VLM Pipeline.

    Two tuning fixes are applied on top of the stock granite-docling spec to
    get complete, clean extraction:

    1. repetition_penalty (1.1) — without it the model can enter a degenerate
       decoding loop on some documents, emitting only left-margin row numbers
       ("1 2 3 ...") then repeating a single token ("71 71 71 ...") until it
       exhausts max_new_tokens. The penalty breaks that loop so the model reads
       the actual document content. (no_repeat_ngram_size is intentionally NOT
       used — it corrupts the DocTags format, whose tags repeat by design.)

    2. image scale — the stock scale of 2.0 renders dense full-page documents
       too small for the 258M model to read body text, so it captures only large
       header text. Bumping the scale feeds a higher-resolution page image and
       recovers nearly all the text. The scale comes from the per-analysis
       option (options.vlm_image_scale) when set, else settings.vlm_image_scale.
    """
    try:
        # Get the model spec from settings
        model_spec_name = settings.vlm_fallback_model
        model_spec = getattr(vlm_model_specs, model_spec_name, vlm_model_specs.GRANITEDOCLING_TRANSFORMERS)

        # Clone the spec and inject a repetition penalty into the generation
        # config to prevent degenerate repetition loops.
        vlm_options = model_spec.model_copy(deep=True)
        gen_config = dict(vlm_options.extra_generation_config or {})
        gen_config.setdefault("repetition_penalty", 1.1)
        vlm_options.extra_generation_config = gen_config

        # Resolve the page-image render scale: per-analysis override wins,
        # otherwise fall back to the server default (see docstring).
        image_scale = settings.vlm_image_scale
        if options is not None and options.vlm_image_scale > 0:
            image_scale = options.vlm_image_scale
        vlm_options.scale = image_scale

        pipeline_options = VlmPipelineOptions(
            vlm_options=vlm_options,
        )
        pipeline_options.images_scale = image_scale

        return DoclingConverter(
            format_options={
                InputFormat.PDF: PdfFormatOption(
                    pipeline_cls=VlmPipeline,
                    pipeline_options=pipeline_options,
                ),
            }
        )
    except Exception as exc:
        logger.warning("Failed to build VLM converter: %s", exc)
        raise


def _clean_vlm_markdown(markdown: str) -> str:
    """Clean up VLM Pipeline markdown output.

    VLM models sometimes output:
    - HTML comments like <!-- image -->, <!-- table -->, <!-- figure -->
    - Repeated text fragments
    - Extra whitespace

    This function cleans up these artifacts.
    """
    if not markdown:
        return markdown

    # Remove HTML comment markers (<!-- image -->, <!-- table -->, etc.)
    cleaned = re.sub(r'<!--\s*\w+\s*-->', '', markdown)

    # Split into lines for processing
    lines = cleaned.split('\n')
    cleaned_lines = []
    prev_line = None
    repeat_count = 0

    for line in lines:
        stripped = line.strip()
        if not stripped:
            cleaned_lines.append(line)
            prev_line = None
            repeat_count = 0
            continue

        # Detect repeated lines (same content repeated many times)
        if stripped == prev_line:
            repeat_count += 1
            if repeat_count <= 2:  # Allow up to 2 repeats
                cleaned_lines.append(line)
            # Skip additional repeats
        else:
            cleaned_lines.append(line)
            prev_line = stripped
            repeat_count = 0

    cleaned = '\n'.join(cleaned_lines)

    # Remove excessive blank lines (more than 2 consecutive)
    cleaned = re.sub(r'\n{4,}', '\n\n\n', cleaned)

    return cleaned.strip()


def _build_vlm_pages_detail(doc, content_markdown: str) -> list[PageDetail]:
    """Build synthetic PageDetail objects from VLM Pipeline output.

    The VLM Pipeline produces markdown text but doesn't create detailed element
    structure with bounding boxes like the standard pipeline. This function
    creates a basic page structure with the markdown content as text elements.
    """
    pages_detail: list[PageDetail] = []

    # Split markdown by pages (VLM typically outputs page markers)
    page_contents = content_markdown.split("\n---\n") if "---" in content_markdown else [content_markdown]

    for page_idx, (page_key, page_obj) in enumerate(doc.pages.items()):
        page_no = int(page_key) if isinstance(page_key, str) else page_key
        page_content = page_contents[page_idx] if page_idx < len(page_contents) else ""

        page_detail = PageDetail(
            page_number=page_no,
            width=page_obj.size.width if hasattr(page_obj, 'size') else DEFAULT_PAGE_WIDTH,
            height=page_obj.size.height if hasattr(page_obj, 'size') else DEFAULT_PAGE_HEIGHT,
        )

        # Add the page content as a single text element
        if page_content.strip():
            page_detail.elements.append(
                PageElement(
                    type="text",
                    bbox=[0, 0, page_detail.width, page_detail.height],  # Full page bbox
                    content=page_content.strip(),
                    level=0,
                    self_ref=f"",
                )
            )

        pages_detail.append(page_detail)

    return pages_detail


def _vlm_convert_document(file_path: str, page_range: tuple[int, int] | None = None) -> tuple[str, list[PageDetail]]:
    """Convert a document using VLM Pipeline for OCR fallback.

    Returns (markdown_string, list[PageDetail]).
    """
    try:
        converter = _build_vlm_converter()
        kwargs: dict = {}
        if settings.max_page_count > 0:
            kwargs["max_num_pages"] = settings.max_page_count
        if settings.max_file_size > 0:
            kwargs["max_file_size"] = settings.max_file_size
        if page_range is not None:
            kwargs["page_range"] = page_range

        result = converter.convert(file_path, **kwargs)
        doc = result.document

        content_markdown = doc.export_to_markdown()

        # For VLM fallback, create synthetic page structure
        pages_detail = _build_vlm_pages_detail(doc, content_markdown)

        logger.info("VLM Pipeline conversion: %d pages with synthetic structure", len(pages_detail))

        return content_markdown, pages_detail

    except Exception as exc:
        logger.warning("VLM Pipeline conversion failed: %s", exc)
        raise


def _ocr_fallback(
    file_path: str, page_range: tuple[int, int] | None = None
) -> tuple[str, list[PageDetail]]:
    """OCR fallback using Docling's VLM Pipeline.

    When the standard pipeline produces no text (pure image PDF),
    this function uses VLM Pipeline as a fallback for high-quality extraction.

    Returns (markdown_string, list[PageDetail]).
    """
    try:
        logger.info("Attempting VLM Pipeline fallback for %s", file_path)
        content_markdown, pages_detail = _vlm_convert_document(file_path, page_range)
        logger.info("VLM Pipeline fallback succeeded: %d pages extracted", len(pages_detail))
        return content_markdown, pages_detail
    except Exception as exc:
        logger.warning("VLM Pipeline fallback failed: %s", exc)
        return "", []


def _build_vlm_document_json(doc, pages: list[PageDetail]) -> str:
    """Build a Docling-compatible document JSON from VLM Pipeline output.

    The VLM Pipeline produces items but with a different internal structure.
    This function transforms the VLM output into a format the frontend expects,
    consolidating small text fragments into meaningful paragraphs.
    """
    texts: list[dict] = []
    body_children: list[dict] = []
    pictures: list[dict] = []
    tables: list[dict] = []

    # First pass: collect and consolidate text items by page
    page_texts: dict[int, list[str]] = {p.page_number: [] for p in pages}

    # Iterate through VLM document items
    item_idx = 0
    for item, level in doc.iterate_items():
        if hasattr(item, 'text') and item.text:
            # Find which page this item belongs to
            page_no = 1  # default
            if hasattr(item, 'prov') and item.prov:
                for prov in item.prov:
                    if hasattr(prov, 'page_no'):
                        page_no = prov.page_no
                        break

            text_content = str(item.text).strip()
            if text_content and len(text_content) > 0:
                if page_no not in page_texts:
                    page_texts[page_no] = []
                page_texts[page_no].append(text_content)

        item_idx += 1

    # Second pass: create consolidated text elements per page
    for page in pages:
        page_no = page.page_number
        page_content_parts = page_texts.get(page_no, [])

        if page_content_parts:
            # Consolidate all text on this page into a single paragraph
            consolidated_text = " ".join(page_content_parts)

            ref = f"#/texts/{len(texts)}"
            prov = {
                "page_no": page_no,
                "bbox": {
                    "l": 0,
                    "t": 0,
                    "r": page.width,
                    "b": page.height,
                    "coord_origin": "TOPLEFT",
                },
            }
            texts.append({
                "self_ref": ref,
                "label": "paragraph",
                "text": consolidated_text,
                "prov": [prov],
            })
            body_children.append({"$ref": ref})

    # Build the document JSON
    doc_json = {
        "schema_name": "DoclingDocument",
        "version": "1.0.0",
        "name": "vlm_conversion",
        "body": {"self_ref": "#/body", "children": body_children, "content_layer": "body"},
        "texts": texts,
        "pictures": pictures,
        "tables": tables,
        "key_value_items": [],
        "form_items": [],
        "pages": {
            str(p.page_number): {
                "size": {"width": p.width, "height": p.height},
                "page_no": p.page_number,
            }
            for p in pages
        },
        "groups": [],
    }
    return json.dumps(doc_json)


def _build_ocr_document_json(pages: list[PageDetail]) -> str:
    """Build a minimal Docling-compatible document JSON from OCR PageDetail objects.

    Produces a flat list of `paragraph` items — one per OCR text region —
    so `_build_tree_nodes` (which reads `body.children` + `texts`) can
    render them in the Structure panel.
    """
    texts: list[dict] = []
    body_children: list[dict] = []

    for page in pages:
        for el in page.elements:
            ref = el.self_ref or f"ocr-{len(texts)}"
            prov = {
                "page_no": page.page_number,
                "bbox": {
                    "l": el.bbox[0] if el.bbox else 0,
                    "t": el.bbox[1] if el.bbox else 0,
                    "r": el.bbox[2] if el.bbox else 0,
                    "b": el.bbox[3] if el.bbox else 0,
                    "coord_origin": "TOPLEFT",
                },
            }
            texts.append({
                "self_ref": ref,
                "label": "paragraph",
                "text": el.content or "",
                "prov": [prov],
            })
            body_children.append({"$ref": ref})

    doc = {
        "schema_name": "DoclingDocument",
        "version": "1.0.0",
        "name": "ocr_fallback",
        "body": {"self_ref": "#/body", "children": body_children, "content_layer": "body"},
        "texts": texts,
        "pictures": [],
        "tables": [],
        "key_value_items": [],
        "form_items": [],
        "pages": {
            str(p.page_number): {
                "size": {"width": p.width, "height": p.height},
                "page_no": p.page_number,
            }
            for p in pages
        },
        "groups": [],
    }
    return json.dumps(doc)


def _result_from_flat_texts(doc, page_count: int) -> ConversionResult | None:
    """Build a ConversionResult from the flat ``doc.texts`` / ``doc.tables`` lists.

    Some documents (e.g. colored shipping forms / Air Waybills) make the layout
    model classify the *entire page* as a single ``picture``. The OCR'd text
    cells then live in ``doc.texts`` but are orphaned from the body tree, so
    ``export_to_markdown()`` and ``iterate_items()`` only yield
    ``<!-- image -->``. This reads the flat lists directly — preserving each
    item's page/bbox via ``prov`` — so the markdown, Structure panel, and Visual
    overlay all populate. Returns ``None`` if no usable text is found.
    """
    pages: dict[int, PageDetail] = {}
    for page_key, page_obj in doc.pages.items():
        page_no = int(page_key) if isinstance(page_key, str) else page_key
        pages[page_no] = PageDetail(
            page_number=page_no,
            width=page_obj.size.width,
            height=page_obj.size.height,
        )

    md_parts: list[str] = []
    texts_json: list[dict] = []
    body_children: list[dict] = []

    def _emit(item, content: str, label: str) -> None:
        content = (content or "").strip()
        if not content:
            return
        page_no = next(iter(pages), 1)
        bbox = [0.0, 0.0, 0.0, 0.0]
        prov_list = getattr(item, "prov", None) or []
        if prov_list:
            prov = prov_list[0]
            page_no = getattr(prov, "page_no", page_no)
            if page_no not in pages:
                pages[page_no] = PageDetail(
                    page_number=page_no, width=DEFAULT_PAGE_WIDTH, height=DEFAULT_PAGE_HEIGHT
                )
            if getattr(prov, "bbox", None):
                bbox = to_topleft_list(prov.bbox, pages[page_no].height)
        if page_no not in pages:
            pages[page_no] = PageDetail(
                page_number=page_no, width=DEFAULT_PAGE_WIDTH, height=DEFAULT_PAGE_HEIGHT
            )
        ref = getattr(item, "self_ref", "") or f"#/texts/{len(texts_json)}"
        pages[page_no].elements.append(
            PageElement(type=label, bbox=bbox, content=content, level=0, self_ref=ref)
        )
        texts_json.append(
            {
                "self_ref": ref,
                "label": "paragraph",
                "text": content,
                "prov": [
                    {
                        "page_no": page_no,
                        "bbox": {
                            "l": bbox[0],
                            "t": bbox[1],
                            "r": bbox[2],
                            "b": bbox[3],
                            "coord_origin": "TOPLEFT",
                        },
                    }
                ],
            }
        )
        body_children.append({"$ref": ref})
        md_parts.append(content)

    for t in getattr(doc, "texts", []) or []:
        _emit(t, getattr(t, "text", ""), "text")

    for tbl in getattr(doc, "tables", []) or []:
        try:
            tbl_md = tbl.export_to_markdown(doc)
        except (AttributeError, ValueError, TypeError):
            tbl_md = ""
        _emit(tbl, tbl_md, "table")

    if not md_parts:
        return None

    content_markdown = "\n\n".join(md_parts)
    sorted_pages = sorted(pages.values(), key=lambda p: p.page_number)
    doc_json = {
        "schema_name": "DoclingDocument",
        "version": "1.0.0",
        "name": "flat_text_recovery",
        "body": {"self_ref": "#/body", "children": body_children, "content_layer": "body"},
        "texts": texts_json,
        "pictures": [],
        "tables": [],
        "key_value_items": [],
        "form_items": [],
        "pages": {
            str(p.page_number): {
                "size": {"width": p.width, "height": p.height},
                "page_no": p.page_number,
            }
            for p in sorted_pages
        },
        "groups": [],
    }
    return ConversionResult(
        page_count=page_count or len(sorted_pages) or 1,
        content_markdown=content_markdown,
        content_html="",
        pages=sorted_pages,
        skipped_items=0,
        document_json=json.dumps(doc_json),
    )


def _standard_ocr_fallback_result(
    file_path: str, page_range: tuple[int, int] | None
) -> ConversionResult | None:
    """Run the standard pipeline with full-page OCR, recovering orphaned text.

    Used when the VLM pipeline returns a degenerate result (the whole page
    classified as one picture, no text). The standard EasyOCR path reads the
    text reliably; ``_result_from_flat_texts`` then rebuilds the document from
    the flat text list. Returns ``None`` if OCR also yields nothing.
    """
    try:
        conv = _build_docling_converter(ConversionOptions(force_full_page_ocr=True))
        kwargs: dict = {}
        if settings.max_page_count > 0:
            kwargs["max_num_pages"] = settings.max_page_count
        if settings.max_file_size > 0:
            kwargs["max_file_size"] = settings.max_file_size
        if page_range is not None:
            kwargs["page_range"] = page_range

        acquired = _converter_lock.acquire(timeout=settings.lock_timeout)
        if not acquired:
            logger.warning("Standard OCR fallback: could not acquire converter lock")
            return None
        try:
            result = conv.convert(file_path, **kwargs)
        finally:
            _converter_lock.release()

        doc = result.document
        page_count = len(doc.pages)
        # Prefer the normal extraction when it actually produced text.
        normal_md = doc.export_to_markdown()
        if not _is_text_empty(normal_md, page_count):
            pages_detail, skipped = _extract_pages_detail(result)
            return ConversionResult(
                page_count=page_count or len(pages_detail) or 1,
                content_markdown=normal_md,
                content_html=doc.export_to_html(),
                pages=pages_detail,
                skipped_items=skipped,
                document_json=json.dumps(doc.export_to_dict()),
            )
        return _result_from_flat_texts(doc, page_count)
    except Exception as exc:
        logger.warning("Standard OCR fallback failed: %s", exc)
        return None


_MIN_CHARS_PER_PAGE = 500  # below this density we consider extraction poor


def _is_text_empty(markdown: str, page_count: int = 1) -> bool:
    """Return True if markdown has no meaningful text content.

    Triggers the OCR fallback in two cases:
    1. Pure image PDF: has <!-- image --> placeholder and <100 non-heading chars.
    2. Low-density extraction: has <!-- image --> and extracted text is below
       _MIN_CHARS_PER_PAGE per page — catches partially-scanned docs where
       Docling extracts some garbled text but misses most of the content.
    """
    has_image_placeholder = "<!-- image -->" in markdown
    if not has_image_placeholder:
        return False
    cleaned = re.sub(r"<!--.*?-->", "", markdown, flags=re.DOTALL)
    cleaned = re.sub(r"^#+\s.*$", "", cleaned, flags=re.MULTILINE)
    cleaned = re.sub(r"^\|.*\|$", "", cleaned, flags=re.MULTILINE)
    cleaned = cleaned.strip()
    if len(cleaned) < 100:
        return True
    pages = max(page_count, 1)
    return (len(cleaned) / pages) < _MIN_CHARS_PER_PAGE


# ---------------------------------------------------------------------------
# Synchronous conversion (called via asyncio.to_thread)
# ---------------------------------------------------------------------------


def _convert_sync(
    file_path: str,
    options: ConversionOptions,
    *,
    page_range: tuple[int, int] | None = None,
) -> ConversionResult:
    # Apply PDF preprocessing if DPI is specified (but NOT for VLM pipeline)
    # VLM pipeline does its own image processing internally, so preprocessing
    # can actually hurt performance and cause issues
    actual_file_path = file_path
    temp_preprocessed_path: str | None = None

    if options.preprocess_pdf_dpi > 0 and not options.force_vlm_pipeline:
        temp_preprocessed_path = _preprocess_pdf_to_dpi(file_path, options.preprocess_pdf_dpi)
        if temp_preprocessed_path != file_path:
            actual_file_path = temp_preprocessed_path
            logger.info("PDF preprocessed to %d DPI: %s", options.preprocess_pdf_dpi, actual_file_path)
    elif options.preprocess_pdf_dpi > 0 and options.force_vlm_pipeline:
        logger.info("Skipping PDF preprocessing for VLM pipeline (not needed)")

    acquired = _converter_lock.acquire(timeout=settings.lock_timeout)
    if not acquired:
        raise TimeoutError(
            f"Could not acquire converter lock within {settings.lock_timeout}s — "
            "a previous conversion may be frozen"
        )
    try:
        conv = _select_converter(options)
        kwargs: dict = {}
        if settings.max_page_count > 0:
            kwargs["max_num_pages"] = settings.max_page_count
        if settings.max_file_size > 0:
            kwargs["max_file_size"] = settings.max_file_size
        if page_range is not None:
            kwargs["page_range"] = page_range
        result = conv.convert(actual_file_path, **kwargs)
    finally:
        _converter_lock.release()
        # Cleanup temp preprocessed file
        if temp_preprocessed_path and temp_preprocessed_path != file_path:
            try:
                os.unlink(temp_preprocessed_path)
            except OSError:
                pass

    doc = result.document
    page_count = len(doc.pages)
    pages_detail, skipped = _extract_pages_detail(result)

    # VLM Pipeline — the granite-docling model emits DocTags with per-item
    # bbox locations, so the document carries the same structure as the
    # standard pipeline (texts/tables/pictures with prov). We therefore reuse
    # the standard extraction path (`_extract_pages_detail` above +
    # `export_to_dict` below) and only post-process the markdown to strip the
    # model's <!-- image --> placeholders and any residual repetition.
    if options.force_vlm_pipeline:
        raw_markdown = doc.export_to_markdown()
        content_markdown = _clean_vlm_markdown(raw_markdown)

        md_preview = content_markdown[:200].replace('\n', ' ') if content_markdown else "(empty)"
        logger.info(
            "VLM Pipeline: raw_md=%d chars, cleaned_md=%d chars, pages=%d, elements=%d, preview: %s...",
            len(raw_markdown) if raw_markdown else 0,
            len(content_markdown) if content_markdown else 0,
            len(pages_detail),
            sum(len(p.elements) for p in pages_detail),
            md_preview,
        )

        # Degenerate VLM output: the granite-docling model sometimes classifies
        # the whole page as a single <picture> (common for colored forms / Air
        # Waybills), yielding no text at all. Fall back to the standard pipeline
        # with full-page OCR, which reads the text reliably.
        if not content_markdown.strip():
            logger.warning(
                "VLM Pipeline produced no text (page likely classified as one "
                "picture) — falling back to standard pipeline + full-page OCR"
            )
            fallback = _standard_ocr_fallback_result(file_path, page_range)
            if fallback is not None and fallback.content_markdown.strip():
                logger.info(
                    "VLM→standard OCR fallback recovered %d chars", len(fallback.content_markdown)
                )
                return fallback
            logger.warning("VLM→standard OCR fallback yielded no text either")

        # Fall back to the synthetic single-paragraph structure only if the
        # standard extraction found no bbox'd elements (degenerate output).
        if not any(p.elements for p in pages_detail):
            logger.warning("VLM Pipeline: no bbox elements extracted — using consolidated fallback")
            pages_detail = _build_vlm_pages_detail(doc, content_markdown)
            document_json = _build_vlm_document_json(doc, pages_detail)
        else:
            document_json = json.dumps(doc.export_to_dict())

        return ConversionResult(
            page_count=page_count or len(pages_detail) or 1,
            content_markdown=content_markdown,
            content_html=doc.export_to_html(),
            pages=pages_detail,
            skipped_items=skipped,
            document_json=document_json,
        )

    if not pages_detail and page_count > 0:
        pages_detail = [
            PageDetail(
                page_number=i + 1,
                width=doc.pages[i + 1].size.width if (i + 1) in doc.pages else DEFAULT_PAGE_WIDTH,
                height=doc.pages[i + 1].size.height
                if (i + 1) in doc.pages
                else DEFAULT_PAGE_HEIGHT,
            )
            for i in range(page_count)
        ]

    if skipped > 0:
        logger.info("Parsed: %d pages, %d items skipped", page_count, skipped)

    content_markdown = doc.export_to_markdown()

    # Debug logging for markdown output
    md_preview = content_markdown[:500].replace('\n', ' ') if content_markdown else "(empty)"
    logger.info(
        "Markdown export: %d chars, preview: %s...",
        len(content_markdown) if content_markdown else 0,
        md_preview[:200]
    )

    # Recover orphaned text: if the layout model classified the whole page as a
    # single picture, the OCR'd cells live in doc.texts but are dropped from the
    # markdown body (export yields only "<!-- image -->"). Rebuild from the flat
    # text list so the content isn't lost (common for colored shipping forms).
    if _is_text_empty(content_markdown, page_count) and getattr(doc, "texts", None):
        recovered = _result_from_flat_texts(doc, page_count)
        if recovered is not None and recovered.content_markdown.strip():
            logger.warning(
                "Standard pipeline: markdown degenerate (full-page picture) — "
                "recovered %d chars from %d orphaned text items",
                len(recovered.content_markdown),
                len(doc.texts),
            )
            return recovered

    # If force_full_page_ocr is set and Docling produced no text (pure image PDF),
    # fall back to direct EasyOCR on the rendered page images.
    if options.force_full_page_ocr and _is_text_empty(content_markdown, page_count):
        logger.warning(
            "Docling produced no text for %s — running direct OCR fallback", file_path
        )
        content_markdown, ocr_pages = _ocr_fallback(file_path, page_range)
        if ocr_pages:
            pages_detail = ocr_pages
            ocr_document_json = _build_ocr_document_json(ocr_pages)
        else:
            ocr_document_json = None
    else:
        ocr_document_json = None

    return ConversionResult(
        page_count=page_count or len(pages_detail) or 1,
        content_markdown=content_markdown,
        content_html=doc.export_to_html(),
        pages=pages_detail,
        skipped_items=skipped,
        document_json=ocr_document_json if ocr_document_json else json.dumps(doc.export_to_dict()),
    )


# ---------------------------------------------------------------------------
# Public adapter class
# ---------------------------------------------------------------------------


class LocalConverter:
    """Adapter that runs Docling locally as a Python library."""

    # In-process — the orchestrator may slice long docs into page batches
    # and merge results (cf. AnalysisService._run_batched_conversion).
    supports_page_batching: bool = True

    async def convert(
        self,
        file_path: str,
        options: ConversionOptions,
        *,
        page_range: tuple[int, int] | None = None,
    ) -> ConversionResult:
        return await asyncio.to_thread(_convert_sync, file_path, options, page_range=page_range)
