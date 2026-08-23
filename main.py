from client import Client
from extract import (
    extract_league_season
)
from config import SEASONS

def main():
    client = Client()  # Initialize the API client

    for league, seasons in SEASONS.items():
        for season in seasons:
            print(f"Extracting data for {league} season {season}...")
            extract_league_season(client, league, season)  # Extract data for the league and season

if __name__ == "__main__":
    main()  # Run the main function when the script is executed 