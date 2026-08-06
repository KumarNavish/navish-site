# Swiss Career Intelligence OS

A private, mobile-first Swiss hiring execution system for Navish Kumar.

## Live application

Production URL: `https://swiss-career-intelligence-os.onrender.com`

The application requires the private one-click access link configured on Render. It does not expose candidate records publicly.

## Operating model

The system separates deterministic automation from consequential reasoning:

1. Official ATS feeds are polled and normalized.
2. Swiss scope, listing freshness, compensation evidence, seniority, mandatory requirements and candidate evidence are checked deterministically.
3. Serious opportunities receive a Suggested application, an evidence-grounded package, interview preparation and a bounded Today action.
4. For deeper reasoning, **Analyze in ChatGPT Pro** creates one evidence-bounded packet, copies it and opens ChatGPT. The user selects the strongest Pro model available in that conversation.
5. ChatGPT returns strict JSON. The server validates the role ID, schema and evidence citations before importing it.

The hosted server never invokes the OpenAI API. The OpenAI API key is blank, API requests are capped at zero and estimated API cost is CHF 0.

## Automatic schedules

All application schedules use `Europe/Zurich`:

- weekdays 06:30 — official-source scan
- weekdays 16:30 — official-source scan
- daily 07:00 — prioritization
- Sunday 18:00 — strategy review

The free web process runs due schedules while awake. `.github/workflows/free-scheduler-wake.yml` provides free external wake-ups around the configured local-time windows; the server remains the authority on whether a schedule is due.

## ChatGPT app boundary

The private read-only MCP endpoint provides opportunity, evidence, package, pipeline, preparation, scheduler and Today retrieval tools. It contains no application-submission, email, message, referral, meeting, negotiation, withdrawal or offer-acceptance tool.

All consequential writes remain one-tap actions inside the authenticated PWA.

## Cost boundary

- OpenAI API: disabled
- OpenAI API requests: 0
- API cost: CHF 0
- paid services allowed: false
- Render web service: free tier
- Render PostgreSQL: free temporary database
- paid upgrades: never automatic

The free PostgreSQL instance expires on 5 September 2026. Before expiry, the app provides a private browser backup. After expiry, a configured ephemeral SQLite fallback keeps the application usable without creating a charge; durable state must then be restored from the private browser backup or moved to another genuinely free store.

## Validation

Hosted release validation on Python 3.12.8 passed:

- Python compilation
- all 9 static JavaScript modules
- 31/31 tests
- zero OpenAI API requests
- CHF 0 API cost
- no external hiring action

See `docs/zero-api-release-validation.json` and `docs/CHATGPT_NATIVE_ZERO_API.md`.

## Safety invariant

The system may discover, rank, explain, draft, prepare and schedule. It cannot submit an application or contact another person without a separate explicit user-controlled action, and no such external-action integration is present in this release.
