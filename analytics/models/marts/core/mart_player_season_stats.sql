with player_seasons as (

    select *
    from {{ ref('int_player_seasons') }}

),

game_counts as (

    select
        league,
        season,
        team_id,
        player_id,

        count(
            distinct game_id
        ) as games_with_stats

    from {{ ref('int_player_games') }}

    where player_id is not null

    group by
        league,
        season,
        team_id,
        player_id

),

final as (

    select
        ps.league,
        ps.season,

        ps.team_id,
        ps.team_name,

        ps.player_id,
        ps.player_name,

        ps.has_canonical_player,

        gc.games_with_stats,

        ps.* exclude (
            league,
            season,
            team_id,
            team_name,
            player_id,
            player_name,
            has_canonical_player
        )

    from player_seasons ps

    left join game_counts gc
        on ps.league = gc.league
        and ps.season = gc.season
        and ps.team_id = gc.team_id
        and ps.player_id = gc.player_id

)

select *
from final