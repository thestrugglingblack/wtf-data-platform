{{ config(materialized='view') }}

select *
from {{ ref('mart_player_game_logs') }}

where league = 'wnfc'