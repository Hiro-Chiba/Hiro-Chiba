# Hiro Chiba

This profile auto-generates language usage stats across all my GitHub repositories, including private repositories.

<p align="center">
  <img src="./output/full_languages.svg" alt="GitHub language stats across all repositories" />
</p>

## Features

- Aggregates all repositories with the GitHub API
- Includes private repositories by using a personal access token in GitHub Actions
- Updates automatically every week

## Update Schedule

- Weekly: Monday 00:00 UTC (Monday 09:00 JST)
- Manual: Actions -> Update Language Stats -> Run workflow

## Optional: Exclude Languages

Set `EXCLUDED_LANGUAGES` in repository secrets with a comma-separated list.

Example:

```text
Jupyter Notebook, HTML, CSS
```
