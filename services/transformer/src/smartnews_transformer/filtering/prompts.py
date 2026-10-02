from smartnews_common.models import Article

# Keeps the prompt and the translated output within the model's token limits.
MAX_CONTENT_CHARS = 12000


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


def build_content_translation_prompt(content: str) -> str:
    return (
        "Translate the following article into Vietnamese as a concise "
        "rewrite that still covers all of its content.\n"
        "Condense it: drop repetition and minor detail, but keep every key "
        "fact, number, name and conclusion.\n"
        "Structure the text in three parts separated by a blank line: an "
        "introduction that states what the article is about, a body that "
        "covers the main points, and a conclusion that closes the article.\n"
        "Write in plain text only, using nothing but words, punctuation and "
        "line breaks. Do not use markdown, bullet points, numbering, "
        "headings, bold, quotes, emojis or other special characters, and do "
        "not label the three parts.\n"
        "Keep technical/industry terms (product names, programming "
        "languages, frameworks, protocols, acronyms such as API, LLM, SDK, "
        "AI) and proper names in their original English form; translate "
        "everything else naturally into Vietnamese.\n"
        "Respond with the Vietnamese text only, no preamble.\n\n"
        f"{content}"
    )
