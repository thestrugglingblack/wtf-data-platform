select
    cast(player_id as varchar) as player_id,
    cast(player_name as varchar) as player_name,

    * exclude (
        player_id,
        player_name
    )

from {{ source('canonical', 'players') }}