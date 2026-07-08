from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    db_path: str = "livetel.db"
    ollama_url: str = "http://127.0.0.1:11434/api/generate"
    ollama_model: str = "phi3:mini"
    metrics_window_seconds: int = 60
    metrics_history_minutes: int = 60
    metrics_history_bucket_minutes: int = 1
    prune_hours: int = 24
    ai_alert_cooldown_seconds: int = 120
    use_template_ai: bool = False
    enable_api_docs: bool = True
    read_only_demo: bool = False
    alert_windows_cache_seconds: int = 30


settings = Settings()
