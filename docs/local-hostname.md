# Local Hostname Setup

The app can run at `http://localhost:8787/` with no extra setup. A cleaner local URL without a port needs something listening on port 80 and forwarding to the Python server on port 8787.

## Recommended Pattern

Use a `.localhost` name instead of `.local`.

- `.localhost` is reserved for loopback and is less likely to conflict with mDNS.
- `.local` can work, but Windows, Apple Bonjour, routers, and VPN tools may treat it as multicast DNS.

Example Caddy config:

```caddyfile
timeforge.localhost {
  reverse_proxy 127.0.0.1:8787
}
```

Then run the Python app:

```powershell
python App/server.py --host 127.0.0.1 --port 8787
```

Open:

```text
http://timeforge.localhost/
```

## Current Timeforge Setup

This repo also includes a direct no-proxy launcher:

```powershell
powershell -ExecutionPolicy Bypass -File App/install_timeforge_hostname.ps1
powershell -ExecutionPolicy Bypass -File App/start_timeforge.ps1
```

That adds the Windows hosts entry and runs the app on port 80 so the URL is:

```text
http://timeforge.localhost/
```

To start the app automatically when you log into Windows, install a Startup-folder shortcut:

```powershell
powershell -ExecutionPolicy Bypass -File App/install_timeforge_startup_shortcut.ps1
```

The app can stay up for days or weeks while the computer is awake. If Windows restarts, the Startup shortcut brings it back after login.

## Hosts File Alternative

If you choose a `.test` name, add a Windows hosts entry:

```text
127.0.0.1 timeforge.test
```

Then point a reverse proxy at the app:

```caddyfile
timeforge.test {
  reverse_proxy 127.0.0.1:8787
}
```

Do not use this setup for public hosting without adding real authentication and HTTPS.
