{{ config(materialized='view') }}

select *
from {{ ref('mart_qb_season_stats') }}

where league = 'wfa'