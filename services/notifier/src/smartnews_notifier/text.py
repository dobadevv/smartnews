from html.parser import HTMLParser


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._chunks: list[str] = []

    def handle_data(self, data: str) -> None:
        self._chunks.append(data)

    def text(self) -> str:
        return " ".join(self._chunks)


def html_to_text(html: str | None) -> str | None:
    if html is None:
        return None
    extractor = _TextExtractor()
    extractor.feed(html)
    extractor.close()
    return " ".join(extractor.text().split())
