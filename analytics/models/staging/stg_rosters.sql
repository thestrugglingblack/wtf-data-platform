select
    cast(league as varchar) as league,
    cast(season as bigint) as season,
    cast(team_id as varchar) as team_id,
    cast(team_name as varchar) as team_name,
    cast(player_id as varchar) as player_id,

    * exclude (
        league,
        season,
        team_id,
        team_name,
        player_id
    )

from {{ source('canonical', 'rosters') }}