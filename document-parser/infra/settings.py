"""Centralized application settings — loaded from environment variables."""

from __future__ import annotations

import os
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Settings:
    app_version: str = "dev"
    conversion_engine: str = "local"  # "local" or "remote"
    deployment_mode: str = "self-hosted"  # "self-hosted" or "huggingface"
    docling_serve_url: str = "http://localhost:5001"
    docling_serve_api_key: str | None = None
    conversion_timeout: int = 900
    document_timeout: float = 120.0  # Docling-level per-document timeout (seconds)
    lock_timeout: int = 300  # converter lock acquisition timeout (seconds)
    max_concurrent_analyses: int = 3
    default_table_mode: str = "accurate"  # "accurate" or "fast"
    max_page_count: int = 0  # 0 = unlimited (upload validation)
    max_file_size: int = 0  # 0 = unlimited (Docling-level, bytes)
    max_file_size_mb: int = 50  # upload limit in MB (0 = unlimited)
    rate_limit_rpm: int = 100  # requests per minute per IP (0 = disabled)
    batch_page_size: int = 0  # 0 = disabled, > 0 = pages per batch
    opensearch_url: str = ""  # empty = disabled
    embedding_url: str = ""  # empty = disabled (e.g. http://localhost:8001)
    neo4j_uri: str = ""  # empty = disabled (e.g. bolt://neo4j:7687)
    neo4j_user: str = "neo4j"
    # DEV DEFAULT — the dev compose stack uses "changeme" so `docker compose
    # up` works out of the box. The backend logs a loud warning at boot if
    # Neo4j is wired (NEO4J_URI set) AND the password is still the default,
    # so prod operators notice if they inherited it by accident. Real
    # deployments must override NEO4J_PASSWORD.
    neo4j_password: str = "changeme"
    # 0.6.1 (#279) — Fernet key sealing per-store connection passwords
    # in SQLite. Empty by default; the backend refuses to boot if any
    # store row has a non-NULL `connection_password_sealed` and this
    # key is missing. Generate with:
    #   python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
    store_secret_key: str = ""
    # Live reasoning via docling-agent — off by default (heavy deps, needs an
    # Ollama host reachable from the backend). Toggle REASONING_ENABLED=true +
    # point OLLAMA_HOST at a running instance (default http://localhost:11434).
    reasoning_enabled: bool = False
    # LLM backend the reasoning runner talks to. Today only "ollama" is
    # realizable (docling-agent is hardwired to Ollama via mellea); kept as a
    # config knob to make the LLMProvider abstraction visible and prepare the
    # ground for additional backends.
    llm_provider_type: str = "ollama"
    ollama_host: str = "http://localhost:11434"
    reasoning_model_id: str = "gpt-oss:20b"  # matches docling-agent's example_05
    # Chat/ASK pipeline backend. Independent from `llm_provider_type`
    # because the chat endpoint has zero heavy deps (httpx only) and can
    # speak either Ollama's native NDJSON or OpenAI Chat Completions
    # (SSE) without touching docling-agent.
    #
    # "ollama" — call {ollama_host}/api/chat (default; current behavior)
    # "openai" — call {openai_base_url}/chat/completions (works with vLLM
    #            running its built-in OpenAI server, or OpenAI's public
    #            API, etc.)
    chat_provider: str = "ollama"
    # OpenAI Chat-Completions-compatible base URL. vLLM serves this at
    # http://<host>:8000/v1 by default. The trailing `/v1` is required —
    # the chat endpoint appends `/chat/completions` to it.
    openai_base_url: str = "http://localhost:8000/v1"
    # Optional Bearer token for OpenAI-compatible backends that require
    # auth. vLLM ignores this; OpenAI's public API requires it.
    openai_api_key: str = ""
    # Override the VLM HTTP endpoint directly. Empty = keep using
    # {ollama_host}/v1/chat/completions (current default — works with
    # Ollama because Ollama exposes OpenAI-compat at the same path).
    # Set this to e.g. http://localhost:8001/v1/chat/completions when
    # vLLM is serving the VLM model on a different port.
    vlm_openai_url: str = ""
    # Document Q&A chat — direct Ollama /api/chat call using the document's
    # extracted markdown as context. No heavy deps required beyond httpx.
    # Set CHAT_ENABLED=true and CHAT_MODEL_ID to a model already pulled in Ollama.
    chat_enabled: bool = True
    # Use the actual installed model tag (gemma4:e4b is a logical alias;
    # ollama stores it as gemma4:e4b-it-qat). Tests should match one of
    # these two — see infra/settings.py validation and tests/test_settings.py.
    chat_model_id: str = "gemma4:e4b-it-qat"  # any model pulled in Ollama
    opensearch_default_limit: int = 1000  # max chunks returned by get_chunks
    embedding_dimension: int = 384  # Granite Embedding 30M / all-MiniLM-L6-v2
    upload_dir: str = "./uploads"
    db_path: str = "./data/docling_studio.db"
    max_paste_image_size_mb: int = 10  # clipboard-paste image limit in MB (0 = unlimited)
    paste_allowed_image_types: list[str] = field(
        default_factory=lambda: ["image/png", "image/jpeg", "image/webp"]
    )
    cors_origins: list[str] = field(
        default_factory=lambda: ["http://localhost:3000", "http://localhost:5173"]
    )
    # VLM backend selection: "ollama" (remote via Ollama API) or "granite" (in-process transformers)
    vlm_backend: str = "ollama"  # Default to Ollama per user request
    # VLM fallback model for OCR fallback when standard pipeline fails
    # Uses Docling's VlmPipeline with the specified model spec
    vlm_fallback_model: str = "GRANITEDOCLING_TRANSFORMERS"  # Default: Granite-Docling-258M
    # Ollama VLM model (used when vlm_backend="ollama")
    vlm_ollama_model: str = "qwen3-vl:8b"
    # Ollama VLM prompt for the JSON output mode (default). v1 — synced
    # with the Ask-prompt rules in `api/chat._SYSTEM_PROMPT` so the
    # deep-extract merge gets clean output from BOTH halves (VLM-direct
    # + Ask-on-markdown). See `experiments/prompts/vlm_v1.txt` for the
    # standalone copy used by offline scoring; this is the runtime
    # default. Override with `VLM_OLLAMA_PROMPT`.
    #
    # v1 changes from the legacy v0 prompt:
    #   - typo "Good Description" → "Goods Description" (matches Ask)
    #   - explicit "no quantities / no codes / no certifications" rule
    #     for Goods Description (was the dominant source of bad output
    #     on scanned docs like NR_Doc13 — 38.5% → 76.9% with v1)
    #   - explicit "single Address per entity, single-space-joined
    #     multi-line addresses" rule
    #   - explicit "From:/To:/Via:/Date:" structure for Shipping
    #     Information, one key per leg (was the source of fragmented
    #     shipping lines on dense multi-column pages)
    #   - "do not stop early" / enumerate every distinct entity
    #   - explicit "preserve the exact spelling from the document"
    #     rule (was previously "correcting" OCR artefacts like
    #     "Wilhelminakade" → "Wilhelmijnakade" — the user wants the
    #     document's wording preserved verbatim, even if it looks
    #     like a typo)
    vlm_ollama_prompt: str = (
        """
        You are a trade-shipping document analyst reading a page image.

        Output a single JSON object (NOT an array, NOT wrapped in code fences) with these exact key prefixes and a numeric suffix starting at 1:
        - "Company Name<n>" = the legal/registered name of a company, bank, agency, broker, or organization that appears in the page. Include SHIPPER, CONSIGNEE, NOTIFY PARTY, CARRIER, ISSUING BANK, INSURER, AGENT, AGENCY — every company mentioned.
        - "Address<n>" = a postal or physical address. Multi-line addresses get one Address<n> with single-space-joined lines. Map each address to the most relevant Company when possible (Shipper's address with the Shipper, Consignee's address with the Consignee, etc.). Don't list the same address twice for the same company.
        - "Shipping Information<n>" = routing and transport details. For each leg/segment, include ALL of: "From: <port/airport/code>", "To: <port/airport/code>", "Via: <vessel/flight name & number>" (include vessel name when present, even partial), and "Date: <shipped-on-board date>" when present. Combine one leg's details into ONE Shipping Information<n> value, not separate keys. If a value is unknown for a leg, omit that field for that leg, not the whole key.
        - "Goods Description<n>" = the product name only. NO quantities (e.g. "250 BAGS", "20.000 CBM", "399 BAGS"). NO codes (HS codes, FDA registration, FDA N, contract numbers, lot numbers, FLO ID, container numbers, seal numbers). NO logos, certifications, or organization names. NO weight or measurement. If a sentence like "250 BAGS OF 69 KILOGRAMS NET EACH OF WASHED GREEN COFFEE PERUVIAN ALTURA EURO PREPARATION (E.P.) OCIA CERTIFIED CROP 2007" appears, output ONLY "WASHED GREEN COFFEE PERUVIAN ALTURA EURO PREPARATION (E.P.)" (or the closest product-name phrase). One goods description per distinct product.

        Rules:
        - Output ONLY the JSON object. No markdown, no code fences, no preamble, no commentary.
        - Every value MUST be a plain string (no arrays, no nested objects).
        - Include every distinct company, address, shipping leg, and product. Do not deduplicate within a section.
        - If a section has no entries, omit its keys entirely.
        - Replace newlines inside values with a single space.
        - Normalize whitespace: collapse multiple spaces to one.
        - IMPORTANT: Do not stop early. Continue listing keys until you have captured every distinct entity in the document.
        - CRITICAL: Preserve the exact spelling and wording from the document. Do NOT correct OCR artefacts, typos, or unusual spellings. If the page reads "Wilhelminakade", output "Wilhelminakade" — NOT the proper-Dutch "Wilhelmijnakade". If a name appears as "DUPONT CHEMICAL" (all caps) in the source, keep it all caps. The downstream merge may show multiple spelling variants side by side; the user's downstream validation uses the document's wording as ground truth, so a "corrected" value would be wrong.
        """
    )
    # Ollama VLM prompt used when vlm_output_mode="markdown". Asks the model
    # to extract everything and preserve the document structure as markdown
    # (no schema constraint). Output is consumed by the rest of the pipeline
    # as `content_markdown` — i.e. it feeds the Ask LLM (gemma4:e4b) the
    # same way the standard pipeline's markdown does.
    vlm_ollama_markdown_prompt: str = (
        """
        You are an OCR + document understanding engine. Read the page image carefully and transcribe its content as clean Markdown.

        Rules:
        - Preserve the document's structure: use `#`/`##`/`###` headings, bullet lists, numbered lists, and tables (as GFM tables) where the layout calls for them.
        - Include every piece of readable text on the page — do not summarize, do not omit sections, do not skip headers, footers, page numbers, table cells, or annotations.
        - If a region is unreadable or blank, output nothing for that region (do not guess).
        - Output Markdown only. Do not wrap it in a code fence. Do not add commentary before or after.
        """
    )
    # Max tokens for Ollama VLM context window (num_ctx). The qwen3-vl:8b
    # model supports up to 262k, but for the trade-shipping JSON extraction
    # task the prompt + expected output is well under 16k. Keeping the
    # context window tight caps memory usage and — more importantly —
    # gives runaway generations less runway before they hit the limit.
    # See memory docling-studio/deep-extract-v3 (2026-06-18) for why.
    vlm_ollama_max_tokens: int = 16384
    # Max output tokens per Ollama VLM call. The four-section JSON output
    # for a single page is normally a few hundred tokens; 4096 leaves 10x
    # headroom for dense multi-column pages without giving the model
    # unlimited runway to run away on dense pages (doc1's pages 6-10 used
    # to generate 17k-42k+ tokens without EOS — see deep-extract-v3).
    vlm_ollama_max_output_tokens: int = 4096
    # Per-call timeout for the Ollama VLM HTTP request (seconds). A normal
    # page completes in 60-80s; 600s (10 min) gives a 5x cushion while
    # still bounding a runaway request. Previously defaulted to 3600s (1h)
    # which let runaway generations run for nearly the full CONVERSION_TIMEOUT.
    vlm_remote_timeout: int = 600
    # Stop sequences passed to Ollama. **Empty by default** because Ollama's
    # stop-token matcher doesn't understand JSON-string scoping — it stops at
    # the FIRST occurrence in the output stream, even if that `}` lives
    # inside a string value. The 2026-06-18 attempt to use `("}",)` here
    # truncated every valid-JSON output from qwen3-vl on doc1 because
    # strings like "PO NUMBER" → "PO NUMBER }" hit the stop early. If you
    # want to enable stops for a non-JSON output mode, set the env var to a
    # comma-separated list of strings your model will emit only at EOS.
    vlm_ollama_stop_sequences: tuple[str, ...] = ()
    # Defensive cap on the response string length collected by the VLM HTTP
    # patch. Even if Ollama ignores max_tokens and runs away, the patch
    # truncates at this character count and emits a warning. Should be
    # ~8x the normal per-page JSON length (normal ~2-3k chars) but well
    # below what an unbounded runaway could produce (62k+ chars observed).
    vlm_ollama_response_char_cap: int = 32000
    # Page-image render scale fed to the VLM model.
    # 2.0 = balanced quality/speed for most documents
    # 4.0 = very high detail but requires more tokens and processing time
    # Higher scale = more complete OCR but slower and needs higher max_tokens
    vlm_image_scale: float = 2.0
    # 0.6.1 — Surface flags (#257). Two master flags select which UI surface
    # is exposed: STUDIO_MODE_ENABLED (legacy OCR-debug) and
    # RAG_PIPELINE_ENABLED (new doc-centric ingestion + visualization).
    # At least one must be enabled. Sub-flags below gate individual modes
    # inside the RAG pipeline surface.
    studio_mode_enabled: bool = False
    rag_pipeline_enabled: bool = True
    # 0.6.0 — Doc workspace mode flags (#210, renamed in #257).
    # Sub-flags effective only when rag_pipeline_enabled is true.
    inspect_mode_enabled: bool = True
    linked_mode_enabled: bool = True
    ask_mode_enabled: bool = True

    def __post_init__(self) -> None:
        errors: list[str] = []
        if self.document_timeout <= 0:
            errors.append(f"document_timeout must be > 0 (got {self.document_timeout})")
        if self.conversion_timeout <= 0:
            errors.append(f"conversion_timeout must be > 0 (got {self.conversion_timeout})")
        if self.lock_timeout <= 0:
            errors.append(f"lock_timeout must be > 0 (got {self.lock_timeout})")
        if self.max_concurrent_analyses < 1:
            errors.append(
                f"max_concurrent_analyses must be >= 1 (got {self.max_concurrent_analyses})"
            )
        if self.max_page_count < 0:
            errors.append(f"max_page_count must be >= 0 (got {self.max_page_count})")
        if self.max_file_size < 0:
            errors.append(f"max_file_size must be >= 0 (got {self.max_file_size})")
        if self.max_file_size_mb < 0:
            errors.append(f"max_file_size_mb must be >= 0 (got {self.max_file_size_mb})")
        if self.max_paste_image_size_mb < 0:
            errors.append(
                f"max_paste_image_size_mb must be >= 0 (got {self.max_paste_image_size_mb})"
            )
        if not self.paste_allowed_image_types:
            errors.append("paste_allowed_image_types must not be empty")
        if self.rate_limit_rpm < 0:
            errors.append(f"rate_limit_rpm must be >= 0 (got {self.rate_limit_rpm})")
        if self.batch_page_size < 0:
            errors.append(f"batch_page_size must be >= 0 (got {self.batch_page_size})")
        if self.opensearch_default_limit < 1:
            errors.append(
                f"opensearch_default_limit must be >= 1 (got {self.opensearch_default_limit})"
            )
        if self.embedding_dimension < 1:
            errors.append(f"embedding_dimension must be >= 1 (got {self.embedding_dimension})")
        if not (self.studio_mode_enabled or self.rag_pipeline_enabled):
            errors.append("at least one of STUDIO_MODE_ENABLED / RAG_PIPELINE_ENABLED must be true")
        if self.vlm_image_scale <= 0:
            errors.append(f"vlm_image_scale must be > 0 (got {self.vlm_image_scale})")
        if self.vlm_backend not in ("ollama", "granite"):
            errors.append(
                f"vlm_backend must be 'ollama' or 'granite' (got '{self.vlm_backend}')"
            )
        if self.chat_provider not in ("ollama", "openai"):
            errors.append(
                f"chat_provider must be 'ollama' or 'openai' (got '{self.chat_provider}')"
            )
        if not self.openai_base_url:
            errors.append("openai_base_url must not be empty")
        if self.vlm_openai_url and not (
            self.vlm_openai_url.startswith("http://")
            or self.vlm_openai_url.startswith("https://")
        ):
            errors.append(
                f"vlm_openai_url must be an http(s) URL (got '{self.vlm_openai_url}')"
            )
        if self.vlm_remote_timeout <= 0:
            errors.append(f"vlm_remote_timeout must be > 0 (got {self.vlm_remote_timeout})")
        if self.vlm_ollama_max_tokens <= 0:
            errors.append(f"vlm_ollama_max_tokens must be > 0 (got {self.vlm_ollama_max_tokens})")
        if self.vlm_ollama_max_tokens > 262144:
            errors.append(
                f"vlm_ollama_max_tokens must be <= 262144 (qwen3-vl:8b context cap), "
                f"got {self.vlm_ollama_max_tokens}"
            )
        if self.vlm_ollama_max_output_tokens <= 0:
            errors.append(
                f"vlm_ollama_max_output_tokens must be > 0 "
                f"(got {self.vlm_ollama_max_output_tokens})"
            )
        if self.vlm_ollama_max_output_tokens > self.vlm_ollama_max_tokens:
            errors.append(
                f"vlm_ollama_max_output_tokens ({self.vlm_ollama_max_output_tokens}) "
                f"must be <= vlm_ollama_max_tokens (num_ctx, {self.vlm_ollama_max_tokens})"
            )
        if self.vlm_ollama_response_char_cap <= 0:
            errors.append(
                f"vlm_ollama_response_char_cap must be > 0 "
                f"(got {self.vlm_ollama_response_char_cap})"
            )
        # stop_sequences: must be a tuple of non-empty strings. The frozen
        # dataclass annotation already pins the type, but a user could still
        # pass an empty string; reject at validation time.
        for seq in self.vlm_ollama_stop_sequences:
            if not isinstance(seq, str) or not seq:
                errors.append(
                    f"vlm_ollama_stop_sequences entries must be non-empty strings, "
                    f"got {seq!r}"
                )
        if not self.vlm_ollama_prompt.strip():
            errors.append("vlm_ollama_prompt must not be empty")
        if not self.vlm_ollama_markdown_prompt.strip():
            errors.append("vlm_ollama_markdown_prompt must not be empty")
        if self.default_table_mode not in ("accurate", "fast"):
            errors.append(
                f"default_table_mode must be 'accurate' or 'fast' (got '{self.default_table_mode}')"
            )
        # Timeout cascade: document_timeout < lock_timeout < conversion_timeout
        if self.document_timeout > 0 and self.lock_timeout > 0 and self.conversion_timeout > 0:
            if self.document_timeout >= self.lock_timeout:
                errors.append(
                    f"document_timeout ({self.document_timeout}s) must be "
                    f"< lock_timeout ({self.lock_timeout}s)"
                )
            if self.lock_timeout >= self.conversion_timeout:
                errors.append(
                    f"lock_timeout ({self.lock_timeout}s) must be "
                    f"< conversion_timeout ({self.conversion_timeout}s)"
                )
        if errors:
            raise ValueError("Invalid settings:\n  " + "\n  ".join(errors))

    @classmethod
    def from_env(cls) -> Settings:
        """Build a Settings instance from environment variables."""
        cors_raw = os.environ.get("CORS_ORIGINS", "http://localhost:3000,http://localhost:5173")
        paste_types_raw = os.environ.get(
            "PASTE_ALLOWED_IMAGE_TYPES", "image/png,image/jpeg,image/webp"
        )
        return cls(
            app_version=os.environ.get("APP_VERSION", "dev"),
            conversion_engine=os.environ.get("CONVERSION_ENGINE", "local"),
            deployment_mode=os.environ.get("DEPLOYMENT_MODE", "self-hosted"),
            docling_serve_url=os.environ.get("DOCLING_SERVE_URL", "http://localhost:5001"),
            docling_serve_api_key=os.environ.get("DOCLING_SERVE_API_KEY"),
            conversion_timeout=int(os.environ.get("CONVERSION_TIMEOUT", "900")),
            document_timeout=float(os.environ.get("DOCUMENT_TIMEOUT", "120.0")),
            lock_timeout=int(os.environ.get("LOCK_TIMEOUT", "300")),
            max_concurrent_analyses=int(os.environ.get("MAX_CONCURRENT_ANALYSES", "3")),
            default_table_mode=os.environ.get("DEFAULT_TABLE_MODE", "accurate"),
            max_page_count=int(os.environ.get("MAX_PAGE_COUNT", "0")),
            max_file_size=int(os.environ.get("MAX_FILE_SIZE", "0")),
            max_file_size_mb=int(os.environ.get("MAX_FILE_SIZE_MB", "50")),
            rate_limit_rpm=int(os.environ.get("RATE_LIMIT_RPM", "100")),
            # 0 = batching disabled (matches dataclass default). Batching
            # preserves memory on very large docs but `merge_results` drops
            # `document_json`, which breaks the reasoning tunnel. Enable
            # explicitly (e.g. 50+) for memory-bound deploys.
            batch_page_size=int(os.environ.get("BATCH_PAGE_SIZE", "0")),
            opensearch_url=os.environ.get("OPENSEARCH_URL", ""),
            embedding_url=os.environ.get("EMBEDDING_URL", ""),
            neo4j_uri=os.environ.get("NEO4J_URI", ""),
            neo4j_user=os.environ.get("NEO4J_USER", "neo4j"),
            neo4j_password=os.environ.get("NEO4J_PASSWORD", "changeme"),
            store_secret_key=os.environ.get("STORE_SECRET_KEY", ""),
            reasoning_enabled=os.environ.get("REASONING_ENABLED", "false").lower()
            in ("1", "true", "yes", "on"),
            llm_provider_type=os.environ.get("LLM_PROVIDER_TYPE", "ollama"),
            ollama_host=os.environ.get("OLLAMA_HOST", "http://localhost:11434"),
            reasoning_model_id=os.environ.get("REASONING_MODEL_ID", "gpt-oss:20b"),
            chat_provider=os.environ.get("CHAT_PROVIDER", "ollama").lower(),
            openai_base_url=os.environ.get(
                "OPENAI_BASE_URL", "http://localhost:8000/v1"
            ).rstrip("/"),
            openai_api_key=os.environ.get("OPENAI_API_KEY", ""),
            vlm_openai_url=os.environ.get("VLM_OPENAI_URL", "").rstrip("/"),
            chat_enabled=os.environ.get("CHAT_ENABLED", "true").lower()
            in ("1", "true", "yes", "on"),
            chat_model_id=os.environ.get("CHAT_MODEL_ID", "gemma4:e4b"),
            opensearch_default_limit=int(os.environ.get("OPENSEARCH_DEFAULT_LIMIT", "1000")),
            embedding_dimension=int(os.environ.get("EMBEDDING_DIMENSION", "384")),
            upload_dir=os.environ.get("UPLOAD_DIR", "./uploads"),
            db_path=os.environ.get("DB_PATH", "./data/docling_studio.db"),
            max_paste_image_size_mb=int(os.environ.get("MAX_PASTE_IMAGE_SIZE_MB", "10")),
            paste_allowed_image_types=[t.strip() for t in paste_types_raw.split(",") if t.strip()],
            cors_origins=[o.strip() for o in cors_raw.split(",")],
            vlm_backend=os.environ.get("VLM_BACKEND", "ollama"),
            vlm_fallback_model=os.environ.get("VLM_FALLBACK_MODEL", "GRANITEDOCLING_TRANSFORMERS"),
            vlm_ollama_model=os.environ.get("VLM_OLLAMA_MODEL", "qwen3-vl:8b"),
            vlm_ollama_prompt=os.environ.get(
                "VLM_OLLAMA_PROMPT",
                (
                    """
                    Extract information from this page and return JSON format: { "Company Name1": "value1", "Address1": "value1", "Shipping Information1": "value1", "Good Description1": "value1" } Only these four sections allowed. Add numbered rows as needed. No duplication. Return all company first, then address, then shipping information, then good description. Extract all addresses, company names, shipping information, and goods descriptions from the document. Return only valid JSON.
                    """
                )
            ),
            vlm_ollama_markdown_prompt=os.environ.get(
                "VLM_OLLAMA_MARKDOWN_PROMPT",
                (
                    """
                    You are an OCR + document understanding engine. Read the page image carefully and transcribe its content as clean Markdown.

                    Rules:
                    - Preserve the document's structure: use `#`/`##`/`###` headings, bullet lists, numbered lists, and tables (as GFM tables) where the layout calls for them.
                    - Include every piece of readable text on the page — do not summarize, do not omit sections, do not skip headers, footers, page numbers, table cells, or annotations.
                    - If a region is unreadable or blank, output nothing for that region (do not guess).
                    - Output Markdown only. Do not wrap it in a code fence. Do not add commentary before or after.
                    """
                )
            ),
            vlm_ollama_max_tokens=int(os.environ.get("VLM_OLLAMA_MAX_TOKENS", "16384")),
            vlm_ollama_max_output_tokens=int(
                os.environ.get("VLM_OLLAMA_MAX_OUTPUT_TOKENS", "4096")
            ),
            vlm_remote_timeout=int(os.environ.get("VLM_REMOTE_TIMEOUT", "600")),
            # Comma-separated list of stop strings; empty by default — see
            # the field docstring for why we don't use `}` for JSON output.
            vlm_ollama_stop_sequences=tuple(
                s.strip()
                for s in os.environ.get("VLM_OLLAMA_STOP_SEQUENCES", "").split(",")
                if s.strip()
            ),
            vlm_ollama_response_char_cap=int(
                os.environ.get("VLM_OLLAMA_RESPONSE_CHAR_CAP", "32000")
            ),
            vlm_image_scale=float(os.environ.get("VLM_IMAGE_SCALE", "2.0")),
            # 0.6.1 — Surface flags (#257).
            studio_mode_enabled=os.environ.get("STUDIO_MODE_ENABLED", "false").lower()
            in ("1", "true", "yes", "on"),
            rag_pipeline_enabled=os.environ.get("RAG_PIPELINE_ENABLED", "true").lower()
            in ("1", "true", "yes", "on"),
            # 0.6.0 — RAG-pipeline sub-flags (#210, renamed in #257).
            inspect_mode_enabled=os.environ.get("INSPECT_MODE_ENABLED", "true").lower()
            in ("1", "true", "yes", "on"),
            linked_mode_enabled=os.environ.get("LINKED_MODE_ENABLED", "true").lower()
            in ("1", "true", "yes", "on"),
            ask_mode_enabled=os.environ.get("ASK_MODE_ENABLED", "true").lower()
            in ("1", "true", "yes", "on"),
        )


# Module-level singleton — import this from other modules.
settings = Settings.from_env()
