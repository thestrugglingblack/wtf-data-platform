select
    cast(league as varchar) as league,
    cast(season as bigint) as season,
    cast(team_id as varchar) as team_id,
    cast(player_id as varchar) as player_id,
    cast(player_name as varchar) as player_name,
    cast(team_name as varchar) as team_name,

    * exclude (
        league,
        season,
        team_id,
        player_id,
        player_name,
        team_name
    )

from {{ source('canonical', 'player_season_stats') }}