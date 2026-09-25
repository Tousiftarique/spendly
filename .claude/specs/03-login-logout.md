# Spec: Login and Logout

## Overview
Implement session-based authentication so registered users can sign in and out of Spendly. This step upgrades the existing stub `GET /login` route to also accept a `POST` that verifies credentials against the `users` table and starts a Flask session, and replaces the `GET /logout` placeholder with a real handler that clears the session. This is the step that turns the app from "anyone can view any page" into "pages know who is signed in," which every later step (profile, expenses) depends on.

## Depends on
- Step 01 — Database setup (`users` table, `get_db()`)
- Step 02 — Registration (users must exist before they can log in)

## Routes
- `GET /login` — render login form — public (already exists, unchanged)
- `POST /login` — verify email/password, start session, redirect to `/` — public (new handler on existing route)
- `GET /logout` — clear session, redirect to `/login` — logged-in only (upgrade stub)

## Database changes
No new tables or columns. The existing `users` table covers all requirements.

A new DB helper must be added to `database/db.py`:
- `get_user_by_email(email)` — returns the full user row (`id`, `name`, `email`, `password_hash`) for the given email, or `None` if no match. Needed because the existing `email_exists()` only returns a boolean and can't be used to verify a password.

## Templates
- **Modify:** `templates/login.html`
  - Change the form `action` from the hardcoded `"/login"` to `url_for('login')`
  - The template already has an `{% if error %}` block — wire it up to display the flashed login error
- **Modify:** `templates/base.html`
  - Nav links must reflect session state: when no user is logged in, show "Sign in" / "Get started" (current behavior); when a user is logged in, show a "Logout" link (`url_for('logout')`) instead of "Sign in"

## Files to change
- `app.py` — upgrade `login()` to handle `GET` and `POST`; implement `logout()` to clear the session and redirect
- `database/db.py` — add `get_user_by_email()` helper
- `templates/login.html` — fix form action, wire up error display
- `templates/base.html` — make nav links session-aware

## Files to create
None.

## New dependencies
No new dependencies. Uses Flask's built-in `session` object and `werkzeug.security.check_password_hash` (already installed).

## Rules for implementation
- No SQLAlchemy or ORMs
- Parameterised queries only — never use f-strings in SQL
- Passwords hashed with werkzeug — verify with `werkzeug.security.check_password_hash`, never compare plaintext
- Use CSS variables — never hardcode hex values
- All templates extend `base.html`
- Use `session['user_id']` to track the logged-in user — no new dependencies for auth
- On failed login (unknown email OR wrong password), flash one generic message: "Invalid email or password" — never reveal which field was wrong
- On successful login, flash a success message and redirect to `url_for('landing')`
- `GET /logout` must clear the entire session (`session.clear()`) and redirect to `url_for('login')`
- Use `abort(405)` if an unsupported HTTP method reaches `/login`
- Use `url_for()` for every internal link — never hardcode URLs

## Definition of done
- [ ] `GET /login` renders the login form without errors
- [ ] `POST /login` with the seeded demo credentials (`demo@spendly.com` / `demo123`) logs in and redirects, with `session['user_id']` set
- [ ] `POST /login` with a wrong password re-renders the form with "Invalid email or password", no session set
- [ ] `POST /login` with an email that doesn't exist re-renders the form with the same generic error, no session set
- [ ] `GET /logout` clears the session and redirects to `/login`
- [ ] Nav bar shows "Sign in" when logged out and "Logout" when logged in
- [ ] No plaintext password comparison anywhere in the codebase
