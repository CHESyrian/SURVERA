# SURVERA – Product Sections (Team Reference)

Short overview of the main product areas and current rules. Keep this file up to date as features land.

---

## 1. Accounts & Identity
- Custom `User` model (`apps.accounts`)
- Email + password auth (register / login / logout / profile)
- Password strength meter + show/hide toggle on register/login
- **Email verification by 6-digit code** (required for take/create survey, points, XP, badges, CSV export, create company). **Superusers** are auto-verified on create/promote and skip the gate.
- Verification **resend rate limit**: 1 code / 60s (self-serve); admin can resend with bypass
- Admin actions: mark verified / unverified, resend verification code
- **Cloudflare Turnstile** on register + verification resend (optional; `TURNSTILE_ENABLED`)
- Bilingual UI (EN / AR) from day one
- Light / dark theme switcher

## 2. Companies & Teams
- Company entity + membership
- Product roles: **owner**, **moderator**, **participant** (legacy admin/researcher/analyst/viewer mapped in code only)
- **Owner**: full company control (team + surveys); created automatically on company creation
- **Moderator**: surveys (create/publish/export) + invite **participants** only
- **Participant**: take surveys only
- Team management UI (assignable roles depend on inviter)

## 3. Surveys
- Owned by a **Company** only (required FK; no personal surveys; `created_by` is audit only)
- **Who creates**: company owner/moderator, or project **superuser**
- **Who takes**: any person (Discover / take flow)
- **Question types**: text, single/multi choice, rating, yes/no, number, date, ranking, matrix
- Conditional logic via `Question.conditions` (JSON)
- Survey freezes after the first response
- `expires_at` + **targeting** (members_only, min/max age, genders, min_level, **min reputation level** 1–7)
- **Reputation** (`honor_points`) is the only trust metric; **7 levels** derived from it. No separate trust score in product UI.
- Visibility: **public** (Discover) vs **private** (invite/targeting only)
- Rules:
  - **Company** → free or paid surveys; targeting on forms
  - **Free** → public, no coins, no targeting, XP only
  - **Paid** → may grant coins; may be private + targeted

## 4. Responses & Answers
- Take-survey flow (HTMX + Alpine)
- Server-side answer validation
- Freeze on first response
- **Response detail**: managers can open a response and see each question + answer
- CSV export of results (**no participant PII** — no email/name/user id; only `response_id`, `completed_at`, answers)
- Survey analytics: totals, completion rate, target progress, 14-day bar chart, **status donut**, horizontal bars per question (`get_survey_analytics`)

## 5. Rewards & Progression
- **Points**: awarded only for completing **paid** surveys (`is_paid` and `points_reward > 0`). **Score-only for now** — no redemption / wallet yet (planned later).
- **XP / Levels / Badges**: **25 levels × 1000 XP** each; daily login, survey completion, tasks, etc.
- Profile progress UI
- Points and XP are deliberately distinct
- **Profile badges**: full catalog on profile (earned + locked with progress); criteria `min_level`, `min_surveys_completed`, `min_surveys_created`, `min_honor`; evaluated on XP award and profile visit; seed via `manage.py seed_badges`
- **Leaderboard** (`/rewards/leaderboard/`): three tabs — Reputation (persons), XP (persons), Companies (by completed responses). Top **100** each; gold/silver/bronze for ranks 1–3; **Load more** every **25** rows (HTMX); viewer rank footer when outside the visible list / top 100.


## 5c. Reputation & Trust levels
- **Reputation** (UI name for `honor_points`): reputation ledger (not survey Points, not XP)
- Increased by **daily / weekly task completion**, quality responses, and onboarding grants
- **Reputation levels (7)** from `honor_points`: Newcomer 0–99 · Contributor 100–199 · Trusted 200–399 · Reliable 400–599 · Proven 600–899 · Elite 900–1499 · Distinguished 1500+
- Onboarding grants (once each): **+10** registration · **+20** email verified · **+20** basic profile (DOB + gender)
- Survey targeting uses **reputation level** (1–7), not a separate score
- Ledger: `HonorEvent` via `apply_honor_delta` / grant helpers
- **Quality scoring (v1)**: on complete → score 0–100 (completeness, pace, pattern, substance) → tier → capped honor (`QualityAssessment`)
- **Reports + penalty catalog** (shipped): warnings ladder, honor deduction, rank reduction, freeze, permanent close

## 5b. Notifications (in-app)
- App: `apps.notifications`
- Types: survey_published, points_awarded, team_invite, system
- On **publish**: notify eligible company members (targeting / private respected); publisher excluded
- On **points award**: notify participant
- On **team invite / re-invite**: notify the member (`TEAM_INVITE`); link to company team page; **email** queued via Celery
- On **publish**: in-app via Celery task; **email** only for private / members_only surveys
- Navbar bell + HTMX badge poll (45s); list at `/notifications/`; open marks read and follows link
- Settings: `SITE_URL` for absolute email links; `CELERY_*` for async fan-out
- **Preferences**: per-type in-app + email toggles on profile settings (`NotificationPreference`)
- **Email digests**: daily / weekly / off (`email_digest`); summarizes unread notifications; Celery beat + `manage.py send_digests --frequency=daily|weekly`
- **Test notifications**: staff “Send test” on notifications list; `manage.py send_test_notification [--email=…]`
- **EMAIL_FOR_TEST** (`surveracorp.test@gmail.com`): receiver for local/manual email tests; `EMAIL_REDIRECT_TO_TEST` redirects all outbound mail there in local; `manage.py send_test_email --kind=all`

## 6. Frontend & UX
- Django templates + HTMX + Alpine.js
- Stylesheet: `static/css/survera.css`
- Discover + filters
- Take-survey UI improvements

## 7. Platform Rules (Quick Reference)
| Actor       | Role                                              |
|-------------|---------------------------------------------------|
| Company     | Owner/moderator create & publish free or paid     |
| Superuser   | Can create surveys for any company                |
| Person      | Take surveys only (Discover); earn XP / points    |
| Free survey | Public; XP only                                   |
| Paid survey | May grant coins; optional private + targeting    |

**Core loop (MVP complete):** create → publish → respond → points → CSV export

### Hardening (2026-08-27)
- Role checks unified on `can_manage_surveys` / `can_manage_team` (owner + moderator; legacy admin kept)
- Frozen / non-draft surveys blocked from edit views
- Publish only from draft; idempotent when already active
- Points awarded only when `is_paid` **and** `points_reward > 0`
- CSV export / response list restricted to survey managers (or superuser)
- Membership re-invite reactivates soft-removed rows
- Initial migrations + pytest coverage for roles and core loop

### Targeting (2026-08-27)
- Form persists `targeting` JSON (members_only, age, gender, level, trust)
- `can_access_survey` enforces private + targeting on take
- Discover excludes private and non-member `members_only` surveys
- Detail shows audience targeting summary

---

*See also: `docs/adr/0001-core-architecture-and-product-decisions.md`*


## 8. Internationalization (EN / AR)
- `LocaleMiddleware` + language switcher in navbar (`set_language`)
- Catalogs: `locale/ar/LC_MESSAGES/django.{po,mo}` and `locale/en/...`
- After adding new `{% trans %}` / `gettext` strings:
  1. `make makemessages` (or `django-admin makemessages -l ar`)
  2. Translate in `.po`
  3. `make compilemessages`
- Bootstrap RTL via `dir="rtl"` when `LANGUAGE_CODE == ar` in `base.html`
- Run once: ensure compiled `.mo` files are deployed with the app


## 5d. Tasks & Reports
- **Tasks** (`/rewards/tasks/`): daily (3 surveys → +5 **Reputation**, +50 XP), weekly (10 → +5 Reputation, +100 XP); auto-grant on complete
- **Reports & penalties** (admin control panel):
  1. Manager submits report (type + note) on a response
  2. Staff open the report in admin — related survey/response/answers/users + warning count shown
  3. **Penalty catalog** (action *Apply penalty & notify* → in-app + email to reporter **and** subject):
     - **Warning** (progressive): 1st −100 honor · 2nd −200 honor · 3rd freeze 7d · 4th freeze 30d · 5th+ permanent close
     - **Honor deduction**: admin-chosen honor amount
     - **Rank reduction**: drop N trust levels (e.g. 7→6)
     - **Account freeze**: admin-chosen days
     - **Permanent account closure**
  4. **Dismiss**: action *Dismiss report & notify* → no penalty → notify reporter only
  - User fields: `warning_count`, `frozen_until`, `closed_at`; frozen/closed accounts cannot log in
  - Service: `apps.responses.penalties`
