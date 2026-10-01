import logging

from google import genai
from google.genai import errors, types
from pydantic import BaseModel
from smartnews_common.models import Article, Transformation

from smartnews_transformation.filtering.base import TransformationError
from smartnews_transformation.filtering.prompts import build_translation_prompt

DEFAULT_API_BASE_URL = "https://generativelanguage.googleapis.com/"
DEFAULT_MODEL = "gemini-3.8-flash"
REQUEST_TIMEOUT_MILLISECONDS = 15_000

logger = logging.getLogger(__name__)


class _TranslatedArticle(BaseModel):
    title: str
    summary: str


class _GeminiModel:
    def __init__(
        self,
        api_key: str,
        model: str = DEFAULT_MODEL,
        api_base_url: str = DEFAULT_API_BASE_URL,
    ) -> None:
        self._model = model
        self._client = genai.Client(
            api_key=api_key,
            http_options=types.HttpOptions(
                base_url=api_base_url, timeout=REQUEST_TIMEOUT_MILLISECONDS
            ),
        )

    def _generate(
        self, prompt: str, **config_options
    ) -> types.GenerateContentResponse:
        # Automatic function calling is unused here and the SDK warns about it
        # on every request unless it is disabled.
        config = types.GenerateContentConfig(
            automatic_function_calling=types.AutomaticFunctionCallingConfig(
                disable=True
            ),
            **config_options,
        )
        try:
            return self._client.models.generate_content(
                model=self._model, contents=prompt, config=config
            )
        except errors.APIError as error:
            logger.error(
                "gemini request failed: status=%d response=%s",
                error.code,
                error.message,
            )
            raise


class GeminiFilter(_GeminiModel):
    def transform(self, article: Article) -> Transformation:
        try:
            translated = self._request(article)
        except Exception as error:
            raise TransformationError(
                f"gemini transformation failed for {article.url}"
            ) from error
        return Transformation(
            title=translated.title, summary=translated.summary, language="vi"
        )

    def _request(self, article: Article) -> _TranslatedArticle:
        response = self._generate(
            build_translation_prompt(article),
            response_mime_type="application/json",
            response_schema=_TranslatedArticle,
        )
        # The SDK leaves `parsed` as None when the prompt was blocked or the
        # text did not match the schema.
        if not isinstance(response.parsed, _TranslatedArticle):
            raise ValueError("gemini response did not contain a title and summary")
        return response.parsed
