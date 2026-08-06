# ChatGPT-native reasoning with zero API cost

Swiss Career Intelligence OS separates deterministic automation from consequential reasoning.

## What runs automatically

The hosted application polls official ATS feeds, normalizes and deduplicates roles, verifies Swiss scope and listing status, classifies compensation evidence, applies mandatory evidence and seniority gates, creates Suggested applications, generates bounded application packages and interview preparation, and keeps Today to three actions.

This layer uses no OpenAI API and cannot submit an application or send a message.

## How Pro reasoning works

1. Open a role in the private dashboard.
2. Select **Analyze in ChatGPT Pro**.
3. The application assembles and copies one source-linked role packet.
4. ChatGPT opens. Select the highest-capability Pro model available in the conversation, paste once, and send.
5. Copy the returned JSON object.
6. Return to the dashboard and select **Import copied result**.

The server validates the schema, role ID and candidate evidence citations before storing the result. Imported analysis cannot change an external employer system.

The application deliberately does not claim that it can select, identify or invoke a specific Pro model from the server. Model selection occurs inside the user's ChatGPT conversation.

## Read-only ChatGPT app

The private dashboard exposes an authenticated read-only MCP endpoint with these tools:

- `get_today_actions`
- `search_opportunities`
- `get_opportunity`
- `get_application_package`
- `get_pipeline`
- `get_interview_plan`
- `get_candidate_evidence`
- `get_scheduler_status`
- `get_weekly_review`
- standard `search`
- standard `fetch`

No tool can submit an application, send email, contact a recruiter, request a referral, schedule a meeting, negotiate, withdraw or accept an offer.

The dashboard's **ChatGPT Pro** control copies the private connection URL. State-changing actions remain in the authenticated PWA.

## Free scheduling

The web process retains the Europe/Zurich scheduler. A GitHub Actions workflow wakes the free Render web service around the configured local-time windows. The server decides which schedules are actually due, so duplicate CET/CEST wake windows are idempotent.

Configured schedules:

- weekdays 06:30 — source scan
- weekdays 16:30 — source scan
- daily 07:00 — prioritization
- Sunday 18:00 — strategy review

## Cost and continuity boundary

- OpenAI API: disabled
- OpenAI API requests: zero
- API cost: CHF 0
- external hiring actions: prohibited
- hosting: free-tier service
- database: temporary free PostgreSQL, with private browser backup and ephemeral SQLite continuity fallback
- paid upgrades: never automatic

Free infrastructure has availability and durability limits. The application surfaces those limits instead of silently upgrading or creating charges.
