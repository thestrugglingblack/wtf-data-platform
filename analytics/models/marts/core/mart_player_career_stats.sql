with player_seasons as (

    select *
    from {{ ref('mart_player_season_stats') }}

    where player_id is not null

),

career as (

    select
        league,
        player_id,

        any_value(
            player_name
        ) as player_name,

        min(season) as first_season,
        max(season) as last_season,

        count(
            distinct season
        ) as seasons_played,

        count(
            distinct team_id
        ) as teams_played_for,

        sum(
            coalesce(
                games_with_stats,
                0
            )
        ) as games_with_stats,

        -- ==================================================
        -- Passing
        -- ==================================================

        sum(
            coalesce(
                passing_attempts,
                0
            )
        ) as passing_attempts,

        sum(
            coalesce(
                passing_completions,
                0
            )
        ) as passing_completions,

        sum(
            coalesce(
                passing_yards,
                0
            )
        ) as passing_yards,

        sum(
            coalesce(
                pass_tds,
                0
            )
        ) as passing_tds,

        sum(
            coalesce(
                passing_interceptions,
                0
            )
        ) as passing_interceptions,

        -- ==================================================
        -- Rushing
        -- ==================================================

        sum(
            coalesce(
                rushing_carries,
                0
            )
        ) as rushing_carries,

        sum(
            coalesce(
                rushing_yards,
                0
            )
        ) as rushing_yards,

        -- ==================================================
        -- Receiving
        -- ==================================================

        sum(
            coalesce(
                receiving_catches,
                0
            )
        ) as receiving_catches,

        sum(
            coalesce(
                receiving_yards,
                0
            )
        ) as receiving_yards,

        sum(
            coalesce(
                receiving_tds,
                0
            )
        ) as receiving_tds,

        -- ==================================================
        -- Defense
        -- ==================================================

        sum(
            coalesce(
                tackles,
                0
            )
        ) as tackles,

        sum(
            coalesce(
                tackle_assists,
                0
            )
        ) as tackle_assists,

        sum(
            coalesce(
                tackles_combined,
                0
            )
        ) as tackles_combined,

        sum(
            coalesce(
                tackles_for_loss,
                0
            )
        ) as tackles_for_loss,

        sum(
            coalesce(
                sacks,
                0
            )
        ) as sacks,

        sum(
            coalesce(
                interceptions,
                0
            )
        ) as defensive_interceptions,

        sum(
            coalesce(
                forced_fumbles,
                0
            )
        ) as forced_fumbles,

        sum(
            coalesce(
                fumble_recoveries,
                0
            )
        ) as fumble_recoveries,

        sum(
            coalesce(
                passes_deflected,
                0
            )
        ) as passes_deflected,

        sum(
            coalesce(
                blocked_kicks,
                0
            )
        ) as blocked_kicks,

        -- ==================================================
        -- Kick returns
        -- ==================================================

        sum(
            coalesce(
                kickoff_returns,
                0
            )
        ) as kickoff_returns,

        sum(
            coalesce(
                kickoff_return_yards,
                0
            )
        ) as kickoff_return_yards,

        sum(
            coalesce(
                kickoff_return_tds,
                0
            )
        ) as kickoff_return_tds,

        -- ==================================================
        -- Punt returns
        -- ==================================================

        sum(
            coalesce(
                punt_returns,
                0
            )
        ) as punt_returns,

        sum(
            coalesce(
                punt_return_yards,
                0
            )
        ) as punt_return_yards,

        sum(
            coalesce(
                punt_return_tds,
                0
            )
        ) as punt_return_tds,

        -- ==================================================
        -- Interception returns
        -- ==================================================

        sum(
            coalesce(
                interception_return_yards,
                0
            )
        ) as interception_return_yards,

        sum(
            coalesce(
                interception_return_tds,
                0
            )
        ) as interception_return_tds,

        -- ==================================================
        -- Fumble returns
        -- ==================================================

        sum(
            coalesce(
                fumble_recovery_yards,
                0
            )
        ) as fumble_recovery_yards,

        sum(
            coalesce(
                fumble_recovery_tds,
                0
            )
        ) as fumble_recovery_tds,

        -- ==================================================
        -- Kicking
        -- ==================================================

        sum(
            coalesce(
                fg_made,
                0
            )
        ) as field_goals_made,

        sum(
            coalesce(
                fg_attempts,
                0
            )
        ) as field_goal_attempts,

        sum(
            coalesce(
                pat_made,
                0
            )
        ) as pats_made,

        sum(
            coalesce(
                pat_attempts,
                0
            )
        ) as pat_attempts,

        -- ==================================================
        -- Punting
        -- ==================================================

        sum(
            coalesce(
                punts,
                0
            )
        ) as punts,

        sum(
            coalesce(
                punt_yards,
                0
            )
        ) as punt_yards,

        -- ==================================================
        -- Scoring
        -- ==================================================

        sum(
            coalesce(
                tds,
                0
            )
        ) as total_tds,

        sum(
            coalesce(
                two_point_conversions,
                0
            )
        ) as two_point_conversions,

        sum(
            coalesce(
                safety,
                0
            )
        ) as safeties,

        sum(
            coalesce(
                total_points,
                0
            )
        ) as total_points

    from player_seasons

    group by
        league,
        player_id

),

final as (

    select
        *,

        case
            when passing_attempts > 0
                then (
                    cast(passing_completions as double)
                    / cast(passing_attempts as double)
                ) * 100.0
            else null
        end as career_completion_pct,

        case
            when passing_attempts > 0
                then (
                    cast(passing_yards as double)
                    / cast(passing_attempts as double)
                )
            else null
        end as career_yards_per_attempt,

        case
            when rushing_carries > 0
                then (
                    cast(rushing_yards as double)
                    / cast(rushing_carries as double)
                )
            else null
        end as career_yards_per_carry,

        case
            when receiving_catches > 0
                then (
                    cast(receiving_yards as double)
                    / cast(receiving_catches as double)
                )
            else null
        end as career_yards_per_reception,

        case
            when kickoff_returns > 0
                then (
                    cast(kickoff_return_yards as double)
                    / cast(kickoff_returns as double)
                )
            else null
        end as career_kickoff_return_average,

        case
            when punt_returns > 0
                then (
                    cast(punt_return_yards as double)
                    / cast(punt_returns as double)
                )
            else null
        end as career_punt_return_average,

        case
            when punts > 0
                then (
                    cast(punt_yards as double)
                    / cast(punts as double)
                )
            else null
        end as career_punt_average,

        case
            when field_goal_attempts > 0
                then (
                    cast(field_goals_made as double)
                    / cast(field_goal_attempts as double)
                ) * 100.0
            else null
        end as career_field_goal_pct,

        case
            when pat_attempts > 0
                then (
                    cast(pats_made as double)
                    / cast(pat_attempts as double)
                ) * 100.0
            else null
        end as career_pat_pct

    from career

)

select *
from final