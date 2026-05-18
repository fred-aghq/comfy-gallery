from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "postgresql+asyncpg://gallery:gallery@db:5432/comfy_gallery"
    media_root: str = "/media"
    thumbnail_dir: str = "/thumbnails"
    thumbnail_size: int = 400
    items_per_page: int = 50
    cors_origins: list[str] = ["http://localhost:3000", "http://localhost:5173"]

    model_config = {"env_prefix": "GALLERY_"}


settings = Settings()
