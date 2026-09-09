{{ config(materialized='view') }}

select *
from {{ ref('mart_players') }}

where league = 'wfa'