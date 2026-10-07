from collections.abc import Mapping
from pathlib import Path

import pytest
import yaml
from smartnews_api.facets import CATEGORY_LABELS, SOURCE_LABELS, Facet, build_facets

FETCHER_CONFIG = Path(__file__).parents[3] / "config/fetcher.yaml"


@pytest.mark.parametrize(
    ("labels", "counts", "expected"),
    [
        pytest.param(
            {"beta": "Beta", "alpha": "Alpha"},
            {"alpha": 3, "beta": 1},
            [Facet(value="alpha", label="Alpha", article_count=3), Facet(value="beta", label="Beta", article_count=1)],
            id="sorts by value regardless of insertion order",
        ),
        pytest.param(
            {"alpha": "Alpha", "beta": "Beta"},
            {"beta": 2},
            [Facet(value="alpha", label="Alpha", article_count=0), Facet(value="beta", label="Beta", article_count=2)],
            id="fills values without articles with zero",
        ),
        pytest.param(
            {"alpha": "Alpha"},
            {"alpha": 1, "unknown": 5},
            [Facet(value="alpha", label="Alpha", article_count=1)],
            id="drops counts for values without a label",
        ),
        pytest.param({}, {"alpha": 1}, [], id="returns nothing without labels"),
    ],
)
def test_build_facets_merges_labels_with_counts(
    labels: Mapping[str, str], counts: Mapping[str, int], expected: list[Facet]
) -> None:
    assert build_facets(labels=labels, counts=counts) == expected


def fetcher_sources() -> list[dict[str, object]]:
    return yaml.safe_load(FETCHER_CONFIG.read_text())["sources"]


def test_source_labels_cover_exactly_the_configured_sources() -> None:
    """Adding a source to config/fetcher.yaml requires a label in facets.py."""
    assert set(SOURCE_LABELS) == {source["name"] for source in fetcher_sources()}


def test_category_labels_cover_exactly_the_configured_categories() -> None:
    """Adding a category to config/fetcher.yaml requires a label in facets.py."""
    assert set(CATEGORY_LABELS) == {source["category"] for source in fetcher_sources()}


@pytest.mark.parametrize("labels", [CATEGORY_LABELS, SOURCE_LABELS], ids=["categories", "sources"])
def test_every_label_is_a_non_empty_string(labels: Mapping[str, str]) -> None:
    assert all(isinstance(label, str) and label.strip() for label in labels.values())
