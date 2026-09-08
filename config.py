import os
from pathlib import Path

from dotenv import load_dotenv
load_dotenv()  # Load environment variables from .env file

BASE_URL = os.getenv("HS_BASE_URL", "https://www.hostedsports.com/rest/")  # Default to the Hosted Sports API base URL if not set
DATA_DIR = Path(__file__).parent / "data"  # Directory to store data files
RAW_DATA_DIR = DATA_DIR / "raw"  # Directory for raw data files
PROCESSED_DATA_DIR = DATA_DIR / "processed"  # Directory for processed data files

# Data Product Paths
# Example:
#
# data/releases/
#     v0.1.0/
#     v0.2.0/
RELEASES_DATA_DIR = DATA_DIR / "releases"
LATEST_RELEASE_FILE = RELEASES_DATA_DIR / "latest.json"


LEAGUES= ['wfa', 'wnfc']
SEASONS = {
    "wfa": [2009, 2010, 2011, 2012, 2013, 2014, 2017, 2018, 2019, 2020, 2021, 2022, 2023, 2024, 2025, 2026], # [2020, 2021, 2022, 2023, 2024, 2025, 2026] 2009, 2010, 2011, 2012, 2013, 2014, 2017, 2018, 2019
    "wnfc": [2019, 2020, 2021, 2022, 2023, 2024, 2025, 2026], #[2019, 2020, 2021, 2022, 2023, 2024, 2025, 2026]
}