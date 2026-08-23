import time
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from dotenv import load_dotenv
from typing import Any, Optional

from config import BASE_URL

load_dotenv()  

class InvalidJSONResponseError(RuntimeError):
    def __init__(
        self,
        message: str,
        raw_text: str
    ):
        super().__init__(message)
        self.raw_text = raw_text

class Client:
    def __init__(
            self, 
            base_url: str = BASE_URL, 
            timeout: int = 30,
            delay: float = 0.25
        ):
        self.base_url = base_url
        self.timeout = timeout
        self.delay = delay
        self.session = requests.Session()
        
        retries = Retry(
            total=5, 
            backoff_factor=1, 
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["GET"]
            )

        adapter = HTTPAdapter(max_retries=retries)
        self.session.mount("https://", adapter)
        self.session.mount("http://", adapter)

    def _request(
            self, 
            uri: str, **params) -> Any:

        query ={
            "URI": uri,
            **params
        }
        response = self.session.get(
            self.base_url, 
            params=query, 
            timeout=self.timeout
        )
        response.raise_for_status()  # Raise an error for bad responses

        time.sleep(self.delay)  # Delay to avoid hitting rate limits
        if not response.content.strip():
            return []

        try:
            return response.json()
        except ValueError as error:
            text = response.text.strip()
            content_type = response.headers.get(
                "Content-Type",
                "unknown"
            )

            raise InvalidJSONResponseError(
                (
                    f"API returned invalid JSON for {uri} "
                    f"({content_type}) at {response.url}"
                ),
                raw_text=text
            ) from error

    def get_league_teams(
            self,
            league: str,
            season: int,
            tier: Optional[str] = None
    ):
        """
        Fetches teams for a specific league and season.

        Args:
            league (str): The league identifier (e.g., 'wfa', 'wnfc').
            season (int): The season year.
            tier (str, optional): The tier of the league. Defaults to None.
        """
        params = {
            "league": league,
            "season": season
        }
        if tier:
            params["tier"] = tier

        return self._request("getleagueTeamsList", **params)

    def get_league_current_season_schedule(
            self,
            league: str,
            season: int
    ):
        """
        Fetches the current season schedule for a specific league.

        Args:
            league (str): The league identifier (e.g., 'wfa', 'wnfc').
            season (int): The season year.
        """
        params = {
            "league": league,
            "season": season
        }

        return self._request("getcurrentSeasonSchedule", **params)

    def get_league_standings(
            self,
            league: str,
            season: int 
    ):
        """
        Fetches the standings for a specific league and season.

        Args:
            league (str): The league identifier (e.g., 'wfa', 'wnfc').
            season (int): The season year.
        """
        params = {
            "league": league,
            "season": season
        }

        return self._request("getLeagueStandings", **params)

    def get_team_roster(
            self,
            team_id: str,
            league: str,
            season: int
    ):
        """
        Fetches the roster for a specific team and season.

        Args:
            team_id (str): The unique identifier for the team.
            league (str): The league identifier.
            season (int): The season year.
        """
        params = {
            "team": team_id,
            "league": league,
            "season": season
        }

        return self._request("getTeamRoster", **params)

    def get_player_info(
            self,
            player_id: str,
            league: str,
            season: int
    ):
        """
        Fetches information for a specific player.

        Args:
            player_id (str): The unique identifier for the player.
            league (str): The league identifier.
            season (int): The season year.
        """
        params = {
            "UID": player_id,
            "league": league,
            "season": season
        }

        return self._request("getRosterInfo", **params)

    def get_player_stats(
            self,
            player_id: str,
            league: str,
            season: int
    ):
        """
        Fetches statistics for a specific player.

        Args:
            player_id (str): The unique identifier for the player.
            league (str): The league identifier.
            season (int): The season year.
        """
        params = {
            "UID": player_id,
            "league": league,
            "season": season
        }

        return self._request("getStatTotals", **params)

    def get_game_stats(
            self,
            game_id: str,
            season: int
    ):
        """
        Fetches statistics for a specific game.

        Args:
            game_id (str): The unique identifier for the game.
            season (int): The season year.
        """
        params = {
            "game_id": game_id,
            "season": season
        }

        return self._request("getGameStats", **params)

    def get_team_stats(
            self,
            league: str,
            season: int,
            tier:  Optional[str] = None
    ):
        """
        Fetches statistics for a specific team.

        Args:
            tier (str | None): The tier of the team.
            league (str): The league identifier.
            season (int): The season year.
        """
        params = {
            "league": league,
            "season": season
        }
        if tier:
            params["tier"] = tier

        return self._request("getTeamStats", **params)

    def get_offensive_stats(
            self,
            league: str,
            season: int,
            week:  Optional[int] = None,
            tier:  Optional[str] = None
    ):
        """
        Fetches offensive statistics for a specific league and season.

        Args:
            league (str): The league identifier.
            season (int): The season year.
            week (int | None): The week number. Defaults to None.
            tier (str | None): The tier of the league. Defaults to None.
        """
        params = {
            "league": league,
            "season": season
        }

        if tier:
            params["tier"] = tier

        if week is not None:
            params["week"] = week

        return self._request("getOffensiveStats", **params)

    def get_defensive_stats(
            self,
            league: str,
            season: int,
            week:  Optional[int] = None,
            tier:  Optional[str] = None,
    ):
        """
        Fetches defensive statistics for a specific league and season.

        Args:
            league (str): The league identifier.
            season (int): The season year.
            week (int | None): The week number. Defaults to None.
            tier (str | None): The tier of the league. Defaults to None.
        """
        params = {
            "league": league,
            "season": season
        }

        if tier:
            params["tier"] = tier

        if week:
            params["week"] = week

        return self._request("getDefensiveStats", **params)

    def get_special_teams_stats(
            self,
            league: str,
            season: int,
            week:  Optional[int] = None,
            tier:  Optional[str] = None,
    ):
        """
        Fetches special teams statistics for a specific league and season.

        Args:
            league (str): The league identifier.
            season (int): The season year.
            week (int | None): The week number. Defaults to None.
            tier (str | None): The tier of the league. Defaults to None.
        """
        params = {
            "league": league,
            "season": season
        }

        if tier:
            params["tier"] = tier

        if week:
            params["week"] = week

        return self._request("getSpecialTeamStats", **params)

    def get_scoring_stats(
            self,
            league: str,
            season: int,
            week:  Optional[int] = None,
            tier:  Optional[str] = None,
    ):
        """
        Fetches scoring statistics for a specific league and season.

        Args:
            league (str): The league identifier.
            season (int): The season year.
            week (int | None): The week number. Defaults to None.
            tier (str | None): The tier of the league. Defaults to None.
        """
        params = {
            "league": league,
            "season": season
        }

        if tier:
            params["tier"] = tier

        if week:
            params["week"] = week

        return self._request("getScoringStats", **params)

