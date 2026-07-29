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
   - **Site URL** — the deployed origin, e.g. `https://scriptgenie.vercel.app`.
   - **Redirect URLs** — every origin that may complete a sign-in:

     ```
     http://localhost:3000/auth/callback
     https://scriptgenie.vercel.app/auth/callback
     https://*-scriptgenie.vercel.app/auth/callback
     ```

     The wildcard entry covers Vercel preview deployments. Without it, sign-in
     works in production and silently fails on every preview.

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

## When sign-in fails

| Symptom                                         | Cause                                                                                           |
| ----------------------------------------------- | ----------------------------------------------------------------------------------------------- |
| `redirect_uri_mismatch` at Google               | Google's authorised redirect URI is not `https://<ref>.supabase.co/auth/v1/callback`            |
| Returns to `/sign-in` with "link has expired"   | The PKCE code was replayed or the exchange ran on a different origin than it started on         |
| `access_denied`                                 | The consent screen is in Testing and this account is not a test user                            |
| Signed out again about an hour after signing in | `proxy.ts` is not running — check its `matcher` still covers page routes                        |
| `/v1/me` answers 401 with a verified session    | `SUPABASE_URL` differs between the two apps, so the API rejects a token from a different issuer |
| `/v1/me` answers 404 naming the signup trigger  | `20260729090000_core_schema.sql` has not been applied to this database                          |

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
