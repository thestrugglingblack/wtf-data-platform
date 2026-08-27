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
Women's Tackle Football also known as WTF is my passion project where leverage my engineering and buddying analytics skill in sports data. This codebase `wtf-data-platform` currently extracts league and season data from HostedSports, stores the raw source data, and prepares normalized datasets for analysis.  It will serve as the Data Layer for this entire process. I will release dev.to and Medium post on my first initial exploration of creating these pipelines.

The long-term goal is to build an end-to-end platform for exploring women's tackle football:

- **Data pipeline:** Extract, validate, normalize, and maintain historical league, team, player, roster, game, and statistics data.
- **Data library:** Provide a consistent Python interface for querying and working with the processed data.
- **Streamlit applications:** Create interactive tools for discovering trends, comparing teams and players, and surfacing insights.
- **API backend:** Expose the curated data and analytical results through a reusable service layer.
- **Models and research:** Explore performance, team, player, and league-level questions across women's tackle football and develop data-informed models.

The project begins with the WFA and WNFC and is intended to grow into a broader, multi-league data resource for women's tackle football. Because league coverage and available statistics vary by season, the platform is designed to preserve source data while making differences in availability and quality visible.

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

### Available Data 
#### WFA
**Women's Football Alliance (WFA)** is a women's tackle football league founded in 2009. It provides organized 11-on-11 tackle football through three competitive divisions: Division I, Division II, and Division III. The divisions group teams by competitive level and program scale, giving teams opportunities to compete against similarly situated opponents across the league.

The WFA has been active as a league since 2009, making the current dataset a potential historical view spanning 18 seasons through 2026. The available data is uneven across seasons, so an empty cell means that a record is not currently available in this collection; it does not necessarily mean that the league or season did not exist.

Based on the table below, the WFA data currently includes:

- **Team lists:** 2010-2026, with the 2009 season not currently represented.
- **Schedules:** 2010-2021 and 2024-2026.
- **Game records:** 2020-2021 and 2024-2026.
- **Team and player information:** rosters from 2013-2019 and 2021-2026; team statistics from 2010-2019 and 2021-2026.
- **Performance statistics:** offensive and special teams statistics from 2010-2019 and 2021-2026; defensive statistics from 2017-2019 and 2021-2026; scoring statistics from 2019 and 2021-2026.
- **Standings:** 2011-2019 and 2021-2026.

**2020 is marked with an asterisk because the COVID-19 pandemic disrupted the WFA season.** The current collection contains game and schedule records for 2020, but the season should be treated as an exceptional and potentially incomplete data point when comparing seasons or building models.

|            | 2009 | 2010 | 2011 | 2012 | 2013 | 2014 | 2015 | 2016 | 2017 | 2018 | 2019 | 2020 | 2021 | 2022 | 2023 | 2024 | 2025 | 2026 |
|------------|------|------|------|------|------|------|------|------|------|------|------|------|------|------|------|------|------|------|
| Games      |      |      |      |      |      |      |      |      |      |      |      | X    | X    |      | X    | X    | X    | X    |
| Roster     |      |      |      |      | X    | X    | X    | X    | X    | X    | X    |      | X    | X    | X    | X    | X    | X    |
| Defensive  |      |      |      |      |      |      |      |      | X    | X    | X    |      | X    | X    | X    | X    | X    | X    |
| Offensive  |      | X    | X    | X    | X    | X    | X    | X    | X    | X    | X    |      | X    | X    | X    | X    | X    | X    |
| Schedule   |      | X    | X    | X    | X    | X    | X    | X    | X    | X    | X    | X    | X    |      | X    | X    | X    | X    |
| Scoring    |      |      |      |      |      |      |      |      |      |      | X    |      | X    | X    | X    | X    | X    | X    |
| Special    |      | X    | X    | X    | X    | X    | X    | X    | X    | X    | X    |      | X    | X    | X    | X    | X    | X    |
| Standings  |      |      | X    | X    | X    | X    | X    | X    | X    | X    | X    |      | X    | X    | X    | X    | X    | X    |
| Team Stats |      | X    | X    | X    | X    | X    | X    | X    | X    | X    | X    |      | X    | X    | X    | X    | X    | X    |
| Team List  |      | X    | X    | X    | X    | X    | X    | X    | X    | X    | X    | X    | X    | X    | X    | X    | X    | X    |

#### WNFC

The **Women's National Football Conference (WNFC)** is a professional women's American football league in the United States. The organization was formed in 2018 and began league play with its inaugural season in 2019. It is structured as a single national league rather than the multi-division format represented for the WFA above; the current dataset does not include separate WNFC divisions or tiers.

The WNFC data in this project covers the inaugural 2019 season and continues through 2026, with a major interruption in 2020. Based on the table below, the collection currently includes:

- **Team lists:** 2019 and 2021-2026.
- **Schedules:** 2019, 2021-2022, and 2024-2026.
- **Game records:** 2021-2022 and 2024-2026.
- **Roster and team information:** rosters and team statistics from 2019 and 2021-2026.
- **Performance statistics:** offensive, defensive, scoring, and special teams statistics from 2019 and 2021-2026.
- **Standings:** 2021-2022 and 2024-2026.

**2020 is marked with an asterisk because the COVID-19 pandemic interrupted the WNFC season.** No WNFC records are currently represented for 2020. The 2023 collection includes roster, performance, team, standings, and team-list data, but does not currently include game or schedule records. These gaps should be considered when comparing seasons or building models.

|            | 2019 | 2020 | 2021 | 2022 | 2023 | 2024 | 2025 | 2026 |
|------------|------|------|------|------|------|------|------|------|
| Game       |      |      | X    | X    |      | X    | X    | X    |
| Roster     | X    |      | X    | X    | X    | X    | X    | X    |
| Defensive  | X    |      | X    | X    | X    | X    | X    | X    |
| Offensive  | X    |      | X    | X    | X    | X    | X    | X    |
| Schedule   | X    |      | X    | X    |      | X    | X    | X    |
| Scoring    | X    |      | X    | X    | X    | X    | X    | X    |
| Special    | X    |      | X    | X    | X    | X    | X    | X    |
| Standings  |      |      | X    | X    | X    | X    | X    | X    |
| Team Stats | X    |      | X    | X    | X    | X    | X    | X    |
| Team List  | X    |      | X    | X    | X    | X    | X    | X    |



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