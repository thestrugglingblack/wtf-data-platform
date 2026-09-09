with team_season_stats as (

    select *
    from {{ ref('stg_team_season_stats') }}

),

teams as (

    select *
    from {{ ref('stg_teams') }}

),

standings as (

    select *
    from {{ ref('stg_standings') }}

),

enriched as (

    select
        ts.league,
        ts.season,
        ts.team_id,

        coalesce(
            t.team_name,
            ts.team_name
        ) as team_name,

        s.wins,
        s.losses,
        s.ties,
        s.win_pct,

        ts.* exclude (
            league,
            season,
            team_id,
            team_name
        ),

        s.* exclude (
            league,
            season,
            team_name,
            wins,
            losses,
            ties,
            win_pct
        )

    from team_season_stats ts

    left join teams t
        on ts.league = t.league
        and ts.season = t.season
        and ts.team_id = t.team_id

    left join standings s
        on ts.league = s.league
        and ts.season = s.season
        and lower(trim(ts.team_name))
            = lower(trim(s.team_name))

)

select *
from enriched