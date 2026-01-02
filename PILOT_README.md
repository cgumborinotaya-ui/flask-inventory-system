# Pilot Test Guide

## Quick Options
- Local network: Share `http://YOUR_IP:5000/login`
- Public temporary link: Use a tunneling service (e.g., ngrok, Cloudflare Tunnel)
- Temporary cloud: Use a free sandbox (PythonAnywhere, Render, Railway)

## Local Network Pilot
Use the start script:
```
.\start_pilot.ps1
```
- It auto-detects your IPv4 and prints a LAN URL like `http://192.168.1.25:5000/login`
- It also opens localhost in your browser
- Windows Firewall: allow inbound connections on port 5000 for Python if needed

## Public Temporary Link (Tunnel)
1. Install ngrok and run `ngrok http 5000` then share the URL shown.
   - Add your auth token for more stability.
2. Or use Cloudflare Tunnel (cloudflared) for a free, stable link.
3. Or run:
```
.\start_pilot.ps1 -Tunnel
```
   - The script starts the server and attempts a tunnel if ngrok or cloudflared is installed

## Production-Like Local Run
Use Waitress (a production WSGI server for Windows):
1. Install deps: `pip install -r requirements.txt`
2. Run: `python run_waitress.py`
3. Share the same IP/port link.

## Accounts and Access
- IT role can manage users and audit; others have restricted access.
- Create test users in Users page.
- Inactive users cannot log in.

## Data Handling
- DB file: `instance/inventory.db`
- Backup before pilot: copy the file
- Reset (fresh start): delete the DB file; app recreates schema

## Security and Stability
- Avoid debug traces to testers: prefer `python run_waitress.py` over `python app.py`
- Keep SECRET_KEY non-default for public tests
- SMTP is optional; reset links will show in UI if email isn’t configured

## Feedback
- Ask testers to share:
  - Usability of login, dashboard, asset add/edit
  - Role-based access correctness
  - Mobile experience
  - Any errors seen
