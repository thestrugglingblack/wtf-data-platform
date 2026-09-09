{{ config(materialized='view') }}

select *
from {{ ref('mart_player_season_stats') }}

where league = 'wnfc'