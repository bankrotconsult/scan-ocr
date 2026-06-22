import os

from dotenv import load_dotenv

load_dotenv()


class BaseConfig:
    # app
    SECRET_KEY = os.getenv("SECRET_KEY")

    # database
    DATABASE_URL = os.getenv("DATABASE_URL")

    SYNC_DATABASE_URL = os.getenv("SYNC_DATABASE_URL")

    DEBUG = os.getenv("DEBUG", True)

    UPLOADS_DIR = os.getenv("UPLOADS_DIR", "./uploads")

    SCAN_FILES_DIR = os.getenv("SCAN_FILES_DIR", "/home/rudich/scan-files/test")

    OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")

    OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen2.5:7b")

    # Windows UNC path to the root scan directory (e.g. \\SERVER\scan-files\test)
    # Used to build clickable folder links in the web UI
    SCAN_FILES_SHARE_URL: str = os.getenv("SCAN_FILES_SHARE_URL", "")

    # Google Sheets integration
    GOOGLE_SHEETS_ID: str = os.getenv("GOOGLE_SHEETS_ID", "")
    GOOGLE_CREDENTIALS_PATH: str = os.getenv("GOOGLE_CREDENTIALS_PATH", "/app/credentials.json")
    # Directory for JSON caches; defaults to .sheet_cache inside SCAN_FILES_DIR
    SHEET_CACHE_DIR: str = os.getenv("SHEET_CACHE_DIR", "")
