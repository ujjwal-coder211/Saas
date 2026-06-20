"""Load .env before app startup when using uvicorn directly."""

from dotenv import load_dotenv

load_dotenv()
