select
    cast(league as varchar) as league,
    cast(season as bigint) as season,
    cast(game_id as varchar) as game_id,
    cast(season_type as varchar) as season_type,
    cast(week as bigint) as week,
    cast(date as date) as date,
    cast(visitor_team_name as varchar) as visitor_team_name,
    cast(home_team_name as varchar) as home_team_name,

    * exclude (
        league,
        season,
        game_id,
        season_type,
        week,
        date,
        visitor_team_name,
        home_team_name
    )

from {{ source('canonical', 'games') }}