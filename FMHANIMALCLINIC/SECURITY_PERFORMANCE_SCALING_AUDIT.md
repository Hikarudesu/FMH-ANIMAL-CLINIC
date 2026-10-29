# Security and Scaling Report

**Updated:** 2026-10-20

## Short Version

I made the parts that can be changed safely in the code. The app has stronger AI and account protections now, but it is **not yet configured or tested for high traffic**. Railway, Cloudflare, Redis, and the live database need settings that I cannot change from this workspace.

## What I Changed

- **AI requests:** Staff need AI Diagnostics permission. Each user can make 20 AI requests per hour. Oversized symptom text is rejected, medical history sent to Groq is capped, and provider calls have a timeout.
- **Account and OTP limits:** Shared database limits apply across app copies: 10 login tries per account in 15 minutes; 3 reset-code emails per hour; 5 code guesses per 10 minutes; and similar limits for profile codes and verification emails.
- **OTP safety:** Codes use secure random generation, are stored as hashes, expire, and can only be used once. Password-reset permission expires after five minutes. Existing codes are converted by a migration.
- **Patient privacy:** AI diagnosis pages and actions now restrict branch staff to pets and diagnoses they are allowed to access.
- **Direct URL access:** Dashboards check role/permission server-side. Wrong-role requests redirect to the correct dashboard; staff without a dashboard grant go to their profile instead of the pet-owner dashboard. The clinic service-management page now requires its VIEW permission.
- **Reservation actions:** Confirmation/cancellation require POST and branch-scoped reservation lookup, so changing the reservation ID cannot target another branch.
- **Production defaults:** Railway no longer reads the local `.env` file. Production defaults to `DEBUG=false` and requires HTTPS-related settings.
- **AI request safety:** Symptom and history sizes are limited; Groq calls have a timeout; clinical text is no longer written into provider-error logs.

The Groq API key was not shown or changed.

## What Still Needs Your Cloud Accounts

These items cannot be completed or verified from the local project alone:

- **Database RLS:** PostgreSQL does not yet enforce branch isolation itself. The app filters AI data, but RLS needs a reviewed table-by-table design, production database roles, and staging tests. Applying generic rules now could block normal clinic workflows or expose data if the branch model is misread.
- **Bot IP limits:** The app limits attempts by account, but Railway/Cloudflare must limit traffic by the real client IP. I cannot safely trust forwarded IP headers without knowing your proxy setup.
- **Cache and CDN:** No shared Redis cache or CDN is active. Add Redis in Railway and use Cloudflare or another CDN for static files only. Never publicly cache patient records or medical files.
- **Scaling:** Railway replicas, health checks, database pooling, persistent media storage, backups, and autoscaling need to be configured in your Railway account.
- **Load/security testing:** No live production scan or realistic concurrent-load test was run.

## Before You Deploy

1. Back up the Railway PostgreSQL database.
2. The OTP migration changes stored codes to hashes and cannot be reversed. Stop old app instances, run `python manage.py migrate`, then start the new version as one coordinated release. Old code cannot verify newly hashed codes.
3. In Railway Variables, set `DEBUG=false`, the secret key, allowed hosts, trusted HTTPS origins, database settings, and email settings. Keep your existing Groq key in Railway; do not put it in source control.
4. Attach persistent storage for uploaded files. Add Redis/CDN and configure IP-based bot limits before increasing replicas.
5. Test login, reset codes, AI diagnostics, branch access, and backups in staging. Load-test before relying on autoscaling.

## Checks Run

- Django system check: passed.
- Migration consistency check: passed.
- Combined AI and account-security tests: **10 passed**.
- Direct URL dashboard, billing, and reservation authorization tests: **9 passed**. The inventory regression suite's 28 existing tests passed, and the two new reservation-security tests passed separately.
- Cross-session login limit test: passed.
- No live Railway changes or production load test were performed.