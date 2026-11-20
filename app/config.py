from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Настройки приложения, загружаемые из файла .env."""

    # Адрес Keitaro и API-ключ для доступа к его Admin API.
    keitaro_url: str
    keitaro_api_key: str

    # Адрес базы данных SQLite по умолчанию.
    database_url: str = "sqlite:///./adrobot.db"

    # ID объектов Keitaro, используемых по умолчанию при создании кампаний.
    default_domain_id: int = 1813
    default_group_id: int = 10332
    default_traffic_source_id: int = 836

    # Указываем Pydantic загружать настройки из файла .env.
    model_config = SettingsConfigDict(env_file=".env")


# Создаём единый объект настроек для использования во всём приложении.
settings = Settings()
