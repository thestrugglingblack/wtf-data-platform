select
    league,
    season,
    season_type,
    week,
    date,
    game_id,

    team_id,
    team_name,
    opponent_team_name,
    game_location,

    home_team_name,
    visitor_team_name,

    player_id,
    source_player_id,
    player_name,
    has_canonical_player,

    * exclude (
        league,
        season,
        season_type,
        week,
        date,
        game_id,
        team_id,
        team_name,
        opponent_team_name,
        game_location,
        home_team_name,
        visitor_team_name,
        player_id,
        source_player_id,
        player_name,
        has_canonical_player
    )

from {{ ref('int_player_games') }}