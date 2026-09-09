with player_game_stats as (

    select *
    from {{ ref('stg_player_game_stats') }}

),

games as (

    select *
    from {{ ref('stg_games') }}

),

players as (

    select *
    from {{ ref('stg_players') }}

),

teams as (

    select *
    from {{ ref('stg_teams') }}

),

enriched as (

    select
        pg.league,
        pg.season,
        pg.game_id,

        g.season_type,
        g.week,

        coalesce(
            g.date,
            pg.date
        ) as date,

        pg.team_id,

        coalesce(
            t.team_name,
            pg.team_name
        ) as team_name,

        case
            when lower(trim(pg.team_name))
                = lower(trim(g.home_team_name))
                then 'home'

            when lower(trim(pg.team_name))
                = lower(trim(g.visitor_team_name))
                then 'away'

            else null
        end as game_location,

        case
            when lower(trim(pg.team_name))
                = lower(trim(g.home_team_name))
                then g.visitor_team_name

            when lower(trim(pg.team_name))
                = lower(trim(g.visitor_team_name))
                then g.home_team_name

            else null
        end as opponent_team_name,

        g.home_team_name,
        g.visitor_team_name,

        pg.source_player_id,
        pg.player_id,

        coalesce(
            p.player_name,
            pg.player_name
        ) as player_name,

        case
            when p.player_id is not null then true
            else false
        end as has_canonical_player,

        pg.* exclude (
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

    from player_game_stats pg

    left join games g
        on pg.league = g.league
        and pg.season = g.season
        and pg.game_id = g.game_id

    left join players p
        on pg.player_id = p.player_id

    left join teams t
        on pg.league = t.league
        and pg.season = t.season
        and pg.team_id = t.team_id

)

select *
from enriched