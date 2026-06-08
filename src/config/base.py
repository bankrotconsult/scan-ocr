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
