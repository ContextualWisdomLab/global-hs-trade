"""Source provenance URLs must not persist credentials or fragments."""

from __future__ import annotations

import pytest

from tests.helpers import mod, row


@pytest.mark.parametrize(
    "source_url",
    [
        "https://analyst:secret@example.org/trade/1",
        "https://example.org/trade/1#private-fragment",
        "https:///trade/1",
        "https://example.org:invalid/trade/1",
    ],
)
def test_observation_source_url_rejects_unsafe_authority(source_url: str) -> None:
    """Credentials, fragments, missing hosts and invalid ports fail provenance admission."""
    with pytest.raises(ValueError, match="source_url"):
        mod("trade.model").normalize_observation(row(source_url=source_url))


def test_observation_source_url_keeps_safe_https_query() -> None:
    """A normal HTTPS provenance URL may retain a bounded source query."""
    source_url = "https://example.org/trade/1?record=abc%20123"
    result = mod("trade.model").normalize_observation(row(source_url=source_url))
    assert result["source_url"] == source_url
