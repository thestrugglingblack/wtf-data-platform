{{ config(materialized='view') }}

select *
from {{ ref('mart_player_career_stats') }}

where league = 'wnfc'