"""Runtime configuration. Every external integration is behind a feature flag and
is disabled automatically when its credentials are absent."""
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Brand (never hard-code the product name in UI or documents)
    brand_name: str = "Renovara"
    brand_tagline: str = "AI renovation & sourcing tool"

    env: str = "development"
    secret_key: str = "dev-only-change-me"
    database_url: str = "sqlite:///./data/forma.db"
    storage_dir: Path = Path("./data/storage")
    public_base_url: str = "http://localhost:5173"
    api_base_url: str = "http://localhost:8000"
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"
    seed_demo: bool = True

    # Base currency of the MVP. Multi-currency is supported through exchange snapshots.
    base_currency: str = "AMD"

    # AI providers (provider abstraction; stub is used when no key is set)
    ai_default_provider: str = "auto"  # auto | openai | anthropic | gemini | stub
    openai_api_key: str | None = None
    openai_model: str = "gpt-5.5"
    openai_image_model: str = "gpt-image-2"
    anthropic_api_key: str | None = None
    anthropic_model: str = "claude-opus-5-5"
    gemini_api_key: str | None = None
    gemini_model: str = "gemini-3-flash-preview"
    ai_timeout_s: float = 120.0

    # Autodesk Platform Services
    aps_client_id: str | None = None
    aps_client_secret: str | None = None
    aps_base_url: str = "https://developer.api.autodesk.com"
    aps_bucket_key: str | None = None  # defaults to "<client_id lower>-forma"
    aps_region: str = "US"
    aps_da_nickname: str | None = None  # Design Automation nickname (defaults to client id)
    aps_da_activity_alias: str = "prod"
    aps_da_engine: str = "Autodesk.AutoCAD+25_0"

    # External catalog discovery
    external_catalog_enabled: bool = True
    external_fetch_user_agent: str = "RenovaraCatalogBot/0.1 (+https://cubeappmaker.agency/bot)"
    external_fetch_live: bool = False  # global opt-in; each source also needs live_enabled
    external_default_delay_s: float = 3.0
    external_fetch_timeout_s: float = 15.0
    external_fetch_max_retries: int = 2
    external_fetch_rate_limit_s: float = 3.0
    external_fetch_max_redirects: int = 3
    external_fetch_concurrency: int = 1
    external_fetch_max_bytes: int = 5_000_000
    external_cache_enabled: bool = True
    external_discovery_max_requests: int = 40  # live HTTP budget per discovery run
    external_robots_enforced: bool = True
    external_ssrf_protection: bool = True
    external_price_ttl_h: int = 24
    external_availability_ttl_h: int = 12
    external_specs_ttl_h: int = 24 * 7
    external_media_ttl_h: int = 24 * 30

    # Sessions & auth (P0-2): HttpOnly session cookie + double-submit CSRF cookie
    session_ttl_h: int = 24 * 14
    cookie_secure: bool = True  # browsers accept Secure cookies on http://localhost; set false only for plain-http test clients
    cookie_domain: str | None = None
    password_min_len: int = 10
    verify_token_ttl_h: int = 48
    reset_token_ttl_min: int = 60
    terms_version: str = "2026-10"

    # Rate limiting (in-memory per process; Redis when REDIS_URL is set)
    rate_limit_enabled: bool = True
    redis_url: str | None = None

    # E-mail: console (writes .eml files to MAIL_DIR, dev) | smtp
    mail_backend: str = "console"
    mail_dir: Path = Path("./data/mail")
    mail_from: str = "Renovara <no-reply@renovara.local>"
    smtp_host: str | None = None
    smtp_port: int = 587
    smtp_user: str | None = None
    smtp_password: str | None = None
    smtp_starttls: bool = True

    # Album
    album_font_path: str = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
    album_font_bold_path: str = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"

    @property
    def aps_enabled(self) -> bool:
        return bool(self.aps_client_id and self.aps_client_secret)

    @property
    def aps_bucket(self) -> str:
        if self.aps_bucket_key:
            return self.aps_bucket_key
        return f"{(self.aps_client_id or 'forma').lower()[:24]}-forma-projects"

    @property
    def is_production(self) -> bool:
        return self.env == "production"

    @property
    def cors_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    s = Settings()
    s.storage_dir.mkdir(parents=True, exist_ok=True)
    if s.database_url.startswith("sqlite:///"):
        Path(s.database_url.removeprefix("sqlite:///")).parent.mkdir(parents=True, exist_ok=True)
    return s
