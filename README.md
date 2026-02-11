# Hiro Chiba

このプロフィールでは、GitHub の全リポジトリ（public / private）の言語使用量を自動集計しています。  
This profile auto-generates language usage stats across all my GitHub repositories, including private repositories.

<p align="center">
  <img src="./output/full_languages.svg" alt="GitHub language stats across all repositories" />
</p>

## 機能 / Features

- GitHub API を使って全リポジトリを集計 / Aggregates all repositories with the GitHub API
- GitHub Actions の personal access token を使って private リポジトリも集計 / Includes private repositories by using a personal access token in GitHub Actions
- 毎週自動更新 / Updates automatically every week

## 更新スケジュール / Update Schedule

- 毎週: 月曜日 00:00 UTC（日本時間 月曜日 09:00） / Weekly: Monday 00:00 UTC (Monday 09:00 JST)
- 手動実行: Actions -> Update Language Stats -> Run workflow / Manual: Actions -> Update Language Stats -> Run workflow
