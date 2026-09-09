{{ config(materialized='view') }}

select *
from {{ ref('mart_team_season_summary') }}

where league = 'wfa'