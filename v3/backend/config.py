import os
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"))

SECRET_KEY = os.getenv("TALENT_SECRET_KEY", "talent-db-2026")
LLM_BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"
LLM_MODEL = os.getenv("TALENT_LLM_MODEL", "qwen-max")
LLM_API_KEY = os.getenv("TALENT_LLM_API_KEY", "")
LLM_MAX_CHARS = 25000

# Paths
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.expanduser(os.getenv("TALENT_DB_PATH", "~/projects/talent-db/data/talent.db"))
UPLOAD_DIR = os.path.expanduser(os.getenv("TALENT_UPLOAD_DIR", "~/projects/talent-db/input"))
