# Security Policy

## Reporting a vulnerability

Report suspected vulnerabilities privately to **samarthdkolur1@gmail.com**, or through GitHub's private vulnerability reporting on this repository. Please do not open a public issue for a security problem.

Include what you can: affected component, reproduction steps, impact, and any proof of concept. Expect an acknowledgement within five working days.

## Supported versions

This project is pre-1.0. Only the `main` branch receives security fixes.

## What this project treats as a vulnerability

- Any path that exposes a Supabase service-role key, JWT secret or Groq API key to a browser client.
- Any query that returns another user's projects, constraint bundles or generated variants — that is, any gap in row level security.
- Authentication or session handling defects: token forgery, missing expiry checks, session fixation.
- Injection into the generation pipeline that causes the system to bypass scope enforcement or content thresholds.
- Dependency vulnerabilities rated HIGH or CRITICAL that are reachable from application code.

## What this project does not treat as a vulnerability

- A generated plot variant containing content a user finds objectionable. Generated output is **verified for scope**, never certified as compliant with any rating board; classification decisions belong to CARA, BBFC, CBFC and FSK. Report inaccurate constraint handling as a bug, not a vulnerability.
- Missing rate limits on unauthenticated endpoints that expose no data (`/health`).
- Findings that require an attacker to already hold the victim's valid session.

## Handling a leaked credential

If a credential reaches this repository, in this order:

1. **Rotate the key at the provider first.** History rewriting is slower than an attacker.
2. Remove it from the working tree and purge it from history.
3. Confirm with `bash scripts/secret-scan.sh` over the full history.
4. Record the incident and its timeline in the pull request that fixes it.

## Automated controls

Every pull request runs secret scanning (gitleaks, with rules covering Groq and Supabase credential formats), an environment-file guard, Python and Node dependency audits, Trivy filesystem and misconfiguration scans, and CodeQL. These are required status checks on `main`.
