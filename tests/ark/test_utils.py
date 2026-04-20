"""Tests for ark/utils.py."""

import pytest

from ark.utils import (
    BETANUMERIC,
    gen_prefixes,
    generate_noid,
    noid_check_digit,
    parse_ark,
    parse_ark_lookup,
)


class TestGenerateNoid:
    def test_length(self):
        for length in [4, 8, 12]:
            assert len(generate_noid(length)) == length

    def test_only_betanumeric(self):
        noid = generate_noid(100)
        assert all(c in BETANUMERIC for c in noid)

    def test_randomness(self):
        assert generate_noid(8) != generate_noid(8)


class TestNoidCheckDigit:
    def test_returns_betanumeric_char(self):
        digit = noid_check_digit("12345678")
        assert digit in BETANUMERIC

    def test_deterministic(self):
        assert noid_check_digit("12345678") == noid_check_digit("12345678")

    def test_different_inputs_may_differ(self):
        digits = {noid_check_digit(f"1234567{c}") for c in "bcdf"}
        assert len(digits) > 1


class TestParseArk:
    def test_valid_ark(self):
        nma, naan, identifier = parse_ark("ark:/12345/abc123")
        assert nma == ""
        assert naan == 12345
        assert identifier == "abc123"

    def test_valid_ark_with_nma(self):
        nma, naan, identifier = parse_ark("https://example.comark:/12345/abc123")
        assert "example.com" in nma

    def test_nested_identifier(self):
        _, naan, identifier = parse_ark("ark:/12345/abc/def")
        assert identifier == "abc/def"

    def test_missing_ark_prefix_raises(self):
        with pytest.raises(ValueError):
            parse_ark("12345/abc123")

    def test_missing_identifier_raises(self):
        with pytest.raises(ValueError):
            parse_ark("ark:/12345")

    def test_non_integer_naan_raises(self):
        with pytest.raises(ValueError, match="NAAN must be an integer"):
            parse_ark("ark:/notanint/abc")


class TestParseArkLookup:
    def test_returns_naan_slash_identifier(self):
        result = parse_ark_lookup("ark:/12345/abc123")
        assert result == "12345/abc123"


class TestGenPrefixes:
    def test_single_part(self):
        assert list(gen_prefixes("abc")) == []

    def test_two_parts(self):
        assert list(gen_prefixes("abc/def")) == ["abc"]

    def test_three_parts(self):
        assert list(gen_prefixes("a/b/c")) == ["a/b", "a"]
