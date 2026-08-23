```bash                                                     
▄     ▄▄▄▄▄▄▄▄ ▄▄▄▄▄▄        ▄▄▄▄            ▄          
█  █  █   █    █             █   ▀▄  ▄▄▄   ▄▄█▄▄   ▄▄▄  
▀ █▀█ █   █    █▄▄▄▄▄        █    █ ▀   █    █    ▀   █ 
██  ██▀   █    █             █    █ ▄▀▀▀█    █    ▄▀▀▀█ 
█    █    █    █             █▄▄▄▀  ▀▄▄▀█    ▀▄▄  ▀▄▄▀█          
```

<p align="center">

![GitHub Repo Stars](https://img.shields.io/github/stars/thestrugglingblack/wtf-data-platform)
![GitHub Last Commit](https://img.shields.io/github/last-commit/thestrugglingblack/wtf-data-platform)
![GitHub Commit Activity](https://img.shields.io/github/commit-activity/m/thestrugglingblack/wtf-data-platform)
![GitHub Repo Size](https://img.shields.io/github/repo-size/thestrugglingblack/wtf-data-platform)
</p>

## 📍Table of Contents
* 👋 [Overview](#-overview)
* ✅ [Dependencies](#-dependencies)
* 🌵 [Folder Structure](#-file-structure)
* 💾 [Data](#-data)
* 🏃 [Preliminary Steps](#-preliminary-steps)
* 🚀 [Getting Started](#getting-started)
* 📑 [Resources](#-resources)


## 👋 Overview

[![LinkedIn Badge](https://img.shields.io/badge/LinkedIn-0077B5?style=flat&logo=linkedin&logoColor=white)](https://www.linkedin.com/in/zuri-hunter-748ba514)
[![Twitter Badge](https://img.shields.io/badge/Twitter-1DA1F2?style=flat&logo=twitter&logoColor=white)](https://x.com/ZuriHunter)


## 🌵 Folder Structure
```tree
.
├── data/                     # Folder that holds all the json/text files
    ├── raw/                  # Raw extracted version of the data from HostedSports
    ├── processed/            # Normalized and processed data
├── client.py                 # Wrapper for interacting with HostedSports API
├── config.py                 # Pipeline configurations
├── extract.py                # Pulls in data from HostedSports API
├── main.py                 
├── normalize.py              # Cleans and normalizes the data after data pull
├── README.md
├── requirements.txt
└── utils.py
```

## 💾 Data 

### Missing Data 
| League | Years Active | Roster         | Games          | Schedule  | Defensive Stats | Offensive Stats | Scoring Stats  | Special Teams Stats | Standings      | Team Stats     | Team List |
|--------|--------------|----------------|----------------|-----------|-----------------|-----------------|----------------|---------------------|----------------|----------------|-----------|
| WFA    | 2009-2026    | 2009 2010 2011 | 2009 2010 2011 | 2009 2011 | 2009 2010 2011  | 2009 2010 2011  | 2009 2010 2011 | 2009 2010 2011      | 2009 2010 2011 | 2009 2010 2011 | 2009      |
| WNFC   | 2019-2026    | 2020           |                |           |                 |                 |                |                     |                |                |           |

This is the folder structure of the data after extraction and normalization.

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