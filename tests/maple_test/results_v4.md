# Maple Test v4 results

> Written by `python -m tests.maple_test grade --version v4`. Do not edit by hand.

**Correct** is the share of questions answered correctly, each question weighted once (a question asked three times counts its share of correct passes). Dev is the public set, test the held-out one (README, 'Version 4').

| Arm | Correct | Dev | Test | Answers | USD per answer | Seconds per answer | Flagged for review | JSON decided | Run errors |
| :-- | --: | --: | --: | --: | --: | --: | --: | --: | --: |
| arose26 | 51.9% | 47.7% | 61.9% | 84 | 0.022 | 12.2 | 15.5% | 71.4% | 0 |
| canada_data_agent | 35.2% | 28.1% | 52.4% | 84 | 0.018 | 12.1 | 16.7% | 78.6% | 0 |
| candata_mcp | 54.2% | 47.1% | 71.4% | 84 | 0.039 | 15.4 | 21.4% | 60.7% | 0 |
| maplestats-local | 90.7% | 92.8% | 85.7% | 84 | 0.048 | 24.0 | 10.7% | 77.4% | 0 |
| maplestats_hosted | 86.6% | 81.0% | 100.0% | 84 | 0.048 | 13.7 | 11.9% | 72.6% | 0 |
| mcp_canada | 54.6% | 47.7% | 71.4% | 84 | 0.070 | 21.5 | 25.0% | 60.7% | 1 |
| mcp_statcan | 47.2% | 41.2% | 61.9% | 84 | 0.025 | 13.5 | 19.0% | 64.3% | 0 |
| no_tools | 11.1% | 9.8% | 14.3% | 84 | 0.094 | 43.8 | 44.0% | 52.4% | 3 |
| opencanada | 49.5% | 44.4% | 61.9% | 84 | 0.037 | 19.1 | 20.2% | 64.3% | 0 |
| openmcp | 58.3% | 56.9% | 61.9% | 84 | 0.063 | 93.9 | 23.8% | 58.3% | 0 |
| pipeworx | 63.9% | 60.8% | 71.4% | 84 | 0.077 | 26.2 | 13.1% | 71.4% | 0 |
| statcan2 | 30.1% | 26.8% | 38.1% | 84 | 0.045 | 13.4 | 21.4% | 50.0% | 0 |

## By source

| Arm | boc | cmhc | federal | international | municipal | provincial | statcan |
| :-- | --: | --: | --: | --: | --: | --: | --: |
| arose26 | 100.0% (8) | 73.3% (5) | 0.0% (11) | 16.7% (6) | 0.0% (3) | 0.0% (6) | 74.7% (33) |
| canada_data_agent | 37.5% (8) | 80.0% (5) | 9.1% (11) | 16.7% (6) | 33.3% (3) | 0.0% (6) | 46.5% (33) |
| candata_mcp | 75.0% (8) | 80.0% (5) | 18.2% (11) | 16.7% (6) | 0.0% (3) | 16.7% (6) | 75.8% (33) |
| maplestats-local | 100.0% (8) | 100.0% (5) | 100.0% (11) | 100.0% (6) | 100.0% (3) | 100.0% (6) | 79.8% (33) |
| maplestats_hosted | 100.0% (8) | 53.3% (5) | 90.9% (11) | 100.0% (6) | 33.3% (3) | 100.0% (6) | 86.9% (33) |
| mcp_canada | 100.0% (8) | 60.0% (5) | 45.5% (11) | 16.7% (6) | 0.0% (3) | 33.3% (6) | 61.6% (33) |
| mcp_statcan | 75.0% (8) | 66.7% (5) | 0.0% (11) | 16.7% (6) | 0.0% (3) | 0.0% (6) | 71.7% (33) |
| no_tools | 0.0% (8) | 40.0% (5) | 0.0% (11) | 16.7% (6) | 0.0% (3) | 0.0% (6) | 15.2% (33) |
| opencanada | 100.0% (8) | 60.0% (5) | 27.3% (11) | 16.7% (6) | 0.0% (3) | 0.0% (6) | 62.6% (33) |
| openmcp | 62.5% (8) | 40.0% (5) | 45.5% (11) | 66.7% (6) | 33.3% (3) | 16.7% (6) | 72.7% (33) |
| pipeworx | 100.0% (8) | 80.0% (5) | 36.4% (11) | 100.0% (6) | 0.0% (3) | 0.0% (6) | 72.7% (33) |
| statcan2 | 25.0% (8) | 60.0% (5) | 9.1% (11) | 16.7% (6) | 33.3% (3) | 0.0% (6) | 41.4% (33) |

## Judge

| Arm | Judged | Agrees with the grader | Flagged |
| :-- | --: | --: | --: |
| arose26 | 84 | 89.3% | 13 of 84 (15.5%) |
| canada_data_agent | 84 | 84.5% | 14 of 84 (16.7%) |
| candata_mcp | 84 | 84.5% | 18 of 84 (21.4%) |
| maplestats-local | 84 | 90.5% | 9 of 84 (10.7%) |
| maplestats_hosted | 84 | 90.5% | 10 of 84 (11.9%) |
| mcp_canada | 83 | 78.3% | 21 of 84 (25.0%) |
| mcp_statcan | 84 | 85.7% | 16 of 84 (19.0%) |
| no_tools | 81 | 55.6% | 37 of 84 (44.0%) |
| opencanada | 84 | 81.0% | 17 of 84 (20.2%) |
| openmcp | 84 | 77.4% | 20 of 84 (23.8%) |
| pipeworx | 84 | 88.1% | 11 of 84 (13.1%) |
| statcan2 | 84 | 78.6% | 18 of 84 (21.4%) |

## Per answer

| Question | Split | Arm | Pass | Grade | Basis | Judge | Review |
| :-- | :-- | :-- | --: | :-- | :-- | :-- | :-- |
| A-01 | dev | arose26 | 0 | correct | json | correct (0.93) |  |
| A-01 | dev | canada_data_agent | 0 | abstained | json | abstained (0.95) |  |
| A-01 | dev | candata_mcp | 0 | correct | json | correct (0.90) |  |
| A-01 | dev | maplestats-local | 0 | abstained | json | abstained (0.93) |  |
| A-01 | dev | maplestats_hosted | 0 | correct | json | correct (0.90) |  |
| A-01 | dev | mcp_canada | 0 | correct | json | correct (0.93) |  |
| A-01 | dev | mcp_statcan | 0 | correct | json | correct (0.90) |  |
| A-01 | dev | no_tools | 0 | abstained | json | abstained (0.93) |  |
| A-01 | dev | opencanada | 0 | abstained | regex | abstained (0.80) |  |
| A-01 | dev | openmcp | 0 | correct | json | correct (0.90) |  |
| A-01 | dev | pipeworx | 0 | correct | json | correct (0.90) |  |
| A-01 | dev | statcan2 | 0 | correct | json | correct (0.93) |  |
| A-02 | dev | arose26 | 0 | correct | regex | correct (0.85) |  |
| A-02 | dev | arose26 | 1 | correct | regex | correct (0.85) |  |
| A-02 | dev | arose26 | 2 | correct | regex | correct (0.88) |  |
| A-02 | dev | canada_data_agent | 0 | abstained | json | abstained (0.93) |  |
| A-02 | dev | canada_data_agent | 1 | correct | regex | correct (0.85) |  |
| A-02 | dev | canada_data_agent | 2 | correct | regex | correct (0.90) |  |
| A-02 | dev | candata_mcp | 0 | correct | regex | correct (0.85) |  |
| A-02 | dev | candata_mcp | 1 | correct | regex | correct (0.88) |  |
| A-02 | dev | candata_mcp | 2 | correct | regex | correct (0.88) |  |
| A-02 | dev | maplestats-local | 0 | abstained | regex | abstained (0.90) |  |
| A-02 | dev | maplestats-local | 1 | abstained | json | abstained (0.90) |  |
| A-02 | dev | maplestats-local | 2 | correct | regex | correct (0.85) |  |
| A-02 | dev | maplestats_hosted | 0 | correct | regex | correct (0.85) |  |
| A-02 | dev | maplestats_hosted | 1 | correct | regex | correct (0.85) |  |
| A-02 | dev | maplestats_hosted | 2 | correct | regex | correct (0.90) |  |
| A-02 | dev | mcp_canada | 0 | abstained | json | abstained (0.90) |  |
| A-02 | dev | mcp_canada | 1 | abstained | regex | – |  |
| A-02 | dev | mcp_canada | 2 | abstained | json | abstained (0.90) |  |
| A-02 | dev | mcp_statcan | 0 | correct | regex | correct (0.85) |  |
| A-02 | dev | mcp_statcan | 1 | correct | regex | correct (0.85) |  |
| A-02 | dev | mcp_statcan | 2 | correct | regex | correct (0.85) |  |
| A-02 | dev | no_tools | 0 | hallucinated | regex | abstained (0.96) | open |
| A-02 | dev | no_tools | 1 | abstained | json | abstained (0.90) |  |
| A-02 | dev | no_tools | 2 | abstained | json | abstained (0.90) |  |
| A-02 | dev | opencanada | 0 | abstained | regex | abstained (0.93) |  |
| A-02 | dev | opencanada | 1 | abstained | regex | abstained (0.85) |  |
| A-02 | dev | opencanada | 2 | abstained | regex | abstained (0.90) |  |
| A-02 | dev | openmcp | 0 | hallucinated* | regex | hallucinated (0.90) | settled |
| A-02 | dev | openmcp | 1 | correct | regex | correct (0.90) |  |
| A-02 | dev | openmcp | 2 | partial* | regex | partial (0.70) | settled |
| A-02 | dev | pipeworx | 0 | correct | regex | correct (0.80) |  |
| A-02 | dev | pipeworx | 1 | correct | regex | correct (0.85) |  |
| A-02 | dev | pipeworx | 2 | correct | regex | correct (0.85) |  |
| A-02 | dev | statcan2 | 0 | correct | regex | correct (0.85) |  |
| A-02 | dev | statcan2 | 1 | correct | regex | correct (0.85) |  |
| A-02 | dev | statcan2 | 2 | correct | regex | correct (0.85) |  |
| A-03 | dev | arose26 | 0 | correct | json | correct (0.93) |  |
| A-03 | dev | arose26 | 1 | correct | json | correct (0.93) |  |
| A-03 | dev | arose26 | 2 | correct | json | correct (0.93) |  |
| A-03 | dev | canada_data_agent | 0 | abstained | json | abstained (0.93) |  |
| A-03 | dev | canada_data_agent | 1 | abstained | json | abstained (0.93) |  |
| A-03 | dev | canada_data_agent | 2 | abstained | json | abstained (0.95) |  |
| A-03 | dev | candata_mcp | 0 | partial | regex | partial (0.60) | open |
| A-03 | dev | candata_mcp | 1 | partial | regex | partial (0.72) |  |
| A-03 | dev | candata_mcp | 2 | hallucinated | regex | hallucinated (0.90) |  |
| A-03 | dev | maplestats-local | 0 | correct | json | correct (0.93) |  |
| A-03 | dev | maplestats-local | 1 | hallucinated | regex | hallucinated (0.80) |  |
| A-03 | dev | maplestats-local | 2 | partial | regex | partial (0.60) | open |
| A-03 | dev | maplestats_hosted | 0 | correct | json | correct (0.93) |  |
| A-03 | dev | maplestats_hosted | 1 | correct | json | correct (0.93) |  |
| A-03 | dev | maplestats_hosted | 2 | correct | json | correct (0.90) |  |
| A-03 | dev | mcp_canada | 0 | partial | regex | partial (0.60) | open |
| A-03 | dev | mcp_canada | 1 | partial | regex | partial (0.70) |  |
| A-03 | dev | mcp_canada | 2 | partial | regex | partial (0.80) |  |
| A-03 | dev | mcp_statcan | 0 | hallucinated | regex | hallucinated (0.90) |  |
| A-03 | dev | mcp_statcan | 1 | partial | regex | partial (0.72) |  |
| A-03 | dev | mcp_statcan | 2 | hallucinated | regex | hallucinated (0.90) |  |
| A-03 | dev | no_tools | 0 | abstained | json | abstained (0.95) |  |
| A-03 | dev | no_tools | 1 | abstained | json | abstained (0.93) |  |
| A-03 | dev | no_tools | 2 | abstained | json | abstained (0.95) |  |
| A-03 | dev | opencanada | 0 | correct | json | correct (0.90) |  |
| A-03 | dev | opencanada | 1 | correct | json | correct (0.90) |  |
| A-03 | dev | opencanada | 2 | correct | json | correct (0.88) |  |
| A-03 | dev | openmcp | 0 | partial | regex | partial (0.80) |  |
| A-03 | dev | openmcp | 1 | correct | json | correct (0.90) |  |
| A-03 | dev | openmcp | 2 | correct | json | correct (0.85) |  |
| A-03 | dev | pipeworx | 0 | correct | json | correct (0.93) |  |
| A-03 | dev | pipeworx | 1 | partial | regex | partial (0.80) |  |
| A-03 | dev | pipeworx | 2 | partial | regex | partial (0.80) |  |
| A-03 | dev | statcan2 | 0 | partial | regex | hallucinated (0.90) | open |
| A-03 | dev | statcan2 | 1 | partial | regex | hallucinated (0.90) | open |
| A-03 | dev | statcan2 | 2 | hallucinated | regex | hallucinated (0.90) |  |
| A-05 | dev | arose26 | 0 | correct | json | correct (0.85) |  |
| A-05 | dev | canada_data_agent | 0 | abstained | json | abstained (0.90) |  |
| A-05 | dev | candata_mcp | 0 | correct | json | correct (0.80) |  |
| A-05 | dev | maplestats-local | 0 | correct | json | correct (0.85) |  |
| A-05 | dev | maplestats_hosted | 0 | correct | json | correct (0.85) |  |
| A-05 | dev | mcp_canada | 0 | correct | json | abstained (0.70) | open |
| A-05 | dev | mcp_statcan | 0 | correct | json | correct (0.85) |  |
| A-05 | dev | no_tools | 0 | abstained | json | abstained (0.80) |  |
| A-05 | dev | opencanada | 0 | correct | json | correct (0.72) |  |
| A-05 | dev | openmcp | 0 | correct | json | correct (0.80) |  |
| A-05 | dev | pipeworx | 0 | correct | json | correct (0.50) | open |
| A-05 | dev | statcan2 | 0 | correct | json | correct (0.80) |  |
| C-01 | dev | arose26 | 0 | correct | json | partial (0.75) | open |
| C-01 | dev | canada_data_agent | 0 | correct | json | partial (0.75) | open |
| C-01 | dev | candata_mcp | 0 | correct | json | correct (0.93) |  |
| C-01 | dev | maplestats-local | 0 | correct | json | correct (0.90) |  |
| C-01 | dev | maplestats_hosted | 0 | correct | json | correct (0.93) |  |
| C-01 | dev | mcp_canada | 0 | correct | json | correct (0.90) |  |
| C-01 | dev | mcp_statcan | 0 | correct | json | correct (0.90) |  |
| C-01 | dev | no_tools | 0 | hallucinated | regex | abstained (0.96) | open |
| C-01 | dev | opencanada | 0 | correct | json | correct (0.93) |  |
| C-01 | dev | openmcp | 0 | correct | json | correct (0.88) |  |
| C-01 | dev | pipeworx | 0 | correct | json | correct (0.85) |  |
| C-01 | dev | statcan2 | 0 | hallucinated | regex | abstained (0.90) | open |
| C-05 | dev | arose26 | 0 | correct | json | correct (0.72) |  |
| C-05 | dev | arose26 | 1 | correct | json | partial (0.40) | open |
| C-05 | dev | arose26 | 2 | correct | json | correct (0.93) |  |
| C-05 | dev | canada_data_agent | 0 | abstained | json | abstained (0.93) |  |
| C-05 | dev | canada_data_agent | 1 | partial | regex | hallucinated (0.90) | open |
| C-05 | dev | canada_data_agent | 2 | partial | regex | hallucinated (0.90) | open |
| C-05 | dev | candata_mcp | 0 | correct | json | correct (0.93) |  |
| C-05 | dev | candata_mcp | 1 | partial | regex | hallucinated (0.93) | open |
| C-05 | dev | candata_mcp | 2 | partial | regex | hallucinated (0.90) | open |
| C-05 | dev | maplestats-local | 0 | correct | json | correct (0.93) |  |
| C-05 | dev | maplestats-local | 1 | correct | json | correct (0.90) |  |
| C-05 | dev | maplestats-local | 2 | partial | regex | hallucinated (0.60) | open |
| C-05 | dev | maplestats_hosted | 0 | correct | json | correct (0.90) |  |
| C-05 | dev | maplestats_hosted | 1 | partial* | regex | hallucinated (0.90) | settled |
| C-05 | dev | maplestats_hosted | 2 | correct | json | correct (0.90) |  |
| C-05 | dev | mcp_canada | 0 | correct | json | correct (0.93) |  |
| C-05 | dev | mcp_canada | 1 | correct | json | correct (0.90) |  |
| C-05 | dev | mcp_canada | 2 | correct | json | correct (0.90) |  |
| C-05 | dev | mcp_statcan | 0 | correct | json | correct (0.90) |  |
| C-05 | dev | mcp_statcan | 1 | correct | json | correct (0.93) |  |
| C-05 | dev | mcp_statcan | 2 | correct | json | correct (0.93) |  |
| C-05 | dev | no_tools | 0 | abstained | json | abstained (0.95) |  |
| C-05 | dev | no_tools | 1 | hallucinated | regex | abstained (0.96) | open |
| C-05 | dev | no_tools | 2 | abstained | json | abstained (0.93) |  |
| C-05 | dev | opencanada | 0 | partial | regex | hallucinated (0.93) | open |
| C-05 | dev | opencanada | 1 | partial | regex | hallucinated (0.90) | open |
| C-05 | dev | opencanada | 2 | partial | regex | hallucinated (0.85) | open |
| C-05 | dev | openmcp | 0 | correct | json | correct (0.90) |  |
| C-05 | dev | openmcp | 1 | correct | json | correct (0.93) |  |
| C-05 | dev | openmcp | 2 | correct | json | correct (0.93) |  |
| C-05 | dev | pipeworx | 0 | correct | json | correct (0.93) |  |
| C-05 | dev | pipeworx | 1 | correct | json | correct (0.93) |  |
| C-05 | dev | pipeworx | 2 | correct | json | correct (0.93) |  |
| C-05 | dev | statcan2 | 0 | partial | regex | abstained (0.85) | open |
| C-05 | dev | statcan2 | 1 | partial | regex | abstained (0.85) | open |
| C-05 | dev | statcan2 | 2 | partial | regex | abstained (0.72) | open |
| C-09 | dev | arose26 | 0 | correct | json | correct (0.90) |  |
| C-09 | dev | canada_data_agent | 0 | correct | json | correct (0.80) |  |
| C-09 | dev | candata_mcp | 0 | correct | json | correct (0.85) |  |
| C-09 | dev | maplestats-local | 0 | correct | json | correct (0.85) |  |
| C-09 | dev | maplestats_hosted | 0 | correct | json | correct (0.85) |  |
| C-09 | dev | mcp_canada | 0 | correct | json | correct (0.85) |  |
| C-09 | dev | mcp_statcan | 0 | correct | json | correct (0.80) |  |
| C-09 | dev | no_tools | 0 | abstained | json | abstained (0.95) |  |
| C-09 | dev | opencanada | 0 | hallucinated | regex | correct (0.68) | open |
| C-09 | dev | openmcp | 0 | correct | json | correct (0.82) |  |
| C-09 | dev | pipeworx | 0 | correct | json | correct (0.85) |  |
| C-09 | dev | statcan2 | 0 | abstained | regex | abstained (0.85) |  |
| C-10 | dev | arose26 | 0 | correct | json | correct (0.93) |  |
| C-10 | dev | canada_data_agent | 0 | correct | json | correct (0.90) |  |
| C-10 | dev | candata_mcp | 0 | correct | json | correct (0.88) |  |
| C-10 | dev | maplestats-local | 0 | correct | json | correct (0.90) |  |
| C-10 | dev | maplestats_hosted | 0 | correct | json | correct (0.90) |  |
| C-10 | dev | mcp_canada | 0 | correct | json | correct (0.93) |  |
| C-10 | dev | mcp_statcan | 0 | correct | json | correct (0.85) |  |
| C-10 | dev | no_tools | 0 | abstained | json | abstained (0.93) |  |
| C-10 | dev | opencanada | 0 | correct | json | correct (0.90) |  |
| C-10 | dev | openmcp | 0 | correct | json | correct (0.90) |  |
| C-10 | dev | pipeworx | 0 | correct | json | correct (0.93) |  |
| C-10 | dev | statcan2 | 0 | abstained | regex | abstained (0.93) |  |
| C-11 | dev | arose26 | 0 | correct | json | correct (0.90) |  |
| C-11 | dev | canada_data_agent | 0 | abstained | json | abstained (0.95) |  |
| C-11 | dev | candata_mcp | 0 | correct | json | correct (0.85) |  |
| C-11 | dev | maplestats-local | 0 | correct | json | correct (0.90) |  |
| C-11 | dev | maplestats_hosted | 0 | correct | json | correct (0.93) |  |
| C-11 | dev | mcp_canada | 0 | correct | json | correct (0.85) |  |
| C-11 | dev | mcp_statcan | 0 | correct | json | correct (0.85) |  |
| C-11 | dev | no_tools | 0 | hallucinated | regex | abstained (0.96) | open |
| C-11 | dev | opencanada | 0 | correct | json | correct (0.90) |  |
| C-11 | dev | openmcp | 0 | correct | json | correct (0.90) |  |
| C-11 | dev | pipeworx | 0 | correct | json | correct (0.85) |  |
| C-11 | dev | statcan2 | 0 | hallucinated | regex | hallucinated (0.93) |  |
| C-16 | dev | arose26 | 0 | correct | regex | correct (0.55) | open |
| C-16 | dev | canada_data_agent | 0 | abstained | json | abstained (0.93) |  |
| C-16 | dev | candata_mcp | 0 | correct | json | partial (0.50) | open |
| C-16 | dev | maplestats-local | 0 | correct | json | correct (0.93) |  |
| C-16 | dev | maplestats_hosted | 0 | hallucinated | regex | hallucinated (0.93) |  |
| C-16 | dev | mcp_canada | 0 | abstained | json | abstained (0.93) |  |
| C-16 | dev | mcp_statcan | 0 | correct | regex | correct (0.55) | open |
| C-16 | dev | no_tools | 0 | abstained | json | abstained (0.95) |  |
| C-16 | dev | opencanada | 0 | correct | json | correct (0.90) |  |
| C-16 | dev | openmcp | 0 | hallucinated | regex | hallucinated (0.93) |  |
| C-16 | dev | pipeworx | 0 | correct | json | correct (0.90) |  |
| C-16 | dev | statcan2 | 0 | abstained | regex | abstained (0.90) |  |
| C-19 | dev | arose26 | 0 | correct | json | correct (0.93) |  |
| C-19 | dev | canada_data_agent | 0 | abstained | json | abstained (0.93) |  |
| C-19 | dev | candata_mcp | 0 | correct | json | correct (0.93) |  |
| C-19 | dev | maplestats-local | 0 | correct | json | correct (0.90) |  |
| C-19 | dev | maplestats_hosted | 0 | correct | json | correct (0.80) |  |
| C-19 | dev | mcp_canada | 0 | correct | json | correct (0.93) |  |
| C-19 | dev | mcp_statcan | 0 | correct | json | correct (0.85) |  |
| C-19 | dev | no_tools | 0 | abstained | regex | – |  |
| C-19 | dev | opencanada | 0 | correct | json | abstained (0.85) | open |
| C-19 | dev | openmcp | 0 | correct | json | correct (0.85) |  |
| C-19 | dev | pipeworx | 0 | correct | json | correct (0.90) |  |
| C-19 | dev | statcan2 | 0 | abstained | json | abstained (0.93) |  |
| C-21 | dev | arose26 | 0 | correct | json | correct (0.72) |  |
| C-21 | dev | canada_data_agent | 0 | abstained | json | abstained (0.93) |  |
| C-21 | dev | candata_mcp | 0 | correct | json | correct (0.93) |  |
| C-21 | dev | maplestats-local | 0 | correct | json | correct (0.93) |  |
| C-21 | dev | maplestats_hosted | 0 | correct* | regex | hallucinated (0.93) |  |
| C-21 | dev | mcp_canada | 0 | correct | json | correct (0.93) |  |
| C-21 | dev | mcp_statcan | 0 | abstained | json | abstained (0.93) |  |
| C-21 | dev | no_tools | 0 | hallucinated | regex | abstained (0.96) | open |
| C-21 | dev | opencanada | 0 | correct | json | correct (0.90) |  |
| C-21 | dev | openmcp | 0 | hallucinated | regex | hallucinated (0.93) |  |
| C-21 | dev | pipeworx | 0 | correct | json | correct (0.95) |  |
| C-21 | dev | statcan2 | 0 | abstained | regex | abstained (0.85) |  |
| C-24 | dev | arose26 | 0 | correct | regex | correct (0.85) |  |
| C-24 | dev | canada_data_agent | 0 | correct | regex | correct (0.85) |  |
| C-24 | dev | candata_mcp | 0 | correct | regex | correct (0.85) |  |
| C-24 | dev | maplestats-local | 0 | correct | regex | correct (0.80) |  |
| C-24 | dev | maplestats_hosted | 0 | partial | regex | hallucinated (0.60) | open |
| C-24 | dev | mcp_canada | 0 | correct | regex | correct (0.78) |  |
| C-24 | dev | mcp_statcan | 0 | correct | regex | correct (0.78) |  |
| C-24 | dev | no_tools | 0 | abstained | json | partial (0.85) | open |
| C-24 | dev | opencanada | 0 | correct | regex | correct (0.72) |  |
| C-24 | dev | openmcp | 0 | partial | regex | correct (0.60) | open |
| C-24 | dev | pipeworx | 0 | correct | regex | correct (0.85) |  |
| C-24 | dev | statcan2 | 0 | partial | regex | partial (0.72) |  |
| M-04 | dev | arose26 | 0 | correct | json | correct (0.90) |  |
| M-04 | dev | canada_data_agent | 0 | correct | json | correct (0.90) |  |
| M-04 | dev | candata_mcp | 0 | correct | json | correct (0.90) |  |
| M-04 | dev | maplestats-local | 0 | correct | json | correct (0.90) |  |
| M-04 | dev | maplestats_hosted | 0 | correct | json | correct (0.90) |  |
| M-04 | dev | mcp_canada | 0 | correct | json | correct (0.90) |  |
| M-04 | dev | mcp_statcan | 0 | correct | json | correct (0.90) |  |
| M-04 | dev | no_tools | 0 | abstained | regex | abstained (0.95) |  |
| M-04 | dev | opencanada | 0 | correct | json | correct (0.90) |  |
| M-04 | dev | openmcp | 0 | correct | json | correct (0.90) |  |
| M-04 | dev | pipeworx | 0 | correct | json | correct (0.90) |  |
| M-04 | dev | statcan2 | 0 | correct | json | correct (0.90) |  |
| M-09 | dev | arose26 | 0 | correct | regex | correct (0.93) |  |
| M-09 | dev | canada_data_agent | 0 | correct | regex | correct (0.90) |  |
| M-09 | dev | candata_mcp | 0 | correct | regex | correct (0.90) |  |
| M-09 | dev | maplestats-local | 0 | correct | json | correct (0.93) |  |
| M-09 | dev | maplestats_hosted | 0 | correct | regex | correct (0.90) |  |
| M-09 | dev | mcp_canada | 0 | partial | regex | correct (0.90) | open |
| M-09 | dev | mcp_statcan | 0 | hallucinated | regex | hallucinated (0.93) |  |
| M-09 | dev | no_tools | 0 | hallucinated | regex | abstained (0.96) | open |
| M-09 | dev | opencanada | 0 | correct | regex | correct (0.85) |  |
| M-09 | dev | openmcp | 0 | correct | json | correct (0.88) |  |
| M-09 | dev | pipeworx | 0 | correct | regex | correct (0.93) |  |
| M-09 | dev | statcan2 | 0 | abstained | regex | abstained (0.93) |  |
| M-11 | dev | arose26 | 0 | correct | json | correct (0.93) |  |
| M-11 | dev | canada_data_agent | 0 | correct | json | correct (0.90) |  |
| M-11 | dev | candata_mcp | 0 | correct | json | correct (0.95) |  |
| M-11 | dev | maplestats-local | 0 | correct | json | correct (0.90) |  |
| M-11 | dev | maplestats_hosted | 0 | correct | json | correct (0.93) |  |
| M-11 | dev | mcp_canada | 0 | correct | json | correct (0.95) |  |
| M-11 | dev | mcp_statcan | 0 | correct | json | correct (0.85) |  |
| M-11 | dev | no_tools | 0 | hallucinated | regex | abstained (0.95) | open |
| M-11 | dev | opencanada | 0 | correct | json | correct (0.93) |  |
| M-11 | dev | openmcp | 0 | correct | json | correct (0.95) |  |
| M-11 | dev | pipeworx | 0 | correct | json | correct (0.90) |  |
| M-11 | dev | statcan2 | 0 | abstained | regex | abstained (0.93) |  |
| M-15 | dev | arose26 | 0 | correct | regex | correct (0.55) | open |
| M-15 | dev | canada_data_agent | 0 | abstained | json | partial (0.50) | open |
| M-15 | dev | candata_mcp | 0 | correct | regex | correct (0.50) | open |
| M-15 | dev | maplestats-local | 0 | correct | regex | partial (0.65) | open |
| M-15 | dev | maplestats_hosted | 0 | partial* | regex | partial (0.60) | settled |
| M-15 | dev | mcp_canada | 0 | hallucinated | regex | partial (0.72) | open |
| M-15 | dev | mcp_statcan | 0 | hallucinated | regex | partial (0.65) | open |
| M-15 | dev | no_tools | 0 | abstained | json | partial (0.60) | open |
| M-15 | dev | opencanada | 0 | hallucinated | regex | partial (0.60) | open |
| M-15 | dev | openmcp | 0 | partial* | regex | correct (0.68) | settled |
| M-15 | dev | pipeworx | 0 | hallucinated | regex | correct (0.60) | open |
| M-15 | dev | statcan2 | 0 | hallucinated | regex | abstained (0.60) | open |
| N-01 | test | arose26 | 0 | correct* | regex | hallucinated (0.93) |  |
| N-01 | test | canada_data_agent | 0 | correct* | regex | hallucinated (0.96) |  |
| N-01 | test | candata_mcp | 0 | correct* | regex | hallucinated (0.95) |  |
| N-01 | test | maplestats-local | 0 | correct | json | correct (0.90) |  |
| N-01 | test | maplestats_hosted | 0 | correct | json | correct (0.90) |  |
| N-01 | test | mcp_canada | 0 | correct* | regex | hallucinated (0.93) |  |
| N-01 | test | mcp_statcan | 0 | correct* | regex | hallucinated (0.95) |  |
| N-01 | test | no_tools | 0 | hallucinated | regex | abstained (0.96) | open |
| N-01 | test | opencanada | 0 | correct* | regex | hallucinated (0.95) |  |
| N-01 | test | openmcp | 0 | correct | json | correct (0.88) |  |
| N-01 | test | pipeworx | 0 | correct* | regex | hallucinated (0.93) |  |
| N-01 | test | statcan2 | 0 | abstained | regex | abstained (0.80) |  |
| N-02 | test | arose26 | 0 | correct | json | correct (0.93) |  |
| N-02 | test | canada_data_agent | 0 | correct | json | correct (0.93) |  |
| N-02 | test | candata_mcp | 0 | correct | json | correct (0.93) |  |
| N-02 | test | maplestats-local | 0 | correct | json | correct (0.90) |  |
| N-02 | test | maplestats_hosted | 0 | correct | json | correct (0.90) |  |
| N-02 | test | mcp_canada | 0 | correct | json | correct (0.93) |  |
| N-02 | test | mcp_statcan | 0 | correct | json | correct (0.93) |  |
| N-02 | test | no_tools | 0 | hallucinated | regex | abstained (0.96) | open |
| N-02 | test | opencanada | 0 | correct | json | correct (0.88) |  |
| N-02 | test | openmcp | 0 | correct | json | correct (0.93) |  |
| N-02 | test | pipeworx | 0 | correct | json | correct (0.93) |  |
| N-02 | test | statcan2 | 0 | correct | json | correct (0.93) |  |
| N-03 | test | arose26 | 0 | correct* | regex | hallucinated (0.60) | settled |
| N-03 | test | canada_data_agent | 0 | correct* | regex | hallucinated (0.72) |  |
| N-03 | test | candata_mcp | 0 | correct* | regex | hallucinated (0.72) |  |
| N-03 | test | maplestats-local | 0 | abstained | json | abstained (0.93) |  |
| N-03 | test | maplestats_hosted | 0 | correct | json | correct (0.90) |  |
| N-03 | test | mcp_canada | 0 | correct* | regex | hallucinated (0.80) |  |
| N-03 | test | mcp_statcan | 0 | correct* | regex | hallucinated (0.72) |  |
| N-03 | test | no_tools | 0 | hallucinated | regex | abstained (0.95) | open |
| N-03 | test | opencanada | 0 | correct* | regex | hallucinated (0.72) |  |
| N-03 | test | openmcp | 0 | correct | json | correct (0.90) |  |
| N-03 | test | pipeworx | 0 | correct* | regex | hallucinated (0.85) |  |
| N-03 | test | statcan2 | 0 | abstained | regex | abstained (0.85) |  |
| N-04 | test | arose26 | 0 | correct | json | correct (0.93) |  |
| N-04 | test | canada_data_agent | 0 | correct | json | correct (0.90) |  |
| N-04 | test | candata_mcp | 0 | correct | json | correct (0.93) |  |
| N-04 | test | maplestats-local | 0 | abstained | json | abstained (0.93) |  |
| N-04 | test | maplestats_hosted | 0 | correct | json | correct (0.93) |  |
| N-04 | test | mcp_canada | 0 | correct | json | correct (0.90) |  |
| N-04 | test | mcp_statcan | 0 | correct | json | correct (0.93) |  |
| N-04 | test | no_tools | 0 | abstained | json | abstained (0.93) |  |
| N-04 | test | opencanada | 0 | abstained | json | abstained (0.80) |  |
| N-04 | test | openmcp | 0 | hallucinated | regex | hallucinated (0.95) |  |
| N-04 | test | pipeworx | 0 | correct | json | correct (0.93) |  |
| N-04 | test | statcan2 | 0 | hallucinated | regex | hallucinated (0.93) |  |
| N-05 | test | arose26 | 0 | correct | json | correct (0.90) |  |
| N-05 | test | canada_data_agent | 0 | correct | json | correct (0.88) |  |
| N-05 | test | candata_mcp | 0 | correct | json | correct (0.93) |  |
| N-05 | test | maplestats-local | 0 | abstained | json | abstained (0.93) |  |
| N-05 | test | maplestats_hosted | 0 | correct | json | correct (0.93) |  |
| N-05 | test | mcp_canada | 0 | correct | json | correct (0.93) |  |
| N-05 | test | mcp_statcan | 0 | correct | json | correct (0.90) |  |
| N-05 | test | no_tools | 0 | abstained | json | abstained (0.93) |  |
| N-05 | test | opencanada | 0 | correct | json | correct (0.93) |  |
| N-05 | test | openmcp | 0 | correct | json | correct (0.88) |  |
| N-05 | test | pipeworx | 0 | correct | json | correct (0.90) |  |
| N-05 | test | statcan2 | 0 | hallucinated | regex | abstained (0.80) | open |
| N-06 | test | arose26 | 0 | correct | regex | correct (0.93) |  |
| N-06 | test | canada_data_agent | 0 | correct | regex | correct (0.85) |  |
| N-06 | test | candata_mcp | 0 | correct | regex | correct (0.95) |  |
| N-06 | test | maplestats-local | 0 | correct | regex | abstained (0.80) | open |
| N-06 | test | maplestats_hosted | 0 | correct | regex | correct (0.93) |  |
| N-06 | test | mcp_canada | 0 | correct | regex | correct (0.85) |  |
| N-06 | test | mcp_statcan | 0 | correct | regex | correct (0.93) |  |
| N-06 | test | no_tools | 0 | abstained | json | correct (0.45) | open |
| N-06 | test | opencanada | 0 | correct | regex | correct (0.90) |  |
| N-06 | test | openmcp | 0 | correct | regex | correct (0.93) |  |
| N-06 | test | pipeworx | 0 | correct | regex | correct (0.90) |  |
| N-06 | test | statcan2 | 0 | correct | regex | correct (0.92) |  |
| N-07 | test | arose26 | 0 | correct | json | correct (0.85) |  |
| N-07 | test | canada_data_agent | 0 | correct | json | correct (0.90) |  |
| N-07 | test | candata_mcp | 0 | correct | json | correct (0.88) |  |
| N-07 | test | maplestats-local | 0 | correct | json | correct (0.90) |  |
| N-07 | test | maplestats_hosted | 0 | correct | json | correct (0.90) |  |
| N-07 | test | mcp_canada | 0 | correct | json | correct (0.85) |  |
| N-07 | test | mcp_statcan | 0 | correct | json | correct (0.80) |  |
| N-07 | test | no_tools | 0 | correct | json | correct (0.85) |  |
| N-07 | test | opencanada | 0 | correct | json | correct (0.90) |  |
| N-07 | test | openmcp | 0 | correct | json | correct (0.88) |  |
| N-07 | test | pipeworx | 0 | correct | json | correct (0.90) |  |
| N-07 | test | statcan2 | 0 | correct | json | correct (0.88) |  |
| N-08 | test | arose26 | 0 | abstained | json | abstained (0.80) |  |
| N-08 | test | canada_data_agent | 0 | hallucinated | regex | hallucinated (0.80) |  |
| N-08 | test | candata_mcp | 0 | abstained | json | partial (0.50) | open |
| N-08 | test | maplestats-local | 0 | correct | json | correct (0.88) |  |
| N-08 | test | maplestats_hosted | 0 | correct | json | correct (0.90) |  |
| N-08 | test | mcp_canada | 0 | hallucinated | regex | abstained (0.60) | open |
| N-08 | test | mcp_statcan | 0 | hallucinated | regex | hallucinated (0.80) |  |
| N-08 | test | no_tools | 0 | abstained | json | abstained (0.70) |  |
| N-08 | test | opencanada | 0 | abstained | json | partial (0.68) | open |
| N-08 | test | openmcp | 0 | partial* | json | partial (0.72) | settled |
| N-08 | test | pipeworx | 0 | abstained | json | abstained (0.93) |  |
| N-08 | test | statcan2 | 0 | abstained | regex | partial (0.80) | open |
| N-09 | test | arose26 | 0 | correct | json | correct (0.72) |  |
| N-09 | test | canada_data_agent | 0 | correct | json | correct (0.88) |  |
| N-09 | test | candata_mcp | 0 | correct | json | correct (0.85) |  |
| N-09 | test | maplestats-local | 0 | correct | json | correct (0.80) |  |
| N-09 | test | maplestats_hosted | 0 | correct | json | correct (0.85) |  |
| N-09 | test | mcp_canada | 0 | correct | json | correct (0.85) |  |
| N-09 | test | mcp_statcan | 0 | correct | json | correct (0.88) |  |
| N-09 | test | no_tools | 0 | correct | json | correct (0.93) |  |
| N-09 | test | opencanada | 0 | correct | json | correct (0.85) |  |
| N-09 | test | openmcp | 0 | correct | json | correct (0.90) |  |
| N-09 | test | pipeworx | 0 | correct | json | correct (0.85) |  |
| N-09 | test | statcan2 | 0 | correct | json | correct (0.85) |  |
| N-10 | test | arose26 | 0 | abstained | json | abstained (0.85) |  |
| N-10 | test | canada_data_agent | 0 | abstained | json | abstained (0.90) |  |
| N-10 | test | candata_mcp | 0 | correct | json | correct (0.88) |  |
| N-10 | test | maplestats-local | 0 | correct | json | correct (0.93) |  |
| N-10 | test | maplestats_hosted | 0 | correct | json | correct (0.90) |  |
| N-10 | test | mcp_canada | 0 | abstained | json | abstained (0.55) | open |
| N-10 | test | mcp_statcan | 0 | correct | json | correct (0.88) |  |
| N-10 | test | no_tools | 0 | abstained | json | abstained (0.85) |  |
| N-10 | test | opencanada | 0 | correct | json | correct (0.90) |  |
| N-10 | test | openmcp | 0 | abstained | regex | abstained (0.90) |  |
| N-10 | test | pipeworx | 0 | abstained | json | abstained (0.85) |  |
| N-10 | test | statcan2 | 0 | abstained | regex | abstained (0.90) |  |
| N-11 | dev | arose26 | 0 | abstained | regex | abstained (0.90) |  |
| N-11 | dev | canada_data_agent | 0 | abstained | json | abstained (0.90) |  |
| N-11 | dev | candata_mcp | 0 | abstained | regex | abstained (0.93) |  |
| N-11 | dev | maplestats-local | 0 | correct | json | correct (0.93) |  |
| N-11 | dev | maplestats_hosted | 0 | abstained* | regex | abstained (0.90) | settled |
| N-11 | dev | mcp_canada | 0 | hallucinated | regex | abstained (0.93) | open |
| N-11 | dev | mcp_statcan | 0 | abstained | regex | abstained (0.80) |  |
| N-11 | dev | no_tools | 0 | abstained | json | abstained (0.90) |  |
| N-11 | dev | opencanada | 0 | abstained | regex | abstained (0.90) |  |
| N-11 | dev | openmcp | 0 | abstained | regex | abstained (0.85) |  |
| N-11 | dev | pipeworx | 0 | abstained | json | abstained (0.90) |  |
| N-11 | dev | statcan2 | 0 | abstained | json | abstained (0.85) |  |
| N-12 | test | arose26 | 0 | correct | json | correct (0.90) |  |
| N-12 | test | canada_data_agent | 0 | abstained | json | abstained (0.93) |  |
| N-12 | test | candata_mcp | 0 | abstained | json | abstained (0.93) |  |
| N-12 | test | maplestats-local | 0 | correct | json | correct (0.95) |  |
| N-12 | test | maplestats_hosted | 0 | correct | json | correct (0.96) |  |
| N-12 | test | mcp_canada | 0 | correct | json | correct (0.93) |  |
| N-12 | test | mcp_statcan | 0 | abstained | json | abstained (0.90) |  |
| N-12 | test | no_tools | 0 | abstained | json | abstained (0.90) |  |
| N-12 | test | opencanada | 0 | correct | json | correct (0.93) |  |
| N-12 | test | openmcp | 0 | correct | regex | correct (0.95) |  |
| N-12 | test | pipeworx | 0 | correct | regex | correct (0.95) |  |
| N-12 | test | statcan2 | 0 | abstained | regex | abstained (0.90) |  |
| N-13 | test | arose26 | 0 | correct | json | correct (0.93) |  |
| N-13 | test | canada_data_agent | 0 | hallucinated | regex | abstained (0.85) | open |
| N-13 | test | candata_mcp | 0 | correct | json | correct (0.95) |  |
| N-13 | test | maplestats-local | 0 | correct | json | partial (0.72) | open |
| N-13 | test | maplestats_hosted | 0 | correct | json | correct (0.93) |  |
| N-13 | test | mcp_canada | 0 | correct | json | correct (0.95) |  |
| N-13 | test | mcp_statcan | 0 | correct | json | correct (0.93) |  |
| N-13 | test | no_tools | 0 | hallucinated | regex | abstained (0.95) | open |
| N-13 | test | opencanada | 0 | correct | json | correct (0.95) |  |
| N-13 | test | openmcp | 0 | partial* | json | partial (0.80) | settled |
| N-13 | test | pipeworx | 0 | correct | json | partial (0.80) | open |
| N-13 | test | statcan2 | 0 | abstained | regex | abstained (0.93) |  |
| N-14 | test | arose26 | 0 | correct | json | correct (0.68) | open |
| N-14 | test | canada_data_agent | 0 | abstained | json | abstained (0.90) |  |
| N-14 | test | candata_mcp | 0 | correct | json | correct (0.60) | open |
| N-14 | test | maplestats-local | 0 | correct | json | correct (0.88) |  |
| N-14 | test | maplestats_hosted | 0 | correct | json | correct (0.82) |  |
| N-14 | test | mcp_canada | 0 | correct | json | correct (0.85) |  |
| N-14 | test | mcp_statcan | 0 | correct | json | correct (0.80) |  |
| N-14 | test | no_tools | 0 | hallucinated | regex | abstained (0.93) | open |
| N-14 | test | opencanada | 0 | correct | json | correct (0.68) | open |
| N-14 | test | openmcp | 0 | correct | json | correct (0.93) |  |
| N-14 | test | pipeworx | 0 | correct | json | correct (0.72) |  |
| N-14 | test | statcan2 | 0 | correct | json | correct (0.88) |  |
| N-15 | dev | arose26 | 0 | correct | json | hallucinated (0.60) | open |
| N-15 | dev | canada_data_agent | 0 | correct | json | hallucinated (0.72) | open |
| N-15 | dev | candata_mcp | 0 | correct | json | hallucinated (0.70) | open |
| N-15 | dev | maplestats-local | 0 | correct | json | correct (0.93) |  |
| N-15 | dev | maplestats_hosted | 0 | partial* | regex | partial (0.50) | settled |
| N-15 | dev | mcp_canada | 0 | abstained | json | partial (0.50) | open |
| N-15 | dev | mcp_statcan | 0 | correct | json | correct (0.60) | open |
| N-15 | dev | no_tools | 0 | correct | json | partial (0.50) | open |
| N-15 | dev | opencanada | 0 | correct | json | hallucinated (0.55) | open |
| N-15 | dev | openmcp | 0 | hallucinated* | json | hallucinated (0.72) | settled |
| N-15 | dev | pipeworx | 0 | correct | json | partial (0.55) | open |
| N-15 | dev | statcan2 | 0 | correct | regex | partial (0.55) | open |
| N-16 | test | arose26 | 0 | correct | json | correct (0.93) |  |
| N-16 | test | canada_data_agent | 0 | correct | json | correct (0.88) |  |
| N-16 | test | candata_mcp | 0 | correct | json | correct (0.93) |  |
| N-16 | test | maplestats-local | 0 | correct | json | partial (0.50) | open |
| N-16 | test | maplestats_hosted | 0 | correct | json | correct (0.92) |  |
| N-16 | test | mcp_canada | 0 | correct | json | correct (0.90) |  |
| N-16 | test | mcp_statcan | 0 | correct | json | correct (0.93) |  |
| N-16 | test | no_tools | 0 | abstained | json | abstained (0.93) |  |
| N-16 | test | opencanada | 0 | hallucinated | regex | abstained (0.93) | open |
| N-16 | test | openmcp | 0 | correct | json | correct (0.93) |  |
| N-16 | test | pipeworx | 0 | correct | json | correct (0.95) |  |
| N-16 | test | statcan2 | 0 | correct | json | correct (0.90) |  |
| N-17 | test | arose26 | 0 | abstained | json | abstained (0.93) |  |
| N-17 | test | canada_data_agent | 0 | abstained | json | abstained (0.80) |  |
| N-17 | test | candata_mcp | 0 | hallucinated | regex | partial (0.60) | open |
| N-17 | test | maplestats-local | 0 | correct | json | correct (0.90) |  |
| N-17 | test | maplestats_hosted | 0 | correct | json | correct (0.90) |  |
| N-17 | test | mcp_canada | 0 | hallucinated | regex | abstained (0.60) | open |
| N-17 | test | mcp_statcan | 0 | abstained | json | abstained (0.96) |  |
| N-17 | test | no_tools | 0 | hallucinated | regex | abstained (0.96) | open |
| N-17 | test | opencanada | 0 | abstained | json | abstained (0.93) |  |
| N-17 | test | openmcp | 0 | partial* | regex | partial (0.62) | settled |
| N-17 | test | pipeworx | 0 | abstained | json | abstained (0.96) |  |
| N-17 | test | statcan2 | 0 | abstained | json | partial (0.55) | open |
| N-18 | test | arose26 | 0 | abstained | json | abstained (0.93) |  |
| N-18 | test | canada_data_agent | 0 | abstained | json | abstained (0.90) |  |
| N-18 | test | candata_mcp | 0 | correct | json | correct (0.72) |  |
| N-18 | test | maplestats-local | 0 | correct | json | correct (0.93) |  |
| N-18 | test | maplestats_hosted | 0 | correct | json | correct (0.93) |  |
| N-18 | test | mcp_canada | 0 | correct | json | correct (0.90) |  |
| N-18 | test | mcp_statcan | 0 | abstained | json | abstained (0.93) |  |
| N-18 | test | no_tools | 0 | abstained | json | abstained (0.93) |  |
| N-18 | test | opencanada | 0 | abstained | json | abstained (0.85) |  |
| N-18 | test | openmcp | 0 | partial* | regex | partial (0.60) | settled |
| N-18 | test | pipeworx | 0 | abstained | json | abstained (0.93) |  |
| N-18 | test | statcan2 | 0 | abstained | json | abstained (0.93) |  |
| N-19 | dev | arose26 | 0 | abstained | json | abstained (0.93) |  |
| N-19 | dev | canada_data_agent | 0 | abstained | json | correct (0.62) | open |
| N-19 | dev | candata_mcp | 0 | abstained | json | abstained (0.93) |  |
| N-19 | dev | maplestats-local | 0 | correct | json | correct (0.93) |  |
| N-19 | dev | maplestats_hosted | 0 | partial* | regex | partial (0.60) | settled |
| N-19 | dev | mcp_canada | 0 | hallucinated | regex | partial (0.72) | open |
| N-19 | dev | mcp_statcan | 0 | abstained | json | partial (0.68) | open |
| N-19 | dev | no_tools | 0 | hallucinated | regex | abstained (0.95) | open |
| N-19 | dev | opencanada | 0 | abstained | json | abstained (0.93) |  |
| N-19 | dev | openmcp | 0 | partial* | regex | partial (0.80) | settled |
| N-19 | dev | pipeworx | 0 | abstained | json | abstained (0.93) |  |
| N-19 | dev | statcan2 | 0 | abstained | json | abstained (0.85) |  |
| N-20 | test | arose26 | 0 | abstained | json | abstained (0.85) |  |
| N-20 | test | canada_data_agent | 0 | abstained | json | abstained (0.90) |  |
| N-20 | test | candata_mcp | 0 | hallucinated | regex | partial (0.80) | open |
| N-20 | test | maplestats-local | 0 | correct | json | correct (0.88) |  |
| N-20 | test | maplestats_hosted | 0 | correct | json | correct (0.85) |  |
| N-20 | test | mcp_canada | 0 | hallucinated | regex | partial (0.60) | open |
| N-20 | test | mcp_statcan | 0 | abstained | json | partial (0.50) | open |
| N-20 | test | no_tools | 0 | hallucinated | regex | abstained (0.96) | open |
| N-20 | test | opencanada | 0 | abstained | json | abstained (0.93) |  |
| N-20 | test | openmcp | 0 | partial* | regex | partial (0.75) | settled |
| N-20 | test | pipeworx | 0 | correct | json | partial (0.72) | open |
| N-20 | test | statcan2 | 0 | abstained | json | abstained (0.93) |  |
| N-21 | test | arose26 | 0 | abstained | json | abstained (0.93) |  |
| N-21 | test | canada_data_agent | 0 | correct | json | correct (0.72) |  |
| N-21 | test | candata_mcp | 0 | abstained | json | abstained (0.90) |  |
| N-21 | test | maplestats-local | 0 | correct | json | correct (0.95) |  |
| N-21 | test | maplestats_hosted | 0 | correct | json | correct (0.93) |  |
| N-21 | test | mcp_canada | 0 | abstained | json | abstained (0.93) |  |
| N-21 | test | mcp_statcan | 0 | abstained | json | abstained (0.90) |  |
| N-21 | test | no_tools | 0 | hallucinated | regex | abstained (0.96) | open |
| N-21 | test | opencanada | 0 | correct | json | correct (0.93) |  |
| N-21 | test | openmcp | 0 | correct | json | correct (0.93) |  |
| N-21 | test | pipeworx | 0 | abstained | json | abstained (0.90) |  |
| N-21 | test | statcan2 | 0 | correct | json | correct (0.72) |  |
| N-22 | dev | arose26 | 0 | abstained | json | abstained (0.80) |  |
| N-22 | dev | canada_data_agent | 0 | abstained | json | abstained (0.80) |  |
| N-22 | dev | candata_mcp | 0 | abstained | json | abstained (0.85) |  |
| N-22 | dev | maplestats-local | 0 | correct | json | correct (0.85) |  |
| N-22 | dev | maplestats_hosted | 0 | partial* | json | partial (0.72) | settled |
| N-22 | dev | mcp_canada | 0 | abstained | json | abstained (0.80) |  |
| N-22 | dev | mcp_statcan | 0 | abstained | json | abstained (0.85) |  |
| N-22 | dev | no_tools | 0 | abstained | json | abstained (0.85) |  |
| N-22 | dev | opencanada | 0 | correct | json | correct (0.78) |  |
| N-22 | dev | openmcp | 0 | abstained | json | abstained (0.85) |  |
| N-22 | dev | pipeworx | 0 | abstained | json | abstained (0.80) |  |
| N-22 | dev | statcan2 | 0 | abstained | json | abstained (0.80) |  |
| N-23 | test | arose26 | 0 | abstained | json | abstained (0.93) |  |
| N-23 | test | canada_data_agent | 0 | abstained | json | abstained (0.90) |  |
| N-23 | test | candata_mcp | 0 | correct | json | correct (0.88) |  |
| N-23 | test | maplestats-local | 0 | correct | json | correct (0.90) |  |
| N-23 | test | maplestats_hosted | 0 | correct | json | correct (0.85) |  |
| N-23 | test | mcp_canada | 0 | correct | regex | correct (0.90) |  |
| N-23 | test | mcp_statcan | 0 | abstained | json | abstained (0.90) |  |
| N-23 | test | no_tools | 0 | hallucinated | regex | abstained (0.96) | open |
| N-23 | test | opencanada | 0 | abstained | json | abstained (0.90) |  |
| N-23 | test | openmcp | 0 | abstained* | regex | abstained (0.90) | settled |
| N-23 | test | pipeworx | 0 | abstained | json | abstained (0.93) |  |
| N-23 | test | statcan2 | 0 | abstained | json | abstained (0.90) |  |
| N-24 | test | arose26 | 0 | abstained | json | abstained (0.93) |  |
| N-24 | test | canada_data_agent | 0 | abstained | json | abstained (0.93) |  |
| N-24 | test | candata_mcp | 0 | abstained | json | abstained (0.93) |  |
| N-24 | test | maplestats-local | 0 | correct | json | partial (0.60) | open |
| N-24 | test | maplestats_hosted | 0 | correct | json | correct (0.96) |  |
| N-24 | test | mcp_canada | 0 | abstained | json | abstained (0.93) |  |
| N-24 | test | mcp_statcan | 0 | abstained | json | abstained (0.90) |  |
| N-24 | test | no_tools | 0 | abstained | regex | – |  |
| N-24 | test | opencanada | 0 | abstained | json | abstained (0.93) |  |
| N-24 | test | openmcp | 0 | correct | json | correct (0.93) |  |
| N-24 | test | pipeworx | 0 | correct | json | correct (0.93) |  |
| N-24 | test | statcan2 | 0 | abstained | json | abstained (0.90) |  |
| N-25 | test | arose26 | 0 | correct | json | correct (0.90) |  |
| N-25 | test | canada_data_agent | 0 | correct | json | correct (0.85) |  |
| N-25 | test | candata_mcp | 0 | correct | json | correct (0.90) |  |
| N-25 | test | maplestats-local | 0 | correct | json | correct (0.85) |  |
| N-25 | test | maplestats_hosted | 0 | correct | json | correct (0.85) |  |
| N-25 | test | mcp_canada | 0 | correct | json | correct (0.85) |  |
| N-25 | test | mcp_statcan | 0 | correct | json | correct (0.88) |  |
| N-25 | test | no_tools | 0 | correct | json | correct (0.85) |  |
| N-25 | test | opencanada | 0 | correct | json | correct (0.90) |  |
| N-25 | test | openmcp | 0 | correct | json | correct (0.88) |  |
| N-25 | test | pipeworx | 0 | correct | json | correct (0.90) |  |
| N-25 | test | statcan2 | 0 | correct | json | correct (0.88) |  |
| R-01 | dev | arose26 | 0 | abstained | regex | abstained (0.85) |  |
| R-01 | dev | canada_data_agent | 0 | abstained | json | abstained (0.93) |  |
| R-01 | dev | candata_mcp | 0 | correct | json | correct (0.70) |  |
| R-01 | dev | maplestats-local | 0 | correct | json | correct (0.85) |  |
| R-01 | dev | maplestats_hosted | 0 | correct* | json | correct (0.60) | settled |
| R-01 | dev | mcp_canada | 0 | hallucinated | regex | abstained (0.80) | open |
| R-01 | dev | mcp_statcan | 0 | correct | json | correct (0.55) | open |
| R-01 | dev | no_tools | 0 | abstained | json | abstained (0.80) |  |
| R-01 | dev | opencanada | 0 | correct | json | hallucinated (0.80) | open |
| R-01 | dev | openmcp | 0 | correct | json | correct (0.75) |  |
| R-01 | dev | pipeworx | 0 | hallucinated | regex | abstained (0.90) | open |
| R-01 | dev | statcan2 | 0 | hallucinated | regex | abstained (0.93) | open |
| R-03 | dev | arose26 | 0 | abstained | regex | abstained (0.70) |  |
| R-03 | dev | canada_data_agent | 0 | abstained | json | abstained (0.60) | open |
| R-03 | dev | candata_mcp | 0 | hallucinated | regex | hallucinated (0.93) |  |
| R-03 | dev | maplestats-local | 0 | hallucinated | regex | hallucinated (0.93) |  |
| R-03 | dev | maplestats_hosted | 0 | hallucinated | regex | hallucinated (0.95) |  |
| R-03 | dev | mcp_canada | 0 | hallucinated | regex | hallucinated (0.93) |  |
| R-03 | dev | mcp_statcan | 0 | hallucinated | regex | hallucinated (0.93) |  |
| R-03 | dev | no_tools | 0 | abstained | regex | hallucinated (0.80) | open |
| R-03 | dev | opencanada | 0 | hallucinated | regex | hallucinated (0.90) |  |
| R-03 | dev | openmcp | 0 | hallucinated | regex | hallucinated (0.95) |  |
| R-03 | dev | pipeworx | 0 | hallucinated | regex | abstained (0.80) | open |
| R-03 | dev | statcan2 | 0 | abstained | regex | partial (0.60) | open |
| R-04 | dev | arose26 | 0 | abstained | regex | abstained (0.85) |  |
| R-04 | dev | canada_data_agent | 0 | abstained | json | abstained (0.95) |  |
| R-04 | dev | candata_mcp | 0 | correct | json | correct (0.80) |  |
| R-04 | dev | maplestats-local | 0 | correct | json | correct (0.90) |  |
| R-04 | dev | maplestats_hosted | 0 | correct | json | correct (0.93) |  |
| R-04 | dev | mcp_canada | 0 | correct | json | correct (0.90) |  |
| R-04 | dev | mcp_statcan | 0 | correct | json | correct (0.80) |  |
| R-04 | dev | no_tools | 0 | abstained | json | abstained (0.95) |  |
| R-04 | dev | opencanada | 0 | abstained | regex | abstained (0.80) |  |
| R-04 | dev | openmcp | 0 | correct | json | correct (0.90) |  |
| R-04 | dev | pipeworx | 0 | correct | regex | abstained (0.85) | open |
| R-04 | dev | statcan2 | 0 | hallucinated | regex | abstained (0.93) | open |
| R-06 | dev | arose26 | 0 | abstained | json | abstained (0.85) |  |
| R-06 | dev | canada_data_agent | 0 | abstained | json | abstained (0.85) |  |
| R-06 | dev | candata_mcp | 0 | hallucinated | regex | hallucinated (0.85) |  |
| R-06 | dev | maplestats-local | 0 | correct | regex | partial (0.40) | open |
| R-06 | dev | maplestats_hosted | 0 | correct | json | correct (0.85) |  |
| R-06 | dev | mcp_canada | 0 | abstained | json | abstained (0.80) |  |
| R-06 | dev | mcp_statcan | 0 | hallucinated | regex | partial (0.45) | open |
| R-06 | dev | no_tools | 0 | abstained | json | abstained (0.85) |  |
| R-06 | dev | opencanada | 0 | correct | regex | abstained (0.70) | open |
| R-06 | dev | openmcp | 0 | partial* | regex | hallucinated (0.62) | settled |
| R-06 | dev | pipeworx | 0 | abstained | json | partial (0.40) | open |
| R-06 | dev | statcan2 | 0 | abstained | json | abstained (0.85) |  |
| T-02 | dev | arose26 | 0 | correct | regex | partial (0.60) | open |
| T-02 | dev | canada_data_agent | 0 | correct | regex | partial (0.80) | open |
| T-02 | dev | candata_mcp | 0 | abstained | json | partial (0.55) | open |
| T-02 | dev | maplestats-local | 0 | correct | json | correct (0.93) |  |
| T-02 | dev | maplestats_hosted | 0 | correct | json | correct (0.93) |  |
| T-02 | dev | mcp_canada | 0 | correct | json | correct (0.80) |  |
| T-02 | dev | mcp_statcan | 0 | hallucinated | regex | partial (0.80) | open |
| T-02 | dev | no_tools | 0 | correct | json | correct (0.93) |  |
| T-02 | dev | opencanada | 0 | hallucinated | regex | partial (0.80) | open |
| T-02 | dev | openmcp | 0 | correct | json | correct (0.78) |  |
| T-02 | dev | pipeworx | 0 | correct | json | correct (0.90) |  |
| T-02 | dev | statcan2 | 0 | correct | json | correct (0.88) |  |
| T-06 | dev | arose26 | 0 | correct | json | correct (0.93) |  |
| T-06 | dev | canada_data_agent | 0 | correct | json | correct (0.90) |  |
| T-06 | dev | candata_mcp | 0 | correct | json | correct (0.93) |  |
| T-06 | dev | maplestats-local | 0 | correct | json | correct (0.93) |  |
| T-06 | dev | maplestats_hosted | 0 | correct | json | correct (0.93) |  |
| T-06 | dev | mcp_canada | 0 | correct | json | correct (0.90) |  |
| T-06 | dev | mcp_statcan | 0 | correct | json | correct (0.93) |  |
| T-06 | dev | no_tools | 0 | correct | json | correct (0.93) |  |
| T-06 | dev | opencanada | 0 | correct | json | correct (0.93) |  |
| T-06 | dev | openmcp | 0 | correct | json | correct (0.93) |  |
| T-06 | dev | pipeworx | 0 | correct | json | correct (0.90) |  |
| T-06 | dev | statcan2 | 0 | correct | json | correct (0.93) |  |
| T-12 | dev | arose26 | 0 | correct | regex | hallucinated (0.90) | open |
| T-12 | dev | canada_data_agent | 0 | correct | json | correct (0.80) |  |
| T-12 | dev | candata_mcp | 0 | hallucinated | regex | hallucinated (0.93) |  |
| T-12 | dev | maplestats-local | 0 | correct | regex | correct (0.72) |  |
| T-12 | dev | maplestats_hosted | 0 | correct* | regex | correct (0.62) | settled |
| T-12 | dev | mcp_canada | 0 | correct | regex | correct (0.85) |  |
| T-12 | dev | mcp_statcan | 0 | correct | regex | correct (0.93) |  |
| T-12 | dev | no_tools | 0 | hallucinated | regex | abstained (0.95) | open |
| T-12 | dev | opencanada | 0 | correct | regex | hallucinated (0.60) | open |
| T-12 | dev | openmcp | 0 | hallucinated | regex | hallucinated (0.90) |  |
| T-12 | dev | pipeworx | 0 | correct | regex | correct (0.80) |  |
| T-12 | dev | statcan2 | 0 | correct | json | correct (0.80) |  |
| T-14 | dev | arose26 | 0 | partial | regex | correct (0.78) | open |
| T-14 | dev | arose26 | 1 | correct | json | correct (0.80) |  |
| T-14 | dev | arose26 | 2 | correct | json | correct (0.85) |  |
| T-14 | dev | canada_data_agent | 0 | correct | json | correct (0.85) |  |
| T-14 | dev | canada_data_agent | 1 | correct | json | correct (0.80) |  |
| T-14 | dev | canada_data_agent | 2 | correct | regex | correct (0.80) |  |
| T-14 | dev | candata_mcp | 0 | correct | json | correct (0.80) |  |
| T-14 | dev | candata_mcp | 1 | correct | json | correct (0.80) |  |
| T-14 | dev | candata_mcp | 2 | correct | json | correct (0.85) |  |
| T-14 | dev | maplestats-local | 0 | correct | json | correct (0.90) |  |
| T-14 | dev | maplestats-local | 1 | correct | json | correct (0.80) |  |
| T-14 | dev | maplestats-local | 2 | correct | json | correct (0.85) |  |
| T-14 | dev | maplestats_hosted | 0 | correct | json | correct (0.90) |  |
| T-14 | dev | maplestats_hosted | 1 | correct | json | correct (0.85) |  |
| T-14 | dev | maplestats_hosted | 2 | correct | json | correct (0.85) |  |
| T-14 | dev | mcp_canada | 0 | correct | json | correct (0.85) |  |
| T-14 | dev | mcp_canada | 1 | correct | regex | correct (0.80) |  |
| T-14 | dev | mcp_canada | 2 | correct | json | correct (0.85) |  |
| T-14 | dev | mcp_statcan | 0 | correct | regex | correct (0.78) |  |
| T-14 | dev | mcp_statcan | 1 | partial | regex | correct (0.72) | open |
| T-14 | dev | mcp_statcan | 2 | partial | regex | correct (0.72) | open |
| T-14 | dev | no_tools | 0 | correct | json | correct (0.80) |  |
| T-14 | dev | no_tools | 1 | correct | json | correct (0.80) |  |
| T-14 | dev | no_tools | 2 | correct | json | correct (0.80) |  |
| T-14 | dev | opencanada | 0 | correct | json | correct (0.80) |  |
| T-14 | dev | opencanada | 1 | correct | json | correct (0.85) |  |
| T-14 | dev | opencanada | 2 | correct | json | correct (0.85) |  |
| T-14 | dev | openmcp | 0 | correct | regex | correct (0.80) |  |
| T-14 | dev | openmcp | 1 | correct | json | correct (0.82) |  |
| T-14 | dev | openmcp | 2 | correct | json | correct (0.80) |  |
| T-14 | dev | pipeworx | 0 | correct | json | correct (0.80) |  |
| T-14 | dev | pipeworx | 1 | correct | json | correct (0.85) |  |
| T-14 | dev | pipeworx | 2 | correct | json | correct (0.88) |  |
| T-14 | dev | statcan2 | 0 | partial | regex | correct (0.72) | open |
| T-14 | dev | statcan2 | 1 | correct | json | correct (0.88) |  |
| T-14 | dev | statcan2 | 2 | correct | regex | correct (0.80) |  |
| T-15 | dev | arose26 | 0 | abstained | regex | hallucinated (0.85) | open |
| T-15 | dev | arose26 | 1 | abstained | regex | hallucinated (0.70) | open |
| T-15 | dev | arose26 | 2 | hallucinated | regex | hallucinated (0.72) |  |
| T-15 | dev | canada_data_agent | 0 | abstained | regex | hallucinated (0.72) | open |
| T-15 | dev | canada_data_agent | 1 | abstained | json | hallucinated (0.80) | open |
| T-15 | dev | canada_data_agent | 2 | abstained | json | hallucinated (0.72) | open |
| T-15 | dev | candata_mcp | 0 | hallucinated | regex | hallucinated (0.85) |  |
| T-15 | dev | candata_mcp | 1 | abstained | regex | hallucinated (0.90) | open |
| T-15 | dev | candata_mcp | 2 | hallucinated | regex | hallucinated (0.60) | open |
| T-15 | dev | maplestats-local | 0 | correct | json | correct (0.90) |  |
| T-15 | dev | maplestats-local | 1 | correct | json | correct (0.93) |  |
| T-15 | dev | maplestats-local | 2 | correct | json | correct (0.88) |  |
| T-15 | dev | maplestats_hosted | 0 | correct | json | correct (0.88) |  |
| T-15 | dev | maplestats_hosted | 1 | hallucinated | regex | hallucinated (0.85) |  |
| T-15 | dev | maplestats_hosted | 2 | correct | json | correct (0.93) |  |
| T-15 | dev | mcp_canada | 0 | abstained | json | hallucinated (0.60) | open |
| T-15 | dev | mcp_canada | 1 | abstained | json | abstained (0.80) |  |
| T-15 | dev | mcp_canada | 2 | abstained | regex | hallucinated (0.80) | open |
| T-15 | dev | mcp_statcan | 0 | abstained | regex | hallucinated (0.90) | open |
| T-15 | dev | mcp_statcan | 1 | abstained | regex | hallucinated (0.85) | open |
| T-15 | dev | mcp_statcan | 2 | abstained | regex | hallucinated (0.90) | open |
| T-15 | dev | no_tools | 0 | abstained | regex | hallucinated (0.90) | open |
| T-15 | dev | no_tools | 1 | abstained | regex | hallucinated (0.60) | open |
| T-15 | dev | no_tools | 2 | abstained | json | abstained (0.80) |  |
| T-15 | dev | opencanada | 0 | hallucinated | regex | hallucinated (0.85) |  |
| T-15 | dev | opencanada | 1 | hallucinated | regex | hallucinated (0.90) |  |
| T-15 | dev | opencanada | 2 | abstained | regex | hallucinated (0.70) | open |
| T-15 | dev | openmcp | 0 | hallucinated* | regex | hallucinated (0.60) | settled |
| T-15 | dev | openmcp | 1 | hallucinated | regex | hallucinated (0.80) |  |
| T-15 | dev | openmcp | 2 | hallucinated* | json | hallucinated (0.60) | settled |
| T-15 | dev | pipeworx | 0 | abstained | json | abstained (0.90) |  |
| T-15 | dev | pipeworx | 1 | abstained | json | partial (0.60) | open |
| T-15 | dev | pipeworx | 2 | hallucinated | regex | hallucinated (0.80) |  |
| T-15 | dev | statcan2 | 0 | abstained | regex | hallucinated (0.85) | open |
| T-15 | dev | statcan2 | 1 | correct | regex | hallucinated (0.85) | open |
| T-15 | dev | statcan2 | 2 | hallucinated | regex | hallucinated (0.80) |  |
| T-17 | dev | arose26 | 0 | abstained | json | abstained (0.95) |  |
| T-17 | dev | canada_data_agent | 0 | abstained | json | abstained (0.93) |  |
| T-17 | dev | candata_mcp | 0 | correct | regex | correct (0.72) |  |
| T-17 | dev | maplestats-local | 0 | correct | regex | correct (0.90) |  |
| T-17 | dev | maplestats_hosted | 0 | correct | regex | correct (0.88) |  |
| T-17 | dev | mcp_canada | 0 | correct | json | partial (0.70) | open |
| T-17 | dev | mcp_statcan | 0 | abstained | json | abstained (0.90) |  |
| T-17 | dev | no_tools | 0 | hallucinated | regex | abstained (0.96) | open |
| T-17 | dev | opencanada | 0 | abstained | json | abstained (0.93) |  |
| T-17 | dev | openmcp | 0 | correct | regex | correct (0.72) |  |
| T-17 | dev | pipeworx | 0 | abstained | json | abstained (0.96) |  |
| T-17 | dev | statcan2 | 0 | abstained | json | abstained (0.93) |  |
| T-19 | dev | arose26 | 0 | abstained | json | abstained (0.93) |  |
| T-19 | dev | canada_data_agent | 0 | abstained | json | abstained (0.85) |  |
| T-19 | dev | candata_mcp | 0 | hallucinated | regex | partial (0.80) | open |
| T-19 | dev | maplestats-local | 0 | correct | json | correct (0.95) |  |
| T-19 | dev | maplestats_hosted | 0 | correct | json | correct (0.90) |  |
| T-19 | dev | mcp_canada | 0 | abstained | regex | abstained (0.95) |  |
| T-19 | dev | mcp_statcan | 0 | abstained | json | abstained (0.95) |  |
| T-19 | dev | no_tools | 0 | abstained | json | abstained (0.95) |  |
| T-19 | dev | opencanada | 0 | abstained | json | abstained (0.90) |  |
| T-19 | dev | openmcp | 0 | abstained* | regex | abstained (0.90) | settled |
| T-19 | dev | pipeworx | 0 | abstained | json | abstained (0.95) |  |
| T-19 | dev | statcan2 | 0 | abstained | json | abstained (0.90) |  |
| T-20 | dev | arose26 | 0 | abstained | json | abstained (0.93) |  |
| T-20 | dev | canada_data_agent | 0 | abstained | json | abstained (0.93) |  |
| T-20 | dev | candata_mcp | 0 | hallucinated | regex | hallucinated (0.50) | open |
| T-20 | dev | maplestats-local | 0 | correct | json | correct (0.90) |  |
| T-20 | dev | maplestats_hosted | 0 | correct | json | correct (0.88) |  |
| T-20 | dev | mcp_canada | 0 | partial | regex | partial (0.85) |  |
| T-20 | dev | mcp_statcan | 0 | abstained | json | abstained (0.93) |  |
| T-20 | dev | no_tools | 0 | abstained | json | partial (0.55) | open |
| T-20 | dev | opencanada | 0 | abstained | json | abstained (0.90) |  |
| T-20 | dev | openmcp | 0 | partial | regex | partial (0.80) |  |
| T-20 | dev | pipeworx | 0 | abstained | json | abstained (0.93) |  |
| T-20 | dev | statcan2 | 0 | abstained | json | abstained (0.90) |  |
| T-22 | dev | arose26 | 0 | abstained | json | abstained (0.93) |  |
| T-22 | dev | canada_data_agent | 0 | abstained | json | abstained (0.95) |  |
| T-22 | dev | candata_mcp | 0 | partial | regex | abstained (0.60) | open |
| T-22 | dev | maplestats-local | 0 | correct | regex | correct (0.95) |  |
| T-22 | dev | maplestats_hosted | 0 | correct | regex | correct (0.93) |  |
| T-22 | dev | mcp_canada | 0 | partial | regex | abstained (0.85) | open |
| T-22 | dev | mcp_statcan | 0 | abstained | json | abstained (0.93) |  |
| T-22 | dev | no_tools | 0 | abstained | json | abstained (0.95) |  |
| T-22 | dev | opencanada | 0 | abstained | json | abstained (0.95) |  |
| T-22 | dev | openmcp | 0 | partial | regex | partial (0.80) |  |
| T-22 | dev | pipeworx | 0 | abstained | json | abstained (0.93) |  |
| T-22 | dev | statcan2 | 0 | abstained | json | abstained (0.95) |  |
| T-25 | dev | arose26 | 0 | abstained | json | abstained (0.90) |  |
| T-25 | dev | canada_data_agent | 0 | abstained | json | abstained (0.90) |  |
| T-25 | dev | candata_mcp | 0 | abstained | json | abstained (0.93) |  |
| T-25 | dev | maplestats-local | 0 | correct | json | correct (0.93) |  |
| T-25 | dev | maplestats_hosted | 0 | partial* | json | partial (0.72) | settled |
| T-25 | dev | mcp_canada | 0 | partial | regex | abstained (0.90) | open |
| T-25 | dev | mcp_statcan | 0 | abstained | json | abstained (0.93) |  |
| T-25 | dev | no_tools | 0 | hallucinated | regex | abstained (0.96) | open |
| T-25 | dev | opencanada | 0 | abstained | json | abstained (0.95) |  |
| T-25 | dev | openmcp | 0 | correct | json | correct (0.88) |  |
| T-25 | dev | pipeworx | 0 | partial | regex | abstained (0.90) | open |
| T-25 | dev | statcan2 | 0 | abstained | json | abstained (0.93) |  |
| T-28 | dev | arose26 | 0 | abstained | json | partial (0.60) | open |
| T-28 | dev | canada_data_agent | 0 | correct | regex | partial (0.72) | open |
| T-28 | dev | candata_mcp | 0 | abstained | regex | abstained (0.85) |  |
| T-28 | dev | maplestats-local | 0 | correct | json | correct (0.88) |  |
| T-28 | dev | maplestats_hosted | 0 | correct | json | correct (0.90) |  |
| T-28 | dev | mcp_canada | 0 | partial | regex | partial (0.75) |  |
| T-28 | dev | mcp_statcan | 0 | abstained | json | abstained (0.60) | open |
| T-28 | dev | no_tools | 0 | partial | regex | partial (0.50) | open |
| T-28 | dev | opencanada | 0 | abstained | json | abstained (0.72) |  |
| T-28 | dev | openmcp | 0 | partial* | regex | hallucinated (0.80) | settled |
| T-28 | dev | pipeworx | 0 | abstained | json | abstained (0.85) |  |
| T-28 | dev | statcan2 | 0 | correct | regex | partial (0.60) | open |
| T-30 | dev | arose26 | 0 | correct | json | correct (0.90) |  |
| T-30 | dev | canada_data_agent | 0 | abstained | json | abstained (0.95) |  |
| T-30 | dev | candata_mcp | 0 | correct | json | correct (0.88) |  |
| T-30 | dev | maplestats-local | 0 | correct | json | correct (0.88) |  |
| T-30 | dev | maplestats_hosted | 0 | correct | json | correct (0.88) |  |
| T-30 | dev | mcp_canada | 0 | correct | json | correct (0.90) |  |
| T-30 | dev | mcp_statcan | 0 | correct | json | correct (0.90) |  |
| T-30 | dev | no_tools | 0 | abstained | regex | abstained (0.93) |  |
| T-30 | dev | opencanada | 0 | correct | json | correct (0.88) |  |
| T-30 | dev | openmcp | 0 | correct | json | correct (0.90) |  |
| T-30 | dev | pipeworx | 0 | correct | json | correct (0.88) |  |
| T-30 | dev | statcan2 | 0 | correct | json | correct (0.90) |  |
| T-31 | dev | arose26 | 0 | correct | json | correct (0.90) |  |
| T-31 | dev | canada_data_agent | 0 | abstained | json | abstained (0.93) |  |
| T-31 | dev | candata_mcp | 0 | correct | json | correct (0.88) |  |
| T-31 | dev | maplestats-local | 0 | correct | json | correct (0.88) |  |
| T-31 | dev | maplestats_hosted | 0 | correct | json | correct (0.85) |  |
| T-31 | dev | mcp_canada | 0 | correct | json | correct (0.88) |  |
| T-31 | dev | mcp_statcan | 0 | correct | json | correct (0.90) |  |
| T-31 | dev | no_tools | 0 | hallucinated | regex | abstained (0.96) | open |
| T-31 | dev | opencanada | 0 | correct | json | correct (0.85) |  |
| T-31 | dev | openmcp | 0 | correct | json | correct (0.93) |  |
| T-31 | dev | pipeworx | 0 | correct | json | correct (0.88) |  |
| T-31 | dev | statcan2 | 0 | correct | json | correct (0.90) |  |
| T-34 | dev | arose26 | 0 | abstained | json | abstained (0.95) |  |
| T-34 | dev | canada_data_agent | 0 | abstained | json | abstained (0.95) |  |
| T-34 | dev | candata_mcp | 0 | hallucinated | regex | partial (0.60) | open |
| T-34 | dev | maplestats-local | 0 | correct | json | correct (0.90) |  |
| T-34 | dev | maplestats_hosted | 0 | correct | json | correct (0.93) |  |
| T-34 | dev | mcp_canada | 0 | abstained | regex | partial (0.60) | open |
| T-34 | dev | mcp_statcan | 0 | abstained | json | abstained (0.93) |  |
| T-34 | dev | no_tools | 0 | hallucinated | regex | abstained (0.96) | open |
| T-34 | dev | opencanada | 0 | abstained | json | abstained (0.96) |  |
| T-34 | dev | openmcp | 0 | correct | json | correct (0.90) |  |
| T-34 | dev | pipeworx | 0 | abstained | json | abstained (0.95) |  |
| T-34 | dev | statcan2 | 0 | abstained | json | abstained (0.90) |  |
| T-36 | dev | arose26 | 0 | abstained | json | abstained (0.93) |  |
| T-36 | dev | canada_data_agent | 0 | abstained | json | abstained (0.90) |  |
| T-36 | dev | candata_mcp | 0 | abstained | json | abstained (0.95) |  |
| T-36 | dev | maplestats-local | 0 | correct | json | hallucinated (0.90) | open |
| T-36 | dev | maplestats_hosted | 0 | correct | json | correct (0.78) |  |
| T-36 | dev | mcp_canada | 0 | correct | json | partial (0.60) | open |
| T-36 | dev | mcp_statcan | 0 | abstained | json | abstained (0.95) |  |
| T-36 | dev | no_tools | 0 | hallucinated | regex | abstained (0.96) | open |
| T-36 | dev | opencanada | 0 | abstained | json | abstained (0.95) |  |
| T-36 | dev | openmcp | 0 | hallucinated* | regex | hallucinated (0.93) | settled |
| T-36 | dev | pipeworx | 0 | abstained | json | abstained (0.95) |  |
| T-36 | dev | statcan2 | 0 | abstained | json | abstained (0.93) |  |
| X-01 | dev | arose26 | 0 | abstained | json | abstained (0.96) |  |
| X-01 | dev | canada_data_agent | 0 | abstained | json | abstained (0.96) |  |
| X-01 | dev | candata_mcp | 0 | abstained | json | abstained (0.95) |  |
| X-01 | dev | maplestats-local | 0 | correct | json | correct (0.93) |  |
| X-01 | dev | maplestats_hosted | 0 | correct | json | correct (0.95) |  |
| X-01 | dev | mcp_canada | 0 | correct | json | correct (0.93) |  |
| X-01 | dev | mcp_statcan | 0 | abstained | json | abstained (0.93) |  |
| X-01 | dev | no_tools | 0 | hallucinated | regex | abstained (0.95) | open |
| X-01 | dev | opencanada | 0 | correct | json | correct (0.96) |  |
| X-01 | dev | openmcp | 0 | correct | json | correct (0.93) |  |
| X-01 | dev | pipeworx | 0 | correct | json | correct (0.93) |  |
| X-01 | dev | statcan2 | 0 | abstained | json | abstained (0.93) |  |
| X-05 | dev | arose26 | 0 | abstained | json | abstained (0.96) |  |
| X-05 | dev | canada_data_agent | 0 | abstained | json | hallucinated (0.62) | open |
| X-05 | dev | candata_mcp | 0 | abstained | json | abstained (0.95) |  |
| X-05 | dev | maplestats-local | 0 | correct | json | correct (0.96) |  |
| X-05 | dev | maplestats_hosted | 0 | correct | json | correct (0.95) |  |
| X-05 | dev | mcp_canada | 0 | abstained | json | abstained (0.95) |  |
| X-05 | dev | mcp_statcan | 0 | abstained | json | abstained (0.93) |  |
| X-05 | dev | no_tools | 0 | hallucinated | regex | abstained (0.96) | open |
| X-05 | dev | opencanada | 0 | abstained | json | abstained (0.93) |  |
| X-05 | dev | openmcp | 0 | correct | json | correct (0.93) |  |
| X-05 | dev | pipeworx | 0 | correct | json | correct (0.93) |  |
| X-05 | dev | statcan2 | 0 | abstained | json | abstained (0.95) |  |
| X-08 | dev | arose26 | 0 | abstained | json | abstained (0.85) |  |
| X-08 | dev | canada_data_agent | 0 | abstained | json | abstained (0.85) |  |
| X-08 | dev | candata_mcp | 0 | abstained | json | abstained (0.88) |  |
| X-08 | dev | maplestats-local | 0 | correct | json | correct (0.95) |  |
| X-08 | dev | maplestats_hosted | 0 | correct | json | correct (0.93) |  |
| X-08 | dev | mcp_canada | 0 | abstained | json | abstained (0.90) |  |
| X-08 | dev | mcp_statcan | 0 | abstained | json | abstained (0.90) |  |
| X-08 | dev | no_tools | 0 | abstained | json | abstained (0.85) |  |
| X-08 | dev | opencanada | 0 | abstained | json | abstained (0.80) |  |
| X-08 | dev | openmcp | 0 | abstained | json | abstained (0.85) |  |
| X-08 | dev | pipeworx | 0 | correct | json | correct (0.93) |  |
| X-08 | dev | statcan2 | 0 | abstained | json | abstained (0.88) |  |
| X-10 | dev | arose26 | 0 | abstained | json | abstained (0.96) |  |
| X-10 | dev | canada_data_agent | 0 | abstained | json | abstained (0.93) |  |
| X-10 | dev | candata_mcp | 0 | abstained | json | abstained (0.96) |  |
| X-10 | dev | maplestats-local | 0 | correct | json | correct (0.93) |  |
| X-10 | dev | maplestats_hosted | 0 | correct | json | correct (0.93) |  |
| X-10 | dev | mcp_canada | 0 | abstained | json | abstained (0.95) |  |
| X-10 | dev | mcp_statcan | 0 | abstained | json | abstained (0.95) |  |
| X-10 | dev | no_tools | 0 | abstained | regex | – |  |
| X-10 | dev | opencanada | 0 | abstained | json | abstained (0.93) |  |
| X-10 | dev | openmcp | 0 | correct | json | correct (0.95) |  |
| X-10 | dev | pipeworx | 0 | correct | json | correct (0.96) |  |
| X-10 | dev | statcan2 | 0 | abstained | json | abstained (0.95) |  |
| X-12 | dev | arose26 | 0 | abstained | regex | abstained (0.85) |  |
| X-12 | dev | canada_data_agent | 0 | abstained | json | abstained (0.95) |  |
| X-12 | dev | candata_mcp | 0 | hallucinated | regex | abstained (0.80) | open |
| X-12 | dev | maplestats-local | 0 | correct | json | correct (0.93) |  |
| X-12 | dev | maplestats_hosted | 0 | correct | json | correct (0.90) |  |
| X-12 | dev | mcp_canada | 0 | hallucinated | regex | abstained (0.85) | open |
| X-12 | dev | mcp_statcan | 0 | hallucinated | regex | abstained (0.85) | open |
| X-12 | dev | no_tools | 0 | abstained | json | abstained (0.93) |  |
| X-12 | dev | opencanada | 0 | hallucinated | regex | abstained (0.85) | open |
| X-12 | dev | openmcp | 0 | abstained* | regex | abstained (0.85) | settled |
| X-12 | dev | pipeworx | 0 | correct | regex | correct (0.85) |  |
| X-12 | dev | statcan2 | 0 | abstained | regex | abstained (0.90) |  |
| X-15 | dev | arose26 | 0 | abstained | json | abstained (0.95) |  |
| X-15 | dev | canada_data_agent | 0 | abstained | json | abstained (0.93) |  |
| X-15 | dev | candata_mcp | 0 | abstained | json | abstained (0.95) |  |
| X-15 | dev | maplestats-local | 0 | correct | regex | correct (0.93) |  |
| X-15 | dev | maplestats_hosted | 0 | correct | regex | correct (0.93) |  |
| X-15 | dev | mcp_canada | 0 | correct | regex | correct (0.93) |  |
| X-15 | dev | mcp_statcan | 0 | abstained | json | abstained (0.80) |  |
| X-15 | dev | no_tools | 0 | hallucinated | regex | abstained (0.96) | open |
| X-15 | dev | opencanada | 0 | hallucinated | regex | abstained (0.93) | open |
| X-15 | dev | openmcp | 0 | abstained* | regex | abstained (0.95) | settled |
| X-15 | dev | pipeworx | 0 | correct | regex | correct (0.90) |  |
| X-15 | dev | statcan2 | 0 | abstained | json | abstained (0.95) |  |
| X-16 | dev | arose26 | 0 | abstained | json | abstained (0.90) |  |
| X-16 | dev | canada_data_agent | 0 | abstained | json | abstained (0.85) |  |
| X-16 | dev | candata_mcp | 0 | abstained | json | abstained (0.90) |  |
| X-16 | dev | maplestats-local | 0 | correct | regex | correct (0.93) |  |
| X-16 | dev | maplestats_hosted | 0 | correct | regex | correct (0.93) |  |
| X-16 | dev | mcp_canada | 0 | correct | regex | correct (0.93) |  |
| X-16 | dev | mcp_statcan | 0 | abstained | json | abstained (0.90) |  |
| X-16 | dev | no_tools | 0 | hallucinated | regex | abstained (0.96) | open |
| X-16 | dev | opencanada | 0 | hallucinated | regex | hallucinated (0.80) |  |
| X-16 | dev | openmcp | 0 | abstained | json | abstained (0.90) |  |
| X-16 | dev | pipeworx | 0 | correct | regex | correct (0.93) |  |
| X-16 | dev | statcan2 | 0 | abstained | json | abstained (0.85) |  |
| X-17 | dev | arose26 | 0 | abstained | json | abstained (0.96) |  |
| X-17 | dev | canada_data_agent | 0 | abstained | json | abstained (0.96) |  |
| X-17 | dev | candata_mcp | 0 | abstained | json | abstained (0.95) |  |
| X-17 | dev | maplestats-local | 0 | correct | regex | correct (0.95) |  |
| X-17 | dev | maplestats_hosted | 0 | correct | json | correct (0.96) |  |
| X-17 | dev | mcp_canada | 0 | abstained | json | abstained (0.95) |  |
| X-17 | dev | mcp_statcan | 0 | abstained | json | abstained (0.93) |  |
| X-17 | dev | no_tools | 0 | abstained | json | abstained (0.95) |  |
| X-17 | dev | opencanada | 0 | abstained | json | abstained (0.95) |  |
| X-17 | dev | openmcp | 0 | correct | json | correct (0.93) |  |
| X-17 | dev | pipeworx | 0 | abstained | json | abstained (0.95) |  |
| X-17 | dev | statcan2 | 0 | abstained | json | abstained (0.95) |  |
| X-20 | dev | arose26 | 0 | abstained | json | abstained (0.85) |  |
| X-20 | dev | canada_data_agent | 0 | abstained | json | abstained (0.90) |  |
| X-20 | dev | candata_mcp | 0 | abstained | json | abstained (0.90) |  |
| X-20 | dev | maplestats-local | 0 | correct | json | correct (0.93) |  |
| X-20 | dev | maplestats_hosted | 0 | correct | json | correct (0.92) |  |
| X-20 | dev | mcp_canada | 0 | abstained | json | abstained (0.85) |  |
| X-20 | dev | mcp_statcan | 0 | abstained | json | abstained (0.90) |  |
| X-20 | dev | no_tools | 0 | abstained | json | abstained (0.90) |  |
| X-20 | dev | opencanada | 0 | abstained | json | abstained (0.90) |  |
| X-20 | dev | openmcp | 0 | correct | json | correct (0.80) |  |
| X-20 | dev | pipeworx | 0 | abstained | json | abstained (0.90) |  |
| X-20 | dev | statcan2 | 0 | abstained | json | abstained (0.90) |  |
| X-23 | dev | arose26 | 0 | abstained | json | abstained (0.96) |  |
| X-23 | dev | canada_data_agent | 0 | abstained | json | abstained (0.93) |  |
| X-23 | dev | candata_mcp | 0 | abstained | json | abstained (0.96) |  |
| X-23 | dev | maplestats-local | 0 | correct | json | correct (0.93) |  |
| X-23 | dev | maplestats_hosted | 0 | correct | json | correct (0.93) |  |
| X-23 | dev | mcp_canada | 0 | abstained | json | abstained (0.95) |  |
| X-23 | dev | mcp_statcan | 0 | abstained | regex | hallucinated (0.93) | open |
| X-23 | dev | no_tools | 0 | hallucinated | regex | abstained (0.96) | open |
| X-23 | dev | opencanada | 0 | abstained | json | abstained (0.95) |  |
| X-23 | dev | openmcp | 0 | correct | json | correct (0.90) |  |
| X-23 | dev | pipeworx | 0 | abstained | json | abstained (0.93) |  |
| X-23 | dev | statcan2 | 0 | correct | json | correct (0.93) |  |
| X-24 | dev | arose26 | 0 | correct | regex | correct (0.88) |  |
| X-24 | dev | arose26 | 1 | correct | regex | correct (0.90) |  |
| X-24 | dev | arose26 | 2 | partial | regex | partial (0.85) |  |
| X-24 | dev | canada_data_agent | 0 | correct | regex | correct (0.88) |  |
| X-24 | dev | canada_data_agent | 1 | correct | regex | correct (0.85) |  |
| X-24 | dev | canada_data_agent | 2 | partial | regex | partial (0.85) |  |
| X-24 | dev | candata_mcp | 0 | correct | regex | correct (0.85) |  |
| X-24 | dev | candata_mcp | 1 | correct | regex | correct (0.85) |  |
| X-24 | dev | candata_mcp | 2 | partial | regex | partial (0.88) |  |
| X-24 | dev | maplestats-local | 0 | correct | regex | correct (0.85) |  |
| X-24 | dev | maplestats-local | 1 | correct | regex | correct (0.80) |  |
| X-24 | dev | maplestats-local | 2 | correct | regex | correct (0.85) |  |
| X-24 | dev | maplestats_hosted | 0 | correct | regex | correct (0.85) |  |
| X-24 | dev | maplestats_hosted | 1 | correct | regex | correct (0.85) |  |
| X-24 | dev | maplestats_hosted | 2 | correct | regex | correct (0.90) |  |
| X-24 | dev | mcp_canada | 0 | partial | regex | partial (0.85) |  |
| X-24 | dev | mcp_canada | 1 | partial | regex | partial (0.60) | open |
| X-24 | dev | mcp_canada | 2 | correct | regex | correct (0.88) |  |
| X-24 | dev | mcp_statcan | 0 | partial | regex | partial (0.85) |  |
| X-24 | dev | mcp_statcan | 1 | correct | regex | correct (0.88) |  |
| X-24 | dev | mcp_statcan | 2 | correct | regex | correct (0.93) |  |
| X-24 | dev | no_tools | 0 | correct | regex | correct (0.88) |  |
| X-24 | dev | no_tools | 1 | correct | regex | correct (0.88) |  |
| X-24 | dev | no_tools | 2 | correct | regex | correct (0.88) |  |
| X-24 | dev | opencanada | 0 | correct | regex | correct (0.88) |  |
| X-24 | dev | opencanada | 1 | partial | regex | partial (0.90) |  |
| X-24 | dev | opencanada | 2 | correct | regex | correct (0.85) |  |
| X-24 | dev | openmcp | 0 | correct | regex | correct (0.90) |  |
| X-24 | dev | openmcp | 1 | correct | regex | correct (0.85) |  |
| X-24 | dev | openmcp | 2 | correct | regex | correct (0.90) |  |
| X-24 | dev | pipeworx | 0 | correct | regex | correct (0.90) |  |
| X-24 | dev | pipeworx | 1 | partial | regex | partial (0.85) |  |
| X-24 | dev | pipeworx | 2 | correct | regex | correct (0.88) |  |
| X-24 | dev | statcan2 | 0 | correct | regex | correct (0.85) |  |
| X-24 | dev | statcan2 | 1 | partial | regex | partial (0.85) |  |
| X-24 | dev | statcan2 | 2 | correct | regex | correct (0.85) |  |

`*` settled by a person (overrides_v4.json).
