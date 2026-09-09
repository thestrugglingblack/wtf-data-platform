with rosters as (

    select *
    from {{ ref('stg_rosters') }}

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
        r.league,
        r.season,
        r.team_id,

        coalesce(
            t.team_name,
            r.team_name
        ) as team_name,

        r.player_id,

        p.player_name as canonical_player_name,

        case
            when p.player_id is not null then true
            else false
        end as has_canonical_player,

        r.* exclude (
            league,
            season,
            team_id,
            team_name,
            player_id
        )

    from rosters r

    left join players p
        on r.player_id = p.player_id

    left join teams t
        on r.league = t.league
        and r.season = t.season
        and r.team_id = t.team_id

)

select *
from enriched