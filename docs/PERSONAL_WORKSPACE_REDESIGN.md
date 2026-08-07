# Personal workspace redesign

## Product principle

Every page answers one question: what must Navish understand or do here to increase the probability of reaching the next hiring stage?

## Spatial model

```text
Today
  → Role
      → Application
          → Interview preparation
```

Role, application, preparation, evidence, and activity are embedded pages in the main product. Important content never appears in a visible right-side drawer. Every object page has a visible Back action and browser-history support.

## Primary navigation

- Today
- Opportunities
- Applications
- Prepare
- Profile

Network, assets, system operations, source health, and backup controls are not primary destinations. Their underlying data remains available through the relevant role or profile context.

## Visual system

- White canvas and dark, high-contrast typography
- Subtle dividers instead of card grids
- No decorative shadows
- Minimal semantic colour
- Reading-width object pages
- Progressive disclosure for evidence
- One focal action at a time

## Continuity

Opening an object stores the origin route and scroll position. Back returns to the originating list and restores its position. Application and preparation pages remain attached to the same role identifier and evidence state.
