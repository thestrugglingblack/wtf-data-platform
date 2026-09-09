with team_seasons as (

    select *
    from {{ ref('int_team_seasons') }}

),

team_games as (

    select
        league,
        season,
        team_name,

        count(
            distinct game_id
        ) as games_scheduled

    from {{ ref('int_team_games') }}

    group by
        league,
        season,
        team_name

),

final as (

    select
        ts.league,
        ts.season,

        ts.team_id,
        ts.team_name,

        tg.games_scheduled,

        ts.wins,
        ts.losses,
        ts.ties,
        ts.win_pct,

        ts.* exclude (
            league,
            season,
            team_id,
            team_name,
            wins,
            losses,
            ties,
            win_pct
        )

    from team_seasons ts

    left join team_games tg
        on ts.league = tg.league
        and ts.season = tg.season
        and lower(
            trim(ts.team_name)
        ) = lower(
            trim(tg.team_name)
        )

)

select *
from final