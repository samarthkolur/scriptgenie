# Runbook

Operational procedures for ScriptGenie. Everything here is done in a provider
dashboard or a terminal; nothing here belongs in the repository, and no value
produced by these steps may be committed.

---

## Setting up Google OAuth

Three systems have to agree on one redirect URL. Most failures in this flow are
that agreement being broken in one of them.

### 1. Google Cloud — create the OAuth client

1. <https://console.cloud.google.com> → create or select a project.
2. **APIs & Services → OAuth consent screen**. External. Fill in the app name,
   support email and developer contact. Add the scopes `userinfo.email`,
   `userinfo.profile` and `openid` — nothing else. ScriptGenie reads a name, an
   email and a picture; requesting more would ask users to grant access the
   product does not use.
3. While the consent screen is in **Testing**, only accounts listed under **Test
   users** can sign in. Every other account gets `access_denied`, which our
   callback surfaces as a message on the sign-in page rather than a blank
   screen. Publish the app before anyone outside that list is expected to use
   it.
4. **Credentials → Create credentials → OAuth client ID → Web application**.
5. **Authorised redirect URIs** — this is Supabase's callback, not ours:

   ```
   https://<project-ref>.supabase.co/auth/v1/callback
   ```

   Google returns to Supabase; Supabase then returns to our `/auth/callback`.
   Putting our own URL here is the single most common mistake, and it fails
   with `redirect_uri_mismatch`.

6. Copy the **Client ID** and **Client secret**.

### 2. Supabase — enable the provider

1. Dashboard → **Authentication → Providers → Google** → enable.
2. Paste the client ID and secret. **These live in the dashboard and never in
   this repository** — the client secret is a real credential, and `gitleaks`
   runs on every commit and every push precisely so it cannot arrive here by
   accident.
3. Dashboard → **Authentication → URL Configuration**:
   - **Site URL** — the deployed origin: `https://scriptgenie-one.vercel.app`.
     Note the `-one`. `scriptgenie.vercel.app` is a different project on
     Vercel's shared namespace and is not ours.
   - **Redirect URLs** — every origin that may complete a sign-in. The path
     matters: entries must end in `/auth/callback`, because that is the only
     route that exchanges the PKCE code.

     ```
     http://localhost:3000/auth/callback
     https://scriptgenie-one.vercel.app/auth/callback
     https://scriptgenie-*-samarthkolurs-projects.vercel.app/auth/callback
     ```

     The wildcard entry covers Vercel preview deployments, which are named
     `scriptgenie-<build>-samarthkolurs-projects.vercel.app`. Without it,
     sign-in works in production and silently fails on every preview.

     **This list is not advisory, and getting it wrong does not produce an
     error.** Supabase ignores a `redirect_to` it does not recognise and
     substitutes the Site URL, so the user lands on `/?code=…` instead of
     `/auth/callback?code=…`. Nothing on `/` exchanges a code, so sign-in
     simply never completes and no message explains why. If you see a `code`
     query parameter on any page other than `/auth/callback`, this list is the
     reason.

### 3. This repository — point the apps at the project

`apps/web/.env.local`, from `apps/web/.env.example`:

```
NEXT_PUBLIC_SUPABASE_URL=https://<project-ref>.supabase.co
NEXT_PUBLIC_SUPABASE_ANON_KEY=<anon public key>
NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:8000
```

`apps/api/.env`, from `apps/api/.env.example`:

```
SUPABASE_URL=https://<project-ref>.supabase.co
SUPABASE_ANON_KEY=<anon public key>
SUPABASE_SERVICE_ROLE_KEY=<service role key>
ALLOWED_ORIGINS=http://localhost:3000
```

The **anon key is public** — it is inlined into the browser bundle, and every
row it reaches is reachable only through the row level security policies in
`supabase/migrations`. The **service role key bypasses row level security
entirely**. It belongs to the API and nowhere else; if it ever appears in
`apps/web`, it is in the browser bundle and must be rotated immediately.

### 4. Apply the schema

```bash
psql "$SUPABASE_DB_URL" -v ON_ERROR_STOP=1 -f supabase/migrations/20260729090000_core_schema.sql
psql "$SUPABASE_DB_URL" -v ON_ERROR_STOP=1 -f supabase/migrations/20260729090100_row_level_security.sql
```

Or `supabase db push` with the CLI linked to the project. Verify the policies
locally first with `pnpm test:db`.

### 5. Verify the whole chain

```bash
pnpm dev:api     # http://127.0.0.1:8000
pnpm dev         # http://localhost:3000
```

Visit `/app` while signed out. Expected, in order:

1. redirect to `/sign-in?next=%2Fapp`;
2. **Continue with Google** → Google consent → back to `/auth/callback?code=…`;
3. redirect to `/app`;
4. the page renders your name, email and join date.

Step 4 is the one that matters. That data does not come from the session
cookie — it comes from `GET /v1/me`, which verified your access token against
the project's JWKS and then read the row under that same token, so the database
decided what you were allowed to see. A profile on that page means the browser
session, the API's token verification and row level security all agree on who
you are.

---

## The local sign-in shortcut

Driving the app by hand means signing in repeatedly, and a full Google round
trip per reload is a tax on the kind of testing that finds what the test suite
cannot. `next dev` can offer a one-click sign-in instead.

**It is not an authentication bypass.** It signs in as a real Supabase user
with a password, so the token is genuine, the API still verifies it against the
project JWKS, and row level security still decides what that account can see.
Everything worth testing is API-backed — the wizard's options, the saved draft,
the conflict panel — so a forged session would render a signed-in shell in
which nothing loaded. A second credential is the only version that works.

### Set it up

1. Dashboard → **Authentication → Users → Add user**. Give it an email address
   you use nowhere else and a password you do not reuse, and tick **Auto
   Confirm User** — an unconfirmed account cannot sign in with a password.
2. Put both into `apps/web/.env.local`:

   ```
   DEV_LOGIN_EMAIL=local-tester@example.invalid
   DEV_LOGIN_PASSWORD=<the password you just set>
   ```

   Neither is `NEXT_PUBLIC_`, so neither reaches the browser bundle.

3. `pnpm dev` (or `pnpm dev:webpack`) → `/sign-in` now carries **Sign in as the
   local test account** below the Google button.

The first use seeds one project — the Phase 2 worked example, horror-comedy at
micro scale aimed at PG-13 for the US and India — so there is something with
real conflicts to open. It is created through the ordinary API under that
user's token, and it is skipped once the account has any project at all.

### Why it cannot leak into a deployment

`app/auth/dev-login/route.ts` returns **404** unless `NODE_ENV` is exactly
`development`, which `next build` and `next start` never set. The check is an
equality test, so an unset or misspelled value fails closed, and it is a
build-time constant rather than configuration — there is no dashboard toggle
that can turn it back on. Filling the two variables in on a deployed
environment does nothing.

Verified rather than assumed: a production build with both variables
deliberately set answers `404` to `POST /auth/dev-login` and omits the button
from `/sign-in`. Re-run that check if the gate is ever touched.

---

## When sign-in fails

| Symptom                                                 | Cause                                                                                                                                                         |
| ------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `redirect_uri_mismatch` at Google                       | Google's authorised redirect URI is not `https://<ref>.supabase.co/auth/v1/callback`                                                                          |
| Returns to `/sign-in` with "link has expired"           | The PKCE code was replayed or the exchange ran on a different origin than it started on                                                                       |
| `access_denied`                                         | The consent screen is in Testing and this account is not a test user                                                                                          |
| Signed out again about an hour after signing in         | `proxy.ts` is not running — check its `matcher` still covers page routes                                                                                      |
| `/v1/me` answers 401 with a verified session            | `SUPABASE_URL` differs between the two apps, so the API rejects a token from a different issuer                                                               |
| `/v1/me` answers 404 naming the signup trigger          | `20260729090000_core_schema.sql` has not been applied to this database                                                                                        |
| Lands on `/?code=…` rather than `/auth/callback?code=…` | The origin is missing from **Redirect URLs**, so Supabase discarded it and used the Site URL. Nothing on `/` exchanges a code, so this fails silently         |
| Every route returns 500, but `/favicon.ico` returns 200 | A `NEXT_PUBLIC_*` variable is unset, so `proxy.ts` throws before routing. `favicon.ico` is the one path its matcher excludes, which is what makes it the tell |
| Env vars look right in Vercel and the 500 persists      | `NEXT_PUBLIC_*` is inlined at build time — redeploy, with build cache off                                                                                     |
| The local test account button is not on `/sign-in`      | `NODE_ENV` is not `development` (a production build, or `next start`), or one of `DEV_LOGIN_EMAIL` / `DEV_LOGIN_PASSWORD` is blank                            |
| The local test account returns "could not sign in"      | The user does not exist in Supabase, the password differs, or the account was created without **Auto Confirm User**                                           |

---

## Rotating a leaked credential

1. **Groq** — <https://console.groq.com/keys>: delete the key, create a new
   one, update `GROQ_API_KEY` wherever the API runs. Deleting first is
   deliberate: a key that is still valid while a replacement is deployed is a
   key that is still leaked.
2. **Supabase service role / anon keys** — Dashboard → Settings → API → rotate.
   Rotating the anon key requires redeploying the web app, because it is baked
   into the bundle at build time.
3. **Google OAuth client secret** — Google Cloud → Credentials → reset the
   secret, then update it in Supabase's provider settings.
4. Run `gitleaks detect --source . --config .gitleaks.toml` over the full
   history to confirm the value was never committed. Removing a value from the
   working tree does not remove it from history, and history is what an
   attacker clones.
