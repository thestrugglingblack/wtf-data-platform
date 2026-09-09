select
    cast(league as varchar) as league,
    cast(season as bigint) as season,
    cast(team_name as varchar) as team_name,
    cast(wins as bigint) as wins,
    cast(losses as bigint) as losses,
    cast(ties as bigint) as ties,
    cast(win_pct as double) as win_pct,

    * exclude (
        league,
        season,
        team_name,
        wins,
        losses,
        ties,
        win_pct
    )

from {{ source('canonical', 'standings') }}