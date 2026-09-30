from smartnews_crawler.config import ContentSelectorOverride, CrawlerConfig
from smartnews_crawler.extraction.registry import ExtractorRegistry
from smartnews_crawler.extraction.selector_extractor import SelectorExtractor
from smartnews_crawler.extraction.trafilatura_extractor import TrafilaturaExtractor


def make_config() -> CrawlerConfig:
    return CrawlerConfig(
        overrides={"some-source": ContentSelectorOverride(content_selector="div.body")}
    )


def test_resolve_returns_trafilatura_for_a_source_without_an_override() -> None:
    registry = ExtractorRegistry(make_config())

    assert isinstance(registry.resolve("unknown-source"), TrafilaturaExtractor)
    assert registry.name_for("unknown-source") == "trafilatura"


def test_resolve_returns_the_selector_extractor_for_an_overridden_source() -> None:
    registry = ExtractorRegistry(make_config())

    extractor = registry.resolve("some-source")

    assert isinstance(extractor, SelectorExtractor)
    assert extractor._css_selector == "div.body"
    assert registry.name_for("some-source") == "selector:some-source"


def test_resolve_falls_back_to_trafilatura_when_there_are_no_overrides_at_all() -> None:
    registry = ExtractorRegistry(CrawlerConfig())

    assert isinstance(registry.resolve("any-source"), TrafilaturaExtractor)
