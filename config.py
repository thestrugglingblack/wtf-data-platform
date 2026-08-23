import os
from pathlib import Path

from dotenv import load_dotenv
load_dotenv()  # Load environment variables from .env file

BASE_URL = os.getenv("HS_BASE_URL", "https://www.hostedsports.com/rest/")  # Default to the Hosted Sports API base URL if not set
DATA_DIR = Path(__file__).parent / "data"  # Directory to store data files
RAW_DATA_DIR = DATA_DIR / "raw"  # Directory for raw data files
PROCESSED_DATA_DIR = DATA_DIR / "processed"  # Directory for processed data files

LEAGUES= ['wfa', 'wnfc']

SEASONS = {
    # "wfa": [2023],
    "wnfc": [2024],
}