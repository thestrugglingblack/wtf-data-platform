# Data Usage and Rights Notice

## Overview

The WTF Data Platform processes women's tackle football data obtained from third-party sources, primarily HostedSports.

The software license for this repository does **not** apply to the underlying sports data.

This document describes the distinction between the WTF Data Platform's original work and data originating from third-party sources.

## Source Data

The primary source of WFA and WNFC data used by this project is HostedSports.

HostedSports provides software used by leagues to manage information including teams, rosters, schedules, standings, and game statistics. According to information provided directly by HostedSports, responsibility for entering, reviewing, publishing, and maintaining this information generally belongs to the individual leagues and teams using the HostedSports platform.

Accordingly, portions of the source data may originate from or be associated with:

* HostedSports;
* the Women's Football Alliance (WFA);
* the Women's National Football Conference (WNFC);
* participating teams;
* league or team administrators;
* league statistical personnel; and
* other applicable data or intellectual-property rights holders.

The WTF Data Platform does **not** claim ownership of third-party source data.

All rights in underlying third-party data remain with their respective rights holders.

## Data Availability and Quality

HostedSports has indicated that WFA data is available from as early as 2010 and WNFC data is available from 2021 through 2026. Changes to the HostedSports platform and league practices over time may result in differences between historical and current data structures.

HostedSports has also indicated that data quality, completeness, verification, and publication practices vary by league, team, and season.

For many historical seasons, statistics were entered by individual teams and may contain missing, incomplete, inconsistent, unverified, or inaccurate information.

HostedSports identified the WNFC 2025 and 2026 seasons as an exception because league statistical personnel, rather than individual teams, were responsible for statistics and additional review occurred.

The WTF Data Platform performs structural validation, normalization, identifier resolution, auditing, and other data-quality processes. These processes improve consistency and identify known data-quality issues, but they do not independently verify that every statistic reported by the original source is factually correct.

## No Data Rights Granted by the Software License

The software license contained in `LICENSE` applies to the original software and related materials authored for the WTF Data Platform.

It does not grant permission to use, reproduce, publish, redistribute, sublicense, sell, commercialize, mirror, or otherwise distribute third-party data obtained from HostedSports or other data providers.

Installing, cloning, forking, modifying, or distributing the WTF Data Platform software does not provide a license to the underlying data.

## Redistribution

Third-party source data is not licensed for redistribution by this project.

Unless a user has independently obtained the necessary authorization from the applicable rights holder, data obtained through this project should not be:

* republished;
* redistributed;
* mirrored;
* sublicensed;
* sold;
* offered as a commercial data product;
* uploaded to another public dataset or repository;
* incorporated into a publicly distributed database;
* exposed through a public API; or
* otherwise made available to third parties.

This restriction applies to raw source files and to processed exports that reproduce or substantially contain the underlying third-party data.

Nothing in this notice should be interpreted as restricting rights that a user may independently possess under an agreement with HostedSports, a league, a team, or another applicable rights holder.

## Commercial Use

No permission to commercially exploit HostedSports, WFA, WNFC, team, player, or other third-party source data is granted by this project.

The presence of data-processing software in a publicly accessible repository does not constitute permission to sell or commercially redistribute the underlying data or datasets produced from it.

Anyone seeking commercial or redistribution rights should obtain authorization directly from the applicable rights holder.

## Processed and Derived Data

The WTF Data Platform transforms source information through processes including extraction, recovery, normalization, validation, schema standardization, identifier resolution, auditing, and publication.

The project may contain original intellectual property in its software, documentation, schema designs, validation rules, data dictionaries, organizational structure, and other original materials.

However, transformation of third-party source data does not mean that this project claims ownership of the underlying facts, statistics, records, or other third-party materials.

Processed datasets may therefore remain subject to rights, contractual restrictions, or usage conditions associated with their underlying sources.

## Repository Policy

The public repository is intended to contain the software and documentation necessary to understand and reproduce the WTF Data Platform architecture.

Third-party production data should not be committed to the public repository.

This includes, unless specifically authorized:

```text
data/raw/
data/recovered/
data/processed/
data/published/
```

Synthetic, fabricated, or otherwise appropriately authorized sample data may be included for testing, examples, and documentation.

## Attribution

HostedSports is the primary source platform for the WFA and WNFC data processed by this project.

The Women's Football Alliance (WFA), Women's National Football Conference (WNFC), HostedSports, participating teams, and other referenced organizations retain their respective names, trademarks, data rights, and other applicable rights.

Reference to these organizations is for identification and attribution purposes and does not imply sponsorship, endorsement, partnership, or affiliation with the WTF Data Platform.

## No Warranty

Data processed by this project is provided without any representation or warranty regarding completeness, accuracy, reliability, or fitness for a particular purpose.

Historical records may contain missing, partial, inconsistent, unverified, or inaccurate statistics originating from the source systems.

Users should account for these limitations when conducting analysis or drawing conclusions from the data.

## Questions About Data Rights

Questions regarding permission to access, redistribute, publish, or commercially use HostedSports-derived data should be directed to HostedSports or the applicable league, team, or rights holder.

Questions regarding the WTF Data Platform's original software, schemas, documentation, or processing methodology may be directed to the project maintainer.
