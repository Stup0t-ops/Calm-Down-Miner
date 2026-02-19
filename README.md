# Calm Down Miner

Desktop mining tracker for EVE Online logs.

## What it does

- Parses your EVE game logs and tracks mined resources.
- Shows session totals and aggregate totals across panels.
- Stores local settings and price data in JSON files in this folder.

## Requirements

- Windows (recommended)
- Python 3.10+
- Tkinter (included with standard Python on Windows installs)

## Run

1. Open PowerShell in this folder.
2. Start the app:

```powershell
python calm_down_miner.py
```

## Notes

- Default log folder is:
  `C:\Users\<you>\Documents\EVE\logs\Gamelogs`
- You can change folders and preferences inside the app.

## Files in this repo

- `calm_down_miner.py` - main app
- `prices.json` - local price cache
- `settings.json` - app settings
- `profile_index_cache.json` - profile cache

## Releases

Use GitHub Releases to publish downloadable versions.

1. Open your repo on GitHub.
2. Go to **Releases** -> **Draft a new release**.
3. Create a tag (example: `v1.0.0`).
4. Add a title and notes for what changed.
5. Publish release.

GitHub will automatically attach source `.zip` and `.tar.gz` downloads.

