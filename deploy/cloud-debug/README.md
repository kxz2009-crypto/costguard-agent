# CostGuard Split cloud-debug deployment gate

This bundle replaces the current landing page at
`costguardsplit.nuxnow.com` with the Split API intentionally and only for the
synthetic debug environment. It is not a production deployment design.

## Runtime contract and red lines

- One container, one Uvicorn process, one worker, because `RequestScope` owns
  one shared SQLite connection and serializes complete requests.
- The fixed, clearly synthetic organization/actor defaults are server-side
  context, not production authentication. Override them only with other
  synthetic identifiers. Clients cannot select an organization.
- Nginx Basic Auth is the entire debug access gate. The app itself has no
  production auth. Never publish container port 8080 or host port 18080 beyond
  `127.0.0.1`.
- The named volume contains synthetic data only. Never copy, migrate, or mount
  real CostGuard data, logs, credentials, `.env`, htpasswd, or TLS keys here.
- No telemetry or external callback is configured. Do not add billing,
  subscription, payment, P2, or production authentication work to this bundle.

## Prerequisites and preflight

Run on the authorized host only after reviewer/deployment approval:

1. Docker and Compose are installed; host Nginx owns ports 80/443.
2. Cloudflare DNS for `costguardsplit.nuxnow.com` resolves to the intended host
   and proxy/TLS mode matches the existing `*.nuxnow.com` origin-cert pattern.
3. Existing certificate and key paths cover `costguardsplit.nuxnow.com`.
4. Create a root-owned htpasswd outside the checkout (`0640`, readable by the
   Nginx worker group). Generate credentials interactively; do not put them in
   shell history, Compose, Git, or this document.
5. Confirm host port 18080 is unused and firewall policy exposes only 80/443.
6. Back up the current enabled Nginx site and record the currently deployed Git
   revision. `docker compose config` and `nginx -t` must pass before changes.

## Exact deployment steps

The deployer chooses `DEPLOY_ROOT`, `DEPLOY_TLS_CERTIFICATE_PATH`,
`DEPLOY_TLS_PRIVATE_KEY_PATH`, and `DEPLOY_HTPASSWD_PATH` for the authorized
host. Do not substitute private material into the committed template.

1. Place a reviewed checkout at `$DEPLOY_ROOT` and verify its exact commit.
2. Run `docker compose -f deploy/cloud-debug/compose.yaml config`.
3. Run `docker compose -f deploy/cloud-debug/compose.yaml build --pull`.
4. Run `docker compose -f deploy/cloud-debug/compose.yaml up -d --wait`.
5. Verify `curl --fail http://127.0.0.1:18080/healthz` on the host and verify
   `docker compose ... ps` reports exactly one healthy backend container.
6. Copy the Nginx template to a temporary site file, replace only its three
   `DEPLOY_*` path placeholders, then run `nginx -t`.
7. Enable this dedicated `server_name` and reload Nginx. Do not restart it and
   do not modify unrelated virtual hosts.
8. Complete all runtime acceptance checks below before declaring deployment.

## Runtime acceptance

- DNS/Cloudflare: the hostname resolves as intended; HTTPS presents the
  expected certificate chain; direct origin policy matches the existing host
  policy. Record facts, do not infer them from a Cloudflare success page.
- Edge/auth: HTTP redirects to HTTPS. HTTPS without or with bad Basic Auth is
  `401`; valid Basic Auth reaches `/healthz`. Responses include
  `Cache-Control: no-store`.
- Exposure/firewall: public scans cannot reach 18080/8080; Compose publishes
  only `127.0.0.1:18080`; Nginx proxies only to that address.
- Runtime identity/topology: container user is non-root; exactly one backend
  container/process serves requests; health is `healthy`.
- Tenant guard: a consumption request whose `org_id` differs from the configured
  synthetic organization returns `404`.
- Synthetic flow: register a synthetic device; ingest one synthetic event;
  replay it and verify deduplication returns the same event; fetch report JSON;
  render that JSON with the installed `render_report_html` and verify complete
  HTML. Use only obvious synthetic identifiers and TEST-NET addresses.
- Concurrency: concurrent synthetic member/event writes complete without 5xx
  and all accepted writes are present.
- Persistence is a two-phase check. First run full acceptance; it reads back
  every accepted concurrent member, then atomically writes the expected
  synthetic device and event plus every member currently returned by the API
  (member ID, display name, and status), in deterministic order, with row counts to
  `/data/acceptance-expected.json` in the named volume. Then record the backend
  container ID and actually recreate the container without deleting the volume:

      before=$(docker compose -f deploy/cloud-debug/compose.yaml ps -q backend)
      docker compose -f deploy/cloud-debug/compose.yaml exec -T backend python /app/acceptance.py
      docker compose -f deploy/cloud-debug/compose.yaml up -d --force-recreate --wait
      after=$(docker compose -f deploy/cloud-debug/compose.yaml ps -q backend)
      test "$before" != "$after"
      docker compose -f deploy/cloud-debug/compose.yaml exec -T backend python /app/acceptance.py --restart-check

  The restart check fails closed if the manifest is absent, corrupt, or differs
  from the complete expected device/event/member state and counts. Never replace
  recreation with a second in-process call, and never use `down -v` during a
  normal deploy/restart.

The image's `/app/acceptance.py` automates the app-level checks from inside the
container without bypassing the edge gate publicly. The initial run only
creates/verifies synthetic state and writes the manifest; it does not claim
restart persistence. Only after the container ID-changing recreation above may
`--restart-check` claim persistence by comparing the manifest with current
state.
Edge TLS/auth/firewall checks stay separate and must be exercised through Nginx.

## Backup and rollback

Before upgrade, stop writes, record the image/commit, and back up the named
volume with a temporary container to a root-only archive outside the checkout.
The backup is synthetic but should still be handled as private debug data.

Rollback order:

1. Restore the prior dedicated Nginx site (or disable this site to restore the
   previous default/landing-page behavior), run `nginx -t`, then reload Nginx.
2. Run the prior reviewed image/checkout with the same named volume if schema
   compatibility was explicitly verified. Otherwise stop and restore the volume
   backup before starting the prior image.
3. Verify edge behavior and firewall exposure again. Preserve failed container
   metadata for diagnosis, but do not commit logs or databases.

Do not claim deployment from this repository change. DNS, Cloudflare, origin
TLS, host firewall, Nginx activation, backup, and rollback are cloud-only checks
for the authorized deployer/reviewer.