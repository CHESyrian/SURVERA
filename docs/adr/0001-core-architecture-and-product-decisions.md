# ADR 0001: Core Architecture and Product Decisions

**Status:** Accepted  
**Date:** 2026-08-25  
**Deciders:** Project team  
**Tags:** architecture, product, mvp, i18n, rewards, multi-tenancy

---

## Context

We are building **SURVERA**, a hybrid survey platform that serves both:

- **Companies** – create paid surveys, target audiences, collect responses, and access analytics/exports.
- **Persons** (participants) – take surveys, earn coins, gain XP/levels/badges, and can also create limited free or restricted paid surveys.

The platform must support rich question types, conditional logic (later), privacy controls, anti-fraud measures, points vs XP separation, company teams, subscriptions, and bilingual (English/Arabic) experience.

This ADR records the foundational product and technical decisions so the team shares a single source of truth before implementation begins.

---

## Product Decisions

### 1. Launch Focus
We launch to **both Companies and Persons simultaneously**.

### 2. MVP Definition
The minimum viable product is:

> A Company can create a survey with at least 5 question types, set a reward (points), collect completed responses, and export results as CSV.

Additional features (advanced conditionals, full analytics dashboards, subscriptions, badges, etc.) come after this core loop is solid.

### 3. Privacy Model
Surveys support a **mix of anonymous and identified** participation. Strong identity verification is not required in the first version.

### 4. Survey Editing Rule
Once a survey receives its first response, the **survey definition is frozen**.  
Questions, logic, and core settings cannot be changed in a way that invalidates existing answers.  
(Future: versioning or “create new version” may be added later.)

### 5. Who Can Create Surveys

| Actor     | Free Surveys                          | Paid Surveys                                      |
|-----------|---------------------------------------|---------------------------------------------------|
| Company   | Full capability                       | Full capability (response targets, rewards, etc.) |
| Person    | Limited number, earns XP only         | Limited, under specific conditions, limited earnings |

Exact limits will be defined in configuration / subscription plans later.

### 6. Rewards Model
- **Points** (redeemable currency): awarded **only** for completing surveys.
- **XP** (experience / progression): awarded for completing surveys **and** other activities (referrals, daily login, profile completion, etc.).
- Levels, ranks, and badges are driven by XP, not by points.
- Full transaction history is kept for points.

### 7. Languages
The platform is **bilingual from day one**: English and Arabic.  
This includes UI, survey content, and RTL support for Arabic.

### 8. Team & Timeline
- Built by a **team**.
- **No hard deadline** → we optimize for clean, maintainable architecture and long-term velocity.

---

## Technical Decisions

### 1. Architecture Style
**Modular Monolith** using Django.

- Clear domain boundaries via Django apps.
- Single deployable unit (suitable for VPS).
- Easy to extract services later if needed.
- Avoids premature microservices complexity.

### 2. Backend Stack
- **Python** + **Django 5.x**
- **Django REST Framework** only where an API is genuinely useful (most interactions will be server-rendered).
- **PostgreSQL** as the primary database.
- **Redis** for caching, rate limiting, and background task broker.
- **Celery** (or equivalent) for background jobs (exports, notifications, trust recalculation, etc.).

### 3. Frontend Strategy
**Django templates + HTMX + Alpine.js**

- Fast iteration and lower complexity for a team.
- Progressive enhancement.
- Good enough for the MVP and early growth phases.
- Can introduce a richer SPA later for specific complex screens (analytics, survey builder) if needed.

### 4. Authentication
- Email + password only at the start.
- Email verification required.
- Social login / magic link / phone OTP deferred.

### 5. Primary Keys
**BigAutoField** (default Django AutoField / BigAutoField).

- Simple, performant for joins and analytics.
- Sequential IDs are acceptable for this domain.

### 6. Multi-tenancy & Permissions
- Companies are first-class tenants.
- All company-owned data is scoped by `company_id`.
- Object-level permissions enforced on every relevant query and action.
- Persons can act both as participants and (limited) survey creators.

### 7. Internationalization
- Django’s built-in i18n + `gettext`.
- RTL support for Arabic.
- Language switcher and per-user language preference.
- Survey content itself must support bilingual questions/answers where needed.

### 8. Hosting
Target deployment is a **VPS**.  
Configuration and deployment scripts will assume a traditional Linux server (Docker optional but not mandatory in v1).

### 9. Core Domain Separations (non-negotiable)
- `Survey` is the aggregate root for questions, settings, and status.
- `Response` is a separate aggregate (one participation event).
- `Answer` belongs to a Response and references a Question.
- Points ledger is completely separate from XP/Levels.
- Audit log for sensitive actions.

---

## Consequences

### Positive
- Team has a shared understanding of MVP scope and technical direction.
- i18n and RTL are considered from the first models and templates.
- Freezing surveys prevents data integrity problems.
- Clear Points vs XP split avoids future economic design pain.
- Server-rendered + HTMX approach keeps the stack simple and productive for the team.

### Negative / Trade-offs
- BigAutoField makes IDs enumerable (mitigated by proper authorization).
- Freezing surveys means companies must plan questions carefully (or we add versioning later).
- HTMX/Alpine will eventually hit limits on very complex interactive UIs (survey builder, advanced analytics) — we accept this for the MVP.
- Supporting Arabic + English from day one adds some upfront cost in templates and models.

### Risks to watch
- Scope creep beyond the defined MVP.
- Under-estimating anti-fraud needs once paid surveys go live.
- Performance of analytics queries as response volume grows (address with proper indexes and later materialized views / separate analytics store).

---

## Follow-up ADRs (expected)

- ADR 0002: Detailed domain model (Survey, Question, Response, Answer, Points, XP…)
- ADR 0003: Permission & role matrix (Company roles + Person capabilities)
- ADR 0004: Survey freezing / versioning mechanism
- ADR 0005: i18n & RTL implementation approach
- ADR 0006: Background job and export strategy

---

## References

- Product feature list (original 25-point vision)
- Clarifying Q&A (2026-08-25)
- Week-1 implementation plan

---

**Next step:** Proceed to Day 1 – Project bootstrap and engineering baseline.
