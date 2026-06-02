from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Database
    database_url: str = "postgresql://postgres:password@localhost:5432/sea_dashboard"

    # External APIs
    newsapi_key: str = ""
    comtrade_subscription_key: str = ""

    # Anthropic
    anthropic_api_key: str = ""
    claude_model: str = "claude-haiku-4-5"

    # App
    debug: bool = False
    allowed_origins: list[str] = ["http://localhost:3000"]


settings = Settings()
