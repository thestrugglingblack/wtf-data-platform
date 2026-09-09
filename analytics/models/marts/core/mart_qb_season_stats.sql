with player_seasons as (

    select *
    from {{ ref('mart_player_season_stats') }}

),

quarterbacks as (

    select *
    from player_seasons

    where coalesce(
        passing_attempts,
        0
    ) > 0

),

final as (

    select
        league,
        season,

        team_id,
        team_name,

        player_id,
        player_name,

        games_with_stats,

        passing_attempts,
        passing_completions,
        passing_yards,

        pass_tds as passing_tds,

        passing_interceptions,

        passing_long,

        completion_pct as source_completion_pct,
        passing_average as source_passing_average,
        passer_rating as source_passer_rating,

        case
            when passing_attempts > 0
                then (
                    cast(passing_completions as double)
                    / cast(passing_attempts as double)
                ) * 100.0
            else null
        end as completion_pct_calculated,

        case
            when passing_attempts > 0
                then (
                    cast(passing_yards as double)
                    / cast(passing_attempts as double)
                )
            else null
        end as yards_per_attempt,

        case
            when passing_attempts > 0
                then (
                    cast(pass_tds as double)
                    / cast(passing_attempts as double)
                ) * 100.0
            else null
        end as touchdown_pct,

        case
            when passing_attempts > 0
                then (
                    cast(passing_interceptions as double)
                    / cast(passing_attempts as double)
                ) * 100.0
            else null
        end as interception_pct,

        case
            when passing_attempts > 0
                then (
                    least(
                        greatest(
                            (
                                (
                                    cast(passing_completions as double)
                                    / cast(passing_attempts as double)
                                ) - 0.3
                            ) * 5.0,
                            0.0
                        ),
                        2.375
                    )
                    +
                    least(
                        greatest(
                            (
                                (
                                    cast(passing_yards as double)
                                    / cast(passing_attempts as double)
                                ) - 3.0
                            ) * 0.25,
                            0.0
                        ),
                        2.375
                    )
                    +
                    least(
                        greatest(
                            (
                                cast(pass_tds as double)
                                / cast(passing_attempts as double)
                            ) * 20.0,
                            0.0
                        ),
                        2.375
                    )
                    +
                    least(
                        greatest(
                            2.375
                            -
                            (
                                cast(passing_interceptions as double)
                                / cast(passing_attempts as double)
                            ) * 25.0,
                            0.0
                        ),
                        2.375
                    )
                ) / 6.0 * 100.0
            else null
        end as passer_rating_calculated,

        has_canonical_player,

        * exclude (
            league,
            season,
            team_id,
            team_name,
            player_id,
            player_name,
            games_with_stats,
            passing_attempts,
            passing_completions,
            passing_yards,
            pass_tds,
            passing_interceptions,
            passing_long,
            completion_pct,
            passing_average,
            passer_rating,
            has_canonical_player
        )

    from quarterbacks

)

select *
from final