from __future__ import annotations

from functools import lru_cache
from typing import Self

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, PydanticBaseSettingsSource, SettingsConfigDict
from pydantic_settings.sources import TomlConfigSettingsSource

# Keep in sync with x402.http.constants.DEFAULT_FACILITATOR_URL (avoid importing x402 in config).
_DEFAULT_X402_FACILITATOR_URL = "https://x402.org/facilitator"

# Resolved from CWD; missing file is ignored. Env and .env override these values.
_CONF_TOML = "conf.toml"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="OMNIMISSION_",
        env_file=".env",
        extra="ignore",
        toml_file=_CONF_TOML,
    )

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        # Priority (highest first): init kwargs → OS env → .env → secrets → conf.toml → field defaults
        return (
            init_settings,
            env_settings,
            dotenv_settings,
            file_secret_settings,
            TomlConfigSettingsSource(settings_cls),
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

    # x402 pay-per-use ("ask"): when enabled, MCP HTTP routes require payment before access.
    x402_ask_enabled: bool = Field(
        default=False,
        description="Enable x402 HTTP 402 payment gate on /mcp (pay per use).",
    )
    x402_facilitator_url: str = Field(
        default=_DEFAULT_X402_FACILITATOR_URL,
        description="x402 facilitator HTTP base URL.",
    )
    x402_network: str = Field(
        default="eip155:84532",
        description="CAIP-2 network id for exact EVM settlement (e.g. Base Sepolia).",
    )
    x402_pay_to: str = Field(
        default="",
        description="EVM address that receives USDC for MCP access (required if ask is enabled).",
    )
    x402_price: str = Field(
        default="$0.01",
        description="Price per MCP session request (exact scheme string, e.g. $0.01).",
    )
    x402_resource_description: str = Field(
        default="OmniMission MCP access (plan_mission and related tools).",
        description="Human-readable resource line in Payment-Required payloads.",
    )

    @property
    def seed_urls(self) -> list[str]:
        return [u.strip() for u in self.crawler_seed_urls.split(",") if u.strip()]

    @model_validator(mode="after")
    def _validate_x402_ask(self) -> Self:
        if self.x402_ask_enabled and not (self.x402_pay_to or "").strip():
            msg = (
                "OMNIMISSION_X402_PAY_TO is required when OMNIMISSION_X402_ASK_ENABLED is true"
            )
            raise ValueError(msg)
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
