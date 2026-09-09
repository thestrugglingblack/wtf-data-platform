select
    cast(league as varchar) as league,
    cast(season as bigint) as season,
    cast(game_id as varchar) as game_id,
    cast(date as date) as date,
    cast(team_id as varchar) as team_id,
    cast(team_name as varchar) as team_name,
    cast(source_player_id as varchar) as source_player_id,
    cast(player_id as varchar) as player_id,
    cast(player_name as varchar) as player_name,

    * exclude (
        league,
        season,
        game_id,
        date,
        team_id,
        team_name,
        source_player_id,
        player_id,
        player_name
    )

from {{ source('canonical', 'player_game_stats') }}