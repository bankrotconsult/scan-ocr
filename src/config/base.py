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

    SCAN_FILES_DIR = os.getenv("SCAN_FILES_DIR", "/home/rudich/scan-files")
