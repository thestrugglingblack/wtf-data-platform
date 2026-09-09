select
    league,
    season,

    team_id,
    team_name,

    player_id,

    canonical_player_name as player_name,

    has_canonical_player,

    * exclude (
        league,
        season,
        team_id,
        team_name,
        player_id,
        canonical_player_name,
        has_canonical_player
    )

from {{ ref('int_roster_memberships') }}