# Swiss Career Intelligence OS — Workflow Redesign

## 1. Current information-architecture audit

The previous interface exposed the correct core data but fragmented the hiring workflow across repeated role cards and separate screens. Today duplicated the same action in multiple panels; Roles, Applications and Preparation each repeated overlapping role information; operational status competed with hiring work; and the card-heavy layout used substantial space without showing stage age, inactivity, deadlines, contacts or a chronological history.

The redesign preserves the existing backend, authentication, PostgreSQL state, source discovery, ranking, application-package logic and safety boundaries. It replaces the frontend information architecture and adds workflow metadata around the canonical Application record.

## 2. Revised sitemap

### Primary navigation

1. **Today** — daily priority, bounded action queue, upcoming events, blockers, funnel movement.
2. **Opportunities** — ranked comparison table, filters, source confidence and unified role workspace.
3. **Applications** — list and kanban views over the same records, follow-ups, deadlines and stage age.
4. **Interviews** — scheduled interviews or deliberate pre-interview mode, role-specific modules and sessions.
5. **Network** — verified contacts, access gaps and follow-up commitments.
6. **Assets** — role-specific packages and the evidence ledger.

### Secondary navigation

- **Profile** — candidate evidence, material facts and compact system status.
- Technical automation and continuity controls remain secondary and are not part of the ordinary hiring flow.

## 3. Screen specification

### Today

- One dominant priority with associated role, duration, deadline, rationale and one primary continuation action.
- Remaining actions appear as compact rows rather than repeated large cards.
- Upcoming interview, follow-up, deadline and preparation events share one chronological list.
- Blockers appear only when overdue, inactive or evidence-critical.
- Funnel metrics answer what requires attention: ready to submit, follow-ups due, advancing and interviews scheduled.

### Opportunities

- Desktop comparison table; structured mobile rows below 820 px.
- Persistent search, recommendation filter and sorting by fit, urgency, compensation or location.
- Multi-role comparison without leaving the list.
- One canonical detail drawer exposes Overview, Application, Preparation, Contacts, Documents, Evidence and Activity.

### Applications

- Compact list plus functional kanban over the same application records.
- Inline stage update; Applied requires explicit confirmation that submission occurred externally.
- Stage age, last activity, inactivity warning, next action, deadline, contact and blocker remain visible.
- Drag-and-drop stage changes are available on desktop; mobile uses the stage control.

### Interviews

- Scheduled interview mode shows date, time, format, interviewers, countdown and readiness.
- When no interview is scheduled, the strongest active application enters pre-interview mode rather than an empty dashboard.
- Sessions are grouped into role understanding, technical, behavioural, stakeholder, questions, logistics and mock-practice modules.

### Network

- Stores only user-confirmed contacts and sources.
- Active roles without a contact appear as access gaps, not invented referral suggestions.
- Follow-up commitments are visible when due.

### Assets

- Shows only existing role-specific packages and verified candidate evidence.
- Copy actions operate on generated package text; no unsupported document is invented.

## 4. Design system

### Core tokens

| Token | Value | Use |
|---|---|---|
| `--bg` | `#07111f` | Application background |
| `--sidebar` | `#091827` | Navigation surface |
| `--surface` | `#0d1d30` | Primary work surface |
| `--surface-2` | `#11243a` | Interactive secondary surface |
| `--text` | `#f6f8fc` | Primary text |
| `--muted` | `#9aa9bd` | Secondary text, never below readable contrast |
| `--line` | `#213650` | Structural borders |
| `--accent` | `#4f8cff` | One primary action colour |
| `--positive` | `#31c48d` | Completed or advancing |
| `--warning` | `#f2b94b` | Attention required |
| `--negative` | `#ff6b6b` | Blocked, overdue or destructive |

Typography uses 28–36 px page titles, 18–22 px section titles, 14–15 px primary body text and 11–13 px metadata. Uppercase is limited to short panel labels.

## 5. Reusable components

- `pageHeader`
- `button`
- `badge`
- `progress`
- `systemStatus`
- `priorityCard`
- `actionQueue`
- `dataTable` / responsive structured row
- `kanbanColumn` / `kanbanCard`
- `emptyState`
- `errorState`
- unified role/application detail drawer
- evidence row
- activity timeline
- interview module and session row
- verified contact row

Frontend primitives live in `static/ui.js`; canonical role/application detail behaviour lives in `static/workspace-detail.js`; route composition remains in `static/live.js`.

## 6. Desktop and mobile behaviour

- Desktop uses a fixed 246 px navigation surface, dense work tables, a right-side operational rail and a canonical detail drawer.
- Tablet collapses the sidebar and converts wide tables into structured rows.
- Mobile preserves the primary action, uses a five-item bottom navigation, places Network, Assets and Profile inside More, and converts secondary detail into the full-width drawer.
- All tested layouts avoid horizontal overflow; focus states and semantic labels are visible.

## 7. Removed, consolidated and renamed sections

| Previous concept | Result |
|---|---|
| Action | Consolidated into Today |
| Roles | Renamed Opportunities |
| Pipeline + Tracking | Consolidated into Applications list and pipeline views |
| Preparation | Renamed Interviews and tied to a role/application |
| Connections | Renamed Network |
| Documents + Evidence | Consolidated into Assets and the canonical role workspace |
| Settings | Moved into secondary Profile |
| Automation + Audit & Operations | Removed from primary navigation; compact status only |

## 8. Workflow acceptance

The primary verified path is:

```text
Today priority
→ Opportunities comparison
→ role workspace
→ Pursue
→ evidence-linked package
→ Applications stage update
→ role-specific Interviews plan
→ Network / Assets continuity
→ Today reprioritization
```

External applications, messages, referrals, meetings, negotiation and offer actions remain manual and require explicit user confirmation.
