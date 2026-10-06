"""Scratch script: read crawled content with a raw query and try translating it with Groq.

Usage:
    DATABASE_URL=postgresql://... GROQ_API_KEY=... \
        uv run --package smartnews-transformer python test.py [target_language]
"""

import os
import sys

import psycopg
from groq import Groq

MODEL = "openai/gpt-oss-120b"
MAX_CONTENT_CHARS = 4000
SELECT_LATEST_CONTENT = """
    SELECT article_id, content
    FROM article_contents
    ORDER BY crawled_at DESC
    LIMIT 1
"""


def normalize_database_url(url: str) -> str:
    return url.replace("postgresql+psycopg://", "postgresql://", 1)


def fetch_latest_content() -> tuple[int, str]:
    database_url = normalize_database_url(os.environ["DATABASE_URL"])
    with psycopg.connect(database_url) as connection:
        row = connection.execute(SELECT_LATEST_CONTENT).fetchone()
    if row is None:
        raise SystemExit("article_contents is empty: nothing to translate")
    return row


def translate(text: str, target_language: str) -> str:
    client = Groq(api_key=os.environ["GROQ_API_KEY"])
    response = client.chat.completions.create(
        model=MODEL,
        messages=[
            {
                "role": "system",
                "content": f"Translate the user's text into {target_language}. "
                "Return only the translation.",
            },
            {"role": "user", "content": text},
        ],
    )
    content = response.choices[0].message.content
    if content is None:
        raise SystemExit("groq returned no translation")
    return content


def main() -> None:
    target_language = sys.argv[1] if len(sys.argv) > 1 else "Vietnamese"
    article_id, content = fetch_latest_content()
    excerpt = content[:MAX_CONTENT_CHARS]

    print(f"article_id: {article_id}")
    print(f"--- original ({len(excerpt)}/{len(content)} chars) ---\n{excerpt}\n")
    print(f"--- {target_language} ---\n{translate(excerpt, target_language)}")


if __name__ == "__main__":
    main()
