import os
from google import genai
from dotenv import load_dotenv

load_dotenv(".env")

EMAIL = os.getenv("EMAIL", "")
APP_PASSWORD = os.getenv("APP_PASSWORD")
GEMINI_KEY = os.getenv("GEMINI_KEY")
MODEL = os.getenv("MODEL", "gemma-4-31b-it")
IMAP_SERVER = "imap.gmail.com"
SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 587
UNKNOWN_TOOLS_LOG = "unknown_tools.json"


def validate_env() -> list[str]:
    """Return list of missing required vars."""
    return [v for v in ("EMAIL", "APP_PASSWORD", "GEMINI_KEY") if not os.getenv(v)]


# Lazy client — initialized after setup
client = None


def ensure_client():
    global client
    if client is None:
        client = genai.Client(api_key=GEMINI_KEY)
    return client


# Shared mutable state — other modules write via config.mail = ..., etc.
mail: object = None
_chat: object = None
_current_user_message: str = ""
session_emails: dict = {}
