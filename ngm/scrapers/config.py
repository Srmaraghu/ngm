import os
import hashlib
from pathlib import Path
from dotenv import load_dotenv

CONCURRENT_REQUESTS = 2
DOWNLOAD_TIMEOUT = 600

load_dotenv()

FILES_STORE = os.getenv("FILES_STORE", Path("output"))

DEFAULT_SETTINGS = {
    "FILES_STORE": FILES_STORE,
    "CONCURRENT_REQUESTS": CONCURRENT_REQUESTS,
    "DOWNLOAD_TIMEOUT": 600,
    "USER_AGENT": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "MEDIA_ALLOW_REDIRECTS": True,
}

if os.getenv("AWS_ENDPOINT_URL"):
    DEFAULT_SETTINGS["AWS_ENDPOINT_URL"] = "https://4c96557d73194d4f245ba23bd6063ad5.r2.cloudflarestorage.com"
