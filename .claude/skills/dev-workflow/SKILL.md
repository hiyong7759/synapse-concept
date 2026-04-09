---
name: dev-workflow
description: "Development workflow orchestrator — enforces wireframe-first review, frontend skill delegation, post-implementation verification, E2E testing for UI changes, and security review for auth/permission features. Use this skill whenever the user asks to implement, build, develop, or add a new feature, page, component, or screen. Also triggers on requests like 'make this page', 'add this feature', 'build the settings screen', or any implementation task that involves UI or security-sensitive code."
---

# Dev Workflow

Orchestrates the full development cycle with thorough verification at every stage. This skill exists so the user never has to repeat the same process instructions. Every output must be polished enough to present to real developers with confidence.

This skill is **project-agnostic** — it adapts to whatever tech stack, folder structure, and tooling the current project uses.

## When This Skill Applies

Any implementation request that involves:
- New pages, screens, or components (UI work)
- Modifications to existing UI
- Security-related features (auth, permissions, tokens, personal data)
- Multi-step features that touch both UI and logic

## Project Detection

At the start of every workflow, detect the project context by reading available config files:

1. **CLAUDE.md** in the project root — tech stack, conventions, design doc paths
2. **package.json** — scripts (dev, build, test, lint, typecheck), dependencies (UI library, test framework)
3. **Folder structure** — `src/components/`, `e2e/`, `tests/`, `docs/` locations

Build a mental model of:

| What | How to detect | Fallback |
|------|--------------|----------|
| UI library | package.json deps (shadcn, MUI, Ant, Chakra, etc.) | Plain HTML/CSS |
| CSS approach | tailwind.config, .scss files, styled-components | Check imports |
| Test framework | vitest/jest/mocha in devDeps + test script | `npm test` |
| E2E framework | playwright/cypress in devDeps | playwright |
| Type checker | typescript in devDeps | Skip if not TS |
| Linter | eslint/biome in devDeps + lint script | `npm run lint` |
| Design docs | CLAUDE.md references, `docs/` folder | None |
| Component dir | `src/components/`, `components/`, `app/components/` | Search for it |

Use detected values throughout the workflow instead of hardcoded paths or commands.

## Workflow Overview

```
Request → Classify (+ Size) → Design Doc Check → Wireframe → User Approval
  → Plan → Implement (delegate to skill) → Verification (by size)
  → E2E Tests → Security Review → Quality Gates → Close Report
```

---

## Phase 1: Classify & Prepare

### Step 1.1: Classify the Request

Before doing anything, classify what the request involves:

| Aspect | Check | Consequence |
|--------|-------|-------------|
| Has UI? | New/modified page, component, or screen | → Wireframe required |
| Security-sensitive? | Auth, permissions, tokens, personal data, encryption | → Security review required |
| Has connected flows? | Multi-page interaction, form → submit → result | → E2E test required |
| Has design doc? | Check project's design doc location | → Must follow spec |

### Step 1.2: Determine Change Size

Size determines verification depth — this keeps simple changes fast while complex changes get full scrutiny.

| Size | Criteria | Verification Level |
|------|----------|-------------------|
| **Small** | Text/style change, 1-2 files, no new components | Lite: wireframe + quality gates only |
| **Medium** | New tab/section, 3-5 files, reuses existing components | Standard: wireframe + verification battery + quality gates |
| **Large** | New page, security feature, 6+ files, new components | Full: all checks including QA agent + PG agent |

State both classification and size to the user upfront:
> "This feature has UI → wireframe review needed. Size: Medium (new section, 3 files). It touches auth → security review at the end."

### Step 1.3: Design Document Check

If the project has design documents (check CLAUDE.md for location):

1. Search the design doc directory for specs related to the target feature
2. If found: read and summarize key requirements (screen items, API mappings, field specs)
3. If not found: note this in the plan — proceed but flag that no design doc exists
4. If implementation needs to deviate from the design doc: **report the reason to user and get approval before proceeding**

If the project has no design docs, skip this step.

---

## Phase 2: Wireframe & Approval

### Step 2.1: Wireframe (if UI involved)

Create an ASCII art wireframe for every screen or component change. Present it **before any code is written**.

**Wireframe format:**
```
┌─────────────────────────────────────────┐
│  Header / Navigation                    │
├─────────────────────────────────────────┤
│                                         │
│  Section Title                          │
│  ─────────────────                      │
│                                         │
│  ┌─────────────┐  ┌─────────────┐      │
│  │  Card A     │  │  Card B     │      │
│  │  - field 1  │  │  - field 1  │      │
│  │  - field 2  │  │  - field 2  │      │
│  └─────────────┘  └─────────────┘      │
│                                         │
│  ┌─────────────────────────────────┐   │
│  │  Form Area                      │   │
│  │  Label:  [____________]         │   │
│  │  Label:  [____________]         │   │
│  │  [Cancel]         [Save]        │   │
│  └─────────────────────────────────┘   │
│                                         │
│  (Mobile: cards stack vertically)       │
└─────────────────────────────────────────┘
```

**Must include:**
- Layout structure and component placement
- Key text labels and placeholder values
- Interactive elements (buttons, inputs, toggles, dropdowns)
- State variations that matter:
  - **Empty state** — what shows when there's no data?
  - **Error state** — what shows on validation failure?
  - **Loading state** — spinner? skeleton?
- Responsive behavior note (e.g., "Mobile: cards stack vertically")
- Design doc field mapping if a design doc exists

**After presenting the wireframe, STOP and wait for user approval.** Do not write any code. If the user requests changes, revise and present again.

### Step 2.2: Plan

After wireframe approval, enter Plan mode and include:
- Goal and scope
- Change size (Small / Medium / Large) and resulting verification level
- The approved wireframe (embedded or referenced)
- Tasks breakdown with clear order
- Which tasks need E2E tests
- Which tasks need security review
- Design doc references (if any)
- Component reuse candidates (list existing components that can be reused)

Get Plan approval before proceeding.

---

## Phase 3: Implement

### Step 3.1: Component Reuse Check

Before writing new components, check what already exists in the project's component directories. Creating a new component when an existing one works is wasteful — reuse first, create only when necessary.

### Step 3.2: Implement via Appropriate Skill

Delegate coding to the appropriate skill based on the project's tech stack:

| Stack | Skill | When |
|-------|-------|------|
| React/Next.js/Vue frontend | `/senior-frontend` | UI components, pages, client logic |
| Node/Express/Go backend | `/senior-backend` | API, services, business logic |
| Full-stack | `/senior-fullstack` | Both frontend and backend |
| React Native/Flutter | `/senior-frontend` | Mobile UI |

Provide the delegate with:
- The approved wireframe as the visual spec
- Design document references (if any)
- List of existing components to reuse
- The project's styling approach (detected in Project Detection)
- Any state variations from the wireframe (empty/error/loading)

The implementation must follow the approved wireframe exactly. Any deviation requires explicit user approval.

---

## Phase 4: Verification Battery

Verification depth depends on the change size determined in Phase 1. This avoids wasting time on full checks for trivial changes while ensuring complex changes are thoroughly vetted.

### Verification by Size

| Check | Small | Medium | Large |
|-------|:-----:|:------:|:-----:|
| 4.1 Visual Match | ✓ (quick) | ✓ (full) | ✓ (full + screenshot) |
| 4.2 Design Doc Alignment | if exists | ✓ | ✓ |
| 4.3 Console Error Check | skip | ✓ | ✓ |
| 4.4 Responsive Check | skip | skip | ✓ |
| 4.5 Accessibility Basics | skip | spot check | ✓ |
| 4.6 QA Agent Code Review | skip | skip | ✓ |

### Step 4.1: Visual Match Verification

Compare the implementation against the approved wireframe:

**Quick (Small):** Confirm layout and key elements are present.

**Full (Medium/Large):**
- [ ] Layout structure matches wireframe
- [ ] All components from wireframe are present
- [ ] Text labels and placeholders match
- [ ] Buttons and interactive elements are in correct positions
- [ ] State variations implemented (empty, error, loading)
- [ ] Responsive behavior works as noted in wireframe

**Full + Screenshot (Large only):** Use `/webapp-testing` to capture a screenshot and present it alongside the wireframe for comparison.

### Step 4.2: Design Document Alignment

If design docs exist:
- Cross-check every screen item listed in the spec
- Verify API mappings match (endpoints, request/response fields)
- Verify field names, types, and validation rules
- Report any discrepancies with specific line references

### Step 4.3: Console & Runtime Error Check (Medium+)

Run the dev server and check for issues:
- No console errors (TypeError, undefined, failed imports)
- No console warnings that indicate real problems
- No network errors (failed API calls, 404s)
- No framework-specific warnings (React key warnings, Vue reactivity warnings, etc.)

Use `/webapp-testing` to capture browser console output and verify clean.

### Step 4.4: Responsive Layout Check (Large only)

Verify the UI works at different viewport sizes:
- **Desktop** (1280px+): full layout as designed
- **Mobile** (375px): stacked layout, readable text, touchable buttons

Use `/webapp-testing` to capture screenshots at both sizes.

### Step 4.5: Accessibility Basics (Medium+)

**Spot check (Medium):** Form inputs have labels, buttons have text.

**Full (Large):**
- Images have `alt` attributes
- Form inputs have associated `<label>` elements
- Interactive elements are keyboard-navigable (Tab order)
- Color contrast is sufficient (no light gray on white)
- Focus indicators are visible

### Step 4.6: QA Agent Code Review (Large only)

Spawn the `qa` agent to review the implementation:
- Code patterns and naming conventions
- Type safety (no `any` casts without reason in TS projects)
- Component structure (single responsibility)
- No dead code or unused imports
- No hardcoded strings that should be constants
- Proper error handling at system boundaries

Report findings categorized as:
- **Must fix** — will cause bugs or embarrassment
- **Should fix** — code smell, may cause problems later
- **Nice to have** — style preference, optional

Fix all "Must fix" items before proceeding.

---

## Phase 5: Testing & Security

### Step 5.1: E2E Test (if connected flows exist)

**When to write E2E tests** (apply judgment):
- Authentication flows (login → redirect → guard)
- Multi-page connected flows (form → submit → result)
- Features where manual click-testing would be repeated 2+ times

**When NOT to write E2E tests:**
- Prototype / PoC (will be thrown away)
- Static pages with nothing to break
- Single component verification → use unit/component test instead

**E2E conventions:**
- Use the project's existing E2E framework and directory (detected in Project Detection)
- Follow existing test patterns in the project
- Run the project's E2E test command to verify all tests pass

### Step 5.2: Security Review (if security-sensitive)

For features touching auth, permissions, tokens, or personal data, spawn the `pg` (Privacy Guardian) agent to review:

- Secrets/credentials exposure
- Token handling (storage, transmission, expiry)
- Permission checks (route guards, API authorization)
- Personal data protection (no PII in console logs or URLs)
- XSS prevention
- CSRF protection
- Input validation at system boundaries

**Critical findings block the workflow** — must fix before proceeding.

---

## Phase 6: Quality Gates & Close

### Step 6.1: Quality Gates

Run available checks **in parallel** for speed — they are independent of each other. Use the commands detected from `package.json`:

```bash
# Run available gates simultaneously (only run what exists in the project)
[typecheck command] &   # e.g., npm run typecheck, tsc --noEmit
[lint command] &        # e.g., npm run lint, npx eslint .
[build command] &       # e.g., npm run build
[test command] &        # e.g., npm test, npm run test
wait
```

If any gate fails, fix the issues and re-run. Do not skip. If a gate doesn't exist in the project (e.g., no typecheck script), skip it.

### Step 6.2: Close Report

Present a structured report to the user. Adapt detail level to change size:

**Small changes — compact report:**
```
## Implementation Report
- Feature: [what was built]
- Files: [count] modified, [count] created
- Wireframe match: [PASS/FAIL]
- Quality gates: typecheck ✓ lint ✓ build ✓ test ✓
- Files: [list]
```

**Medium/Large changes — full report:**
```
## Implementation Report

### Summary
- Feature: [what was built]
- Size: [Small/Medium/Large]
- Files changed: [count] modified, [count] created

### Wireframe Match
- [PASS/FAIL] Layout matches approved wireframe
- [PASS/FAIL] All specified components present
- [PASS/FAIL] State variations implemented
- Screenshot: [link or inline] (Large only)

### Design Doc Alignment
- [PASS/N/A] Matches design spec
- Deviations: [list any, with reasons]

### Code Quality (Medium: gates only / Large: + QA review)
- [PASS/FAIL] No console errors
- [PASS/FAIL] Responsive layout verified (Large only)
- [PASS/FAIL] Accessibility basics checked
- [PASS/FAIL] QA review — [count] must-fix, [count] should-fix (Large only)

### Testing
- [PASS/N/A] E2E tests — [count] tests, all passing
- [PASS/N/A] Unit tests — existing tests still pass

### Security
- [PASS/N/A] PG review — [count] findings ([count] critical)

### Quality Gates
- [PASS/FAIL/N/A] typecheck
- [PASS/FAIL] lint
- [PASS/FAIL] build
- [PASS/FAIL] test

### Files
- [list of created/modified files with brief descriptions]
```

This report is what the user shows to developers. Make it clean and factual.
