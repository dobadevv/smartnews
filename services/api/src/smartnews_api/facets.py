from collections.abc import Mapping
from dataclasses import dataclass

# Keys mirror the `category` values in config/fetcher.yaml; test_facets.py fails
# until a category added there gets a label here.
CATEGORY_LABELS: Mapping[str, str] = {
    "ai": "AI",
    "architecture": "Architecture",
    "cloud": "Cloud",
    "crypto": "Crypto",
    "data": "Data",
    "frontend": "Frontend",
    "observability": "Observability",
    "runtime": "Runtime",
    "stocks": "Stocks",
    "world": "World",
}

# Keys mirror every source `name` in config/fetcher.yaml, enabled or not;
# test_facets.py fails until a source added there gets a label here.
SOURCE_LABELS: Mapping[str, str] = {
    "aljazeera": "Al Jazeera",
    "aws-architecture-blog": "AWS Architecture Blog",
    "aws-whats-new": "AWS What's New",
    "azure-updates": "Azure Updates",
    "bbc-world": "BBC World",
    "bun-releases": "Bun Releases",
    "cafef-chung-khoan": "CafeF Stocks",
    "cloudflare-blog": "Cloudflare Blog",
    "cnbc-markets": "CNBC Markets",
    "coindesk": "CoinDesk",
    "cointelegraph": "Cointelegraph",
    "deno-releases": "Deno Releases",
    "elastic-blog": "Elastic Blog",
    "flutter-releases": "Flutter Releases",
    "gcp-release-notes": "Google Cloud Release Notes",
    "go-blog": "Go Blog",
    "google-deepmind": "Google DeepMind",
    "grafana-blog": "Grafana Blog",
    "guardian-world": "The Guardian World",
    "hacker-news": "Hacker News",
    "hn-ai": "Hacker News AI",
    "huggingface-blog": "Hugging Face Blog",
    "infoq": "InfoQ",
    "kafka-tags": "Apache Kafka Releases",
    "langchain-blog": "LangChain Blog",
    "latent-space": "Latent Space",
    "lobsters-ai": "Lobsters AI",
    "lobsters-distributed": "Lobsters Distributed",
    "loki-releases": "Loki Releases",
    "marketwatch": "MarketWatch",
    "mongodb-blog": "MongoDB Blog",
    "mysql-releases": "MySQL Releases",
    "nestjs-releases": "NestJS Releases",
    "nextjs-releases": "Next.js Releases",
    "nodejs-releases": "Node.js Releases",
    "openai-news": "OpenAI News",
    "postgresql-news": "PostgreSQL News",
    "prometheus-blog": "Prometheus Blog",
    "python-insider": "Python Insider",
    "rabbitmq-blog": "RabbitMQ Blog",
    "react-blog": "React Blog",
    "react-native-blog": "React Native Blog",
    "redis-blog": "Redis Blog",
    "spring-blog": "Spring Blog",
    "techcrunch-ai": "TechCrunch AI",
    "the-block": "The Block",
    "the-new-stack": "The New Stack",
    "typescript-blog": "TypeScript Blog",
    "verge-ai": "The Verge AI",
}


@dataclass(frozen=True)
class Facet:
    value: str
    label: str
    article_count: int


def build_facets(labels: Mapping[str, str], counts: Mapping[str, int]) -> list[Facet]:
    """Return one facet per labeled value, sorted by value; values without
    articles count 0 and counted values without a label are dropped."""
    return [
        Facet(value=value, label=labels[value], article_count=counts.get(value, 0))
        for value in sorted(labels)
    ]
