with games as (

    select *
    from {{ ref('stg_games') }}

),

home_teams as (

    select
        league,
        season,
        game_id,
        season_type,
        week,
        date,

        home_team_name as team_name,
        visitor_team_name as opponent_team_name,

        'home' as game_location,

        home_team_name,
        visitor_team_name,

        * exclude (
            league,
            season,
            game_id,
            season_type,
            week,
            date,
            home_team_name,
            visitor_team_name
        )

    from games

),

away_teams as (

    select
        league,
        season,
        game_id,
        season_type,
        week,
        date,

        visitor_team_name as team_name,
        home_team_name as opponent_team_name,

        'away' as game_location,

        home_team_name,
        visitor_team_name,

        * exclude (
            league,
            season,
            game_id,
            season_type,
            week,
            date,
            home_team_name,
            visitor_team_name
        )

    from games

),

team_games as (

    select *
    from home_teams

    union all

    select *
    from away_teams

)

select *
from team_games