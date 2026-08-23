```bash                                                     
▄     ▄▄▄▄▄▄▄▄ ▄▄▄▄▄▄        ▄▄▄▄            ▄          
█  █  █   █    █             █   ▀▄  ▄▄▄   ▄▄█▄▄   ▄▄▄  
▀ █▀█ █   █    █▄▄▄▄▄        █    █ ▀   █    █    ▀   █ 
██  ██▀   █    █             █    █ ▄▀▀▀█    █    ▄▀▀▀█ 
█    █    █    █             █▄▄▄▀  ▀▄▄▀█    ▀▄▄  ▀▄▄▀█          
```

## Table of Contents

## Overview

## File Structure

## Data 
```tree
data/
├── raw/
│   ├── wnfc/
│   │   ├── 2025/
│   │   │   ├── teams.json
│   │   │   ├── schedule.json
│   │   │   ├── standings.json
│   │   │   ├── team_stats.json
│   │   │   ├── offensive_stats.json
│   │   │   ├── defensive_stats.json
│   │   │   ├── special_teams_stats.json
│   │   │   ├── scoring_stats.json
│   │   │   ├── rosters/
│   │   │   ├── players/
│   │   │   └── games/
│   │
│   └── wfa/
│   │   ├── 2025/
│   │   │   ├── teams.json
│   │   │   ├── schedule.json
│   │   │   ├── standings.json
│   │   │   ├── team_stats.json
│   │   │   ├── offensive_stats.json
│   │   │   ├── defensive_stats.json
│   │   │   ├── special_teams_stats.json
│   │   │   ├── scoring_stats.json
│   │   │   ├── rosters/
│   │   │   ├── players/
│   │   │   └── games/
│
└── processed/
    ├── teams.csv
    ├── players.csv
    ├── rosters.csv
    ├── games.csv
    ├── player_game_stats.csv
    ├── player_season_stats.csv
    ├── team_season_stats.csv
    └── standings.csv

```
## Deployment