"""Tests for the Deep-Extract helpers (merge_extractions, parse_ask_response).

Covers the new code path that powers the `extract_mode="deep"` option in
`POST /api/analyses` (see extracted-json/merged__SHIPPED_REPORT.md for the
scoring rationale).
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from api.chat import parse_ask_response
from domain.services import (
    _dedup_exact_only,
    _normalise_for_dedup,
    merge_extractions,
)
from domain.value_objects import ConversionOptions, ConversionResult, PageDetail
from services.analysis_service import AnalysisService

# ---------------------------------------------------------------------------
# merge_extractions
# ---------------------------------------------------------------------------


class TestMergeExtractions:
    def test_empty_inputs_return_none(self):
        assert merge_extractions(None) is None
        assert merge_extractions(None, None) is None
        assert merge_extractions("", "  ") is None

    def test_single_input_passthrough(self):
        out = merge_extractions('{"Company Name1": "ACME"}')
        assert json.loads(out) == {"Company Name1": "ACME"}

    def test_substring_kept_as_separate_entry(self):
        # v2 (2026-06-13): substring variants are kept as separate
        # entries. Losing one is worse than keeping a near-duplicate.
        out = merge_extractions(
            '{"Company Name1": "FLUID LIMITED"}',
            '{"Company Name1": "FLUID LIMITED CO"}',
        )
        parsed = json.loads(out)
        # Both preserved in first-seen order.
        assert parsed == {
            "Company Name1": "FLUID LIMITED",
            "Company Name2": "FLUID LIMITED CO",
        }

    def test_substring_kept_regardless_of_order(self):
        # Order doesn't matter — both substring variants survive.
        out = merge_extractions(
            '{"Company Name1": "FLUID LIMITED CO"}',
            '{"Company Name1": "FLUID LIMITED"}',
        )
        parsed = json.loads(out)
        assert parsed == {
            "Company Name1": "FLUID LIMITED CO",
            "Company Name2": "FLUID LIMITED",
        }

    def test_different_values_kept_separate(self):
        out = merge_extractions(
            '{"Company Name1": "FLUID LIMITED"}',
            '{"Company Name1": "OTHER CO"}',
        )
        parsed = json.loads(out)
        assert parsed == {
            "Company Name1": "FLUID LIMITED",
            "Company Name2": "OTHER CO",
        }

    def test_union_across_sections(self):
        out = merge_extractions(
            '{"Company Name1": "FLUID LIMITED", "Address1": "A1"}',
            '{"Address2": "A2", "Goods Description1": "WIDGETS"}',
        )
        parsed = json.loads(out)
        assert parsed == {
            "Company Name1": "FLUID LIMITED",
            "Address1": "A1",
            "Address2": "A2",
            "Goods Description1": "WIDGETS",
        }

    def test_exact_duplicates_dedup(self):
        out = merge_extractions(
            '{"Company Name1": "FLUID LIMITED"}',
            '{"Company Name1": "FLUID LIMITED"}',
        )
        parsed = json.loads(out)
        assert parsed == {"Company Name1": "FLUID LIMITED"}

    def test_whitespace_normalisation(self):
        out = merge_extractions(
            '{"Company Name1": "FLUID  LIMITED"}',
            '{"Company Name1": "FLUID LIMITED"}',
        )
        parsed = json.loads(out)
        # Both normalise to the same string; only one survives.
        assert len(parsed) == 1
        assert parsed["Company Name1"].replace("  ", " ") == "FLUID LIMITED"

    def test_case_insensitive_kept_separate(self):
        """v2 (loose dedup): casing variants are NOT considered duplicates.

        The merge is a preserve, not a normalise — a user who wants to
        inspect the OCR'd form ("FLUID LIMITED CO") and the title-cased
        form ("Fluid Limited") independently can pick whichever
        matches the golden.
        """
        out = merge_extractions(
            '{"Company Name1": "Fluid Limited"}',
            '{"Company Name2": "FLUID LIMITED CO"}',
        )
        parsed = json.loads(out)
        assert parsed == {"Company Name1": "Fluid Limited", "Company Name2": "FLUID LIMITED CO"}

    def test_malformed_input_skipped(self):
        out = merge_extractions(
            "{not json",
            '{"Company Name1": "X"}',
        )
        parsed = json.loads(out)
        assert parsed == {"Company Name1": "X"}

    def test_non_dict_input_skipped(self):
        out = merge_extractions(
            '["Company Name1", "X"]',  # array, not dict
            '{"Company Name1": "X"}',
        )
        parsed = json.loads(out)
        assert parsed == {"Company Name1": "X"}

    def test_three_inputs(self):
        """v2 (loose dedup): three prefix variants are all preserved,
        not collapsed to the longest.
        """
        out = merge_extractions(
            '{"Company Name1": "A"}',
            '{"Company Name2": "AB"}',
            '{"Company Name3": "ABC"}',
        )
        parsed = json.loads(out)
        assert parsed == {"Company Name1": "A", "Company Name2": "AB", "Company Name3": "ABC"}

    def test_longest_prefix_first_matching(self):
        # "Shipping Information" must not be bucketed under "Address" or
        # any shorter prefix — defensive against the section overlap bug.
        out = merge_extractions(
            '{"Address1": "X", "Shipping Information1": "From: HK"}',
            '{"Goods Description1": "WIDGETS"}',
        )
        parsed = json.loads(out)
        assert "Shipping Information1" in parsed
        assert "Goods Description1" in parsed


# ---------------------------------------------------------------------------
# parse_ask_response
# ---------------------------------------------------------------------------


class TestParseAskResponse:
    def test_empty_returns_none(self):
        assert parse_ask_response("") is None
        assert parse_ask_response("   ") is None

    def test_well_formed_object_passthrough(self):
        raw = '{"Company Name1": "FLUID LIMITED", "Address1": "Tokyo"}'
        out = parse_ask_response(raw)
        parsed = json.loads(out)
        assert parsed == {"Company Name1": "FLUID LIMITED", "Address1": "Tokyo"}

    def test_brace_less_colon_separator(self):
        raw = (
            '"Company Name1": "FLUID LIMITED",\n'
            '"Address1": "Tokyo",\n'
            '"Address2": "Yokohama",\n'
        )
        out = parse_ask_response(raw)
        parsed = json.loads(out)
        assert parsed["Company Name1"] == "FLUID LIMITED"
        assert parsed["Address1"] == "Tokyo"
        assert parsed["Address2"] == "Yokohama"

    def test_equals_separator(self):
        raw = (
            '"Company Name1" = "FLUID LIMITED",\n'
            '"Address1" = "Tokyo",\n'
        )
        out = parse_ask_response(raw)
        parsed = json.loads(out)
        assert parsed["Company Name1"] == "FLUID LIMITED"
        assert parsed["Address1"] == "Tokyo"

    def test_colon_equals_separator(self):
        # gemma4 sometimes emits `":="` instead of `":"`.
        raw = (
            '"Company Name1":="FLUID LIMITED",\n'
            '"Address1":="Tokyo",\n'
        )
        out = parse_ask_response(raw)
        parsed = json.loads(out)
        assert parsed["Company Name1"] == "FLUID LIMITED"
        assert parsed["Address1"] == "Tokyo"

    def test_angle_bracket_suffix(self):
        # "Company Name<1>" must be normalised to "Company Name1".
        raw = (
            '"Company Name<1>": "FLUID LIMITED",\n'
            '"Address<1>": "Tokyo",\n'
        )
        out = parse_ask_response(raw)
        parsed = json.loads(out)
        assert parsed["Company Name1"] == "FLUID LIMITED"
        assert parsed["Address1"] == "Tokyo"

    def test_code_fence_stripped(self):
        raw = (
            "```json\n"
            '{"Company Name1": "FLUID LIMITED"}\n'
            "```"
        )
        out = parse_ask_response(raw)
        parsed = json.loads(out)
        assert parsed == {"Company Name1": "FLUID LIMITED"}

    def test_preamble_stripped(self):
        raw = (
            "Here is the JSON object:\n"
            '{"Company Name1": "FLUID LIMITED"}'
        )
        out = parse_ask_response(raw)
        parsed = json.loads(out)
        assert parsed == {"Company Name1": "FLUID LIMITED"}

    def test_dict_value_flattened_to_string(self):
        """Gemma 4 sometimes emits a value as a Python-dict literal
        instead of a flat string. The sanitizer must flatten it to a
        `key: value` string so the merge contract holds."""
        raw = (
            '{"Company Name1":"Thomas Miller",'
            '"Shipping Information1":{"To": "CHINA"}}'
        )
        out = parse_ask_response(raw)
        parsed = json.loads(out)
        assert parsed == {
            "Company Name1": "Thomas Miller",
            "Shipping Information1": "To: CHINA",
        }
        # Every value is a plain string (not a dict / list).
        for v in parsed.values():
            assert isinstance(v, str), f"non-string value: {v!r}"

    def test_nested_section_dict_promoted_to_top_level_keys(self):
        """Gemma 4 sometimes wraps a section in an outer key — e.g.
        ``{"Company Name": {"Company Name1": "A", "Company Name2": "B"}}``.
        The sanitizer must promote the inner entries to TOP-LEVEL keys,
        not concatenate them into a single ``Company Name1`` value (the
        pre-fix behaviour, which corrupted the merge contract).

        Regression from 2026-06-18: VLM-direct runaway-defense fix made
        VLM fail to parse, exposing this latent Ask bug because the
        merged result fell back to the Ask JSON.
        """
        raw = (
            '{"Company Name":'
            '{"Company Name1": "BANQUE POPULAIRE ATLANTIQUE",'
            '"Company Name2": "DBS BANK (HONG KONG) LIMITED",'
            '"Company Name3": "SNC ONE SAS"},'
            '"Address":'
            '{"Address1": "194 RUE CHOLETAISE EN MAUGES FRANCE",'
            '"Address2": "10/F DA DA INDUSTRIAL BUIDLING HONG KONG"}}'
        )
        out = parse_ask_response(raw)
        parsed = json.loads(out)
        # Inner entries are promoted to top-level keys, NOT concatenated.
        assert parsed == {
            "Company Name1": "BANQUE POPULAIRE ATLANTIQUE",
            "Company Name2": "DBS BANK (HONG KONG) LIMITED",
            "Company Name3": "SNC ONE SAS",
            "Address1": "194 RUE CHOLETAISE EN MAUGES FRANCE",
            "Address2": "10/F DA DA INDUSTRIAL BUIDLING HONG KONG",
        }
        # The outer section key MUST NOT survive — otherwise the merge
        # would bucket its value into Company Name1 (single-key collapse).
        assert "Company Name" not in parsed
        assert "Address" not in parsed
        for v in parsed.values():
            assert isinstance(v, str), f"non-string value: {v!r}"

    def test_nested_dict_with_single_inner_key_still_concatenates(self):
        """Edge case: if the inner dict has only ONE key matching the
        section prefix, the original single-value-dict behaviour applies
        (the dict is most likely a single-value quirk like
        ``{"To": "CHINA"}``, not a section wrapper — but here it has the
        outer key as prefix, so we still treat it as section-level).

        Documenting this so the two branches don't diverge silently if
        someone refactors the heuristic later.
        """
        raw = (
            '{"Company Name":'
            '{"Company Name1": "ONLY ENTRY"}}'
        )
        out = parse_ask_response(raw)
        parsed = json.loads(out)
        # Single-entry section is still promoted to a top-level key.
        assert parsed == {"Company Name1": "ONLY ENTRY"}

    def test_unrelated_dict_value_still_uses_semicolon_format(self):
        """Sanity: an inner dict whose keys DON'T share the outer-key
        prefix (i.e. the gemma4 single-value-dict quirk ``{"To": "CHINA"}``)
        must keep using the `;`-joined string format."""
        raw = (
            '{"Shipping Information1":'
            '{"From": "HONG KONG", "To": "LE HAVRE"}}'
        )
        out = parse_ask_response(raw)
        parsed = json.loads(out)
        assert parsed == {
            "Shipping Information1": "From: HONG KONG; To: LE HAVRE",
        }


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


class TestNormaliseForDedup:
    def test_lowercases(self):
        assert _normalise_for_dedup("FLUID Limited") == "fluid limited"

    def test_collapses_whitespace(self):
        assert _normalise_for_dedup("  FLUID   LIMITED  ") == "fluid limited"


class TestDedupExactOnly:
    def test_empty_list(self):
        assert _dedup_exact_only([]) == []

    def test_empty_strings_filtered(self):
        assert _dedup_exact_only(["", "  ", "X"]) == ["X"]

    def test_substring_kept(self):
        # v2 (2026-06-13): substring variants are NOT considered duplicates.
        # Both survive.
        out = _dedup_exact_only(["FLUID LIMITED", "FLUID LIMITED CO"])
        assert out == ["FLUID LIMITED", "FLUID LIMITED CO"]

    def test_different_kept(self):
        out = _dedup_exact_only(["A", "B", "C"])
        assert out == ["A", "B", "C"]

    def test_exact_dup_filtered(self):
        out = _dedup_exact_only(["A", "A", "B"])
        assert out == ["A", "B"]

    def test_case_insensitive_exact_dedup(self):
        out = _dedup_exact_only(["FLUID Limited", "fluid limited"])
        assert out == ["FLUID Limited"]

    def test_whitespace_normalised_exact_dedup(self):
        out = _dedup_exact_only(["FLUID  LIMITED", "FLUID LIMITED"])
        assert out == ["FLUID  LIMITED"]

    def test_first_seen_order_preserved(self):
        out = _dedup_exact_only(["A", "B", "C"])
        assert out == ["A", "B", "C"]


# ---------------------------------------------------------------------------
# Schema / value object plumbing
# ---------------------------------------------------------------------------


class TestExtractModeWiring:
    def test_conversion_options_default_is_standard(self):
        assert ConversionOptions().extract_mode == "standard"

    def test_conversion_options_accepts_deep(self):
        assert ConversionOptions(extract_mode="deep").extract_mode == "deep"


# ---------------------------------------------------------------------------
# _run_deep_extract — orchestration
# ---------------------------------------------------------------------------


def _make_deep_service(
    std_result: ConversionResult, vlm_result: ConversionResult
) -> AnalysisService:
    """Build a service that returns `std_result` for the standard run and
    `vlm_result` for the VLM-json run, and a mock analysis repo."""
    converter = MagicMock()
    converter.supports_page_batching = False
    # The first call is the standard run; the second is the VLM run.
    converter.convert = AsyncMock(side_effect=[std_result, vlm_result])
    repo = MagicMock()
    repo.find_by_id = AsyncMock(
        return_value=MagicMock(document_id="d1", document_filename="test.pdf")
    )
    repo.update_progress = AsyncMock()
    doc_repo = MagicMock()
    return AnalysisService(converter=converter, analysis_repo=repo, document_repo=doc_repo)


class TestRunDeepExtract:
    @pytest.mark.asyncio
    async def test_runs_standard_and_vlm_in_order(self):
        std_md = "STANDARD MARKDOWN"
        std_result = ConversionResult(
            page_count=1,
            content_markdown=std_md,
            content_html="",
            pages=[PageDetail(page_number=1, width=612, height=792)],
            document_json='{"origin": "standard"}',
        )
        vlm_result = ConversionResult(
            page_count=1,
            content_markdown="",
            content_html="",
            pages=[],
            content_json='{"Company Name1": "VLM CO"}',
        )
        svc = _make_deep_service(std_result, vlm_result)

        with patch(
            "services.analysis_service.run_ask_extraction",
            new=AsyncMock(return_value='{"Company Name1": "ASK CO"}'),
        ):
            result = await svc._run_deep_extract(
                "j1", "/tmp/test.pdf", "test.pdf", ConversionOptions(extract_mode="deep")
            )

        # Both converter calls happened, in order
        assert svc._converter.convert.await_count == 2
        # The first call gets a standard options (force_vlm_pipeline=False)
        first_opts = svc._converter.convert.call_args_list[0][0][1]
        assert first_opts.force_vlm_pipeline is False
        # The second gets a VLM-json options
        second_opts = svc._converter.convert.call_args_list[1][0][1]
        assert second_opts.force_vlm_pipeline is True
        assert second_opts.vlm_output_mode == "json"

        # The merged result uses the standard's markdown/html
        assert result is not None
        assert result.content_markdown == std_md
        # And the merged content_json is the union. ASK is passed first
        # to merge_extractions, so it claims slot 1; VLM takes the
        # next available slot.
        parsed = json.loads(result.content_json)
        assert parsed == {"Company Name1": "ASK CO", "Company Name2": "VLM CO"}

    @pytest.mark.asyncio
    async def test_ask_failure_is_non_fatal(self):
        """If the Ask step fails, the VLM-json extraction still wins."""
        std_result = ConversionResult(
            page_count=1,
            content_markdown="STANDARD MARKDOWN",
            content_html="",
            pages=[PageDetail(page_number=1, width=612, height=792)],
        )
        vlm_result = ConversionResult(
            page_count=1,
            content_markdown="",
            content_html="",
            pages=[],
            content_json='{"Company Name1": "VLM CO"}',
        )
        svc = _make_deep_service(std_result, vlm_result)

        with patch(
            "services.analysis_service.run_ask_extraction",
            new=AsyncMock(return_value=None),  # Ask step unreachable
        ):
            result = await svc._run_deep_extract(
                "j1", "/tmp/test.pdf", "test.pdf", ConversionOptions(extract_mode="deep")
            )

        assert result is not None
        parsed = json.loads(result.content_json)
        assert parsed == {"Company Name1": "VLM CO"}

    @pytest.mark.asyncio
    async def test_vlm_failure_is_non_fatal(self):
        """If the VLM run returns no content_json, the Ask JSON is used."""
        std_result = ConversionResult(
            page_count=1,
            content_markdown="STANDARD MARKDOWN",
            content_html="",
            pages=[PageDetail(page_number=1, width=612, height=792)],
        )
        vlm_result = ConversionResult(
            page_count=1,
            content_markdown="",
            content_html="",
            pages=[],
            content_json=None,
        )
        svc = _make_deep_service(std_result, vlm_result)

        with patch(
            "services.analysis_service.run_ask_extraction",
            new=AsyncMock(return_value='{"Company Name1": "ASK CO"}'),
        ):
            result = await svc._run_deep_extract(
                "j1", "/tmp/test.pdf", "test.pdf", ConversionOptions(extract_mode="deep")
            )

        assert result is not None
        parsed = json.loads(result.content_json)
        assert parsed == {"Company Name1": "ASK CO"}

    @pytest.mark.asyncio
    async def test_returns_none_when_job_already_deleted(self):
        """If the job is gone before the deep-extract starts, return None."""
        std_result = ConversionResult(
            page_count=1,
            content_markdown="x",
            content_html="",
            pages=[PageDetail(page_number=1, width=612, height=792)],
        )
        svc = _make_deep_service(std_result, std_result)
        svc._analysis_repo.find_by_id = AsyncMock(return_value=None)

        with patch(
            "services.analysis_service.run_ask_extraction",
            new=AsyncMock(return_value=None),
        ):
            result = await svc._run_deep_extract(
                "j1", "/tmp/test.pdf", "test.pdf", ConversionOptions(extract_mode="deep")
            )
        assert result is None
        # Standard conversion was NOT triggered — we bailed before
        # spending the time on it.
        assert svc._converter.convert.await_count == 0
