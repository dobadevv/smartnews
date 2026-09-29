from smartnews.models import Article


def build_translation_prompt(article: Article) -> str:
    return (
        "Translate the following tech article title and summary into "
        "Vietnamese.\n"
        "Rewrite the summary as a brief 1-2 sentence overview, not the full "
        "original text.\n"
        "Keep technical/industry terms (product names, programming "
        "languages, frameworks, protocols, acronyms such as API, LLM, SDK, "
        "AI) in their original English form; translate everything else "
        "naturally into Vietnamese.\n"
        "Respond with a JSON object with exactly two keys: "
        '"title" and "summary".\n\n'
        f"Title: {article.title}\n"
        f"Summary: {article.summary or ''}"
    )
