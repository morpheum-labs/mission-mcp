from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="OMNIMISSION_",
        env_file=".env",
        extra="ignore",
    )

    chroma_host: str = "localhost"
    chroma_port: int = 8000
    collection_name: str = "skills_mcp"
    embed_model: str = "sentence-transformers/all-MiniLM-L6-v2"
    top_k: int = 12
    fetch_n: int = 24
    crawler_interval_minutes: int = 15
    crawler_seed_urls: str = Field(
        default="https://example.com",
        description="Comma-separated seed URLs for the crawler.",
    )

    @property
    def seed_urls(self) -> list[str]:
        return [u.strip() for u in self.crawler_seed_urls.split(",") if u.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
