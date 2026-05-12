# Security Notes

Timeforge is designed as a local-first app. Treat calendar data, generated review data, OAuth credentials, and SQLite files as private.

Never commit or deploy:

- `.env`
- `Data/time_tracking.sqlite`
- `Data/google_credentials.json`
- `Data/google_token.json`
- `Data/normalization_overrides.json`
- `Dashboard/data/app-data.json`
- generated review notes
- runtime logs

The default server binds to `127.0.0.1`. Do not expose it to a public network without adding authentication, HTTPS, and a deliberate data-hosting plan.

By default, the local server refuses to serve generated static exports such as `Dashboard/data/app-data.json`. Set `TIME_OUTPUT_SERVE_STATIC_EXPORT=1` only if you intentionally want the static export endpoint available.

Before publishing, run:

```powershell
git status --short --ignored
git add -n .
rg -n "google_token|google_credentials|client_secret|refresh_token|private_key|BEGIN PRIVATE|sqlite|app-data.json" .
```
