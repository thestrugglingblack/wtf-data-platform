with player_season_stats as (

    select *
    from {{ ref('stg_player_season_stats') }}

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
        ps.league,
        ps.season,
        ps.team_id,

        coalesce(
            t.team_name,
            ps.team_name
        ) as team_name,

        ps.player_id,

        coalesce(
            p.player_name,
            ps.player_name
        ) as player_name,

        case
            when p.player_id is not null then true
            else false
        end as has_canonical_player,

        ps.* exclude (
            league,
            season,
            team_id,
            team_name,
            player_id,
            player_name
        )

    from player_season_stats ps

    left join players p
        on ps.player_id = p.player_id

    left join teams t
        on ps.league = t.league
        and ps.season = t.season
        and ps.team_id = t.team_id

)

select *
from enriched