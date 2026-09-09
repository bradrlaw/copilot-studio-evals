"""
Copilot Studio Evaluation Runner (Power Platform API)
=====================================================
Runs a Copilot Studio built-in evaluation *test set* against an agent from the
command line, using the Power Platform REST API's `makerevaluation` operations,
then polls for completion and writes the per-test-case results to CSV plus a
pass-rate summary. This automates the portal "upload CSV + click Run" step so it
can be used for regression / CI checks.

Docs: https://learn.microsoft.com/en-us/microsoft-copilot-studio/analytics-agent-evaluation-rest-api

What this does NOT do
---------------------
The API *runs* an existing test set; it does not create one. Upload the eval CSV
in Copilot Studio once to create a named test set (see docs/), then use this
script to run it repeatedly and pull results.

Authentication
--------------
The Power Platform API requires a token from an Entra identity that has the
Copilot Studio maker-evaluation permission (delegated
`CopilotStudio.MakerOperations.ReadWrite`, or the app-only equivalent) and is
added as an Application User in the target environment. Supported modes:

  1. --token <BEARER>  (or env POWERPLATFORM_TOKEN)
                       -> auth-agnostic; recommended for CI. Authenticate in the
                          workflow via OIDC workload-identity federation
                          (azure/login) and mint the token with
                          `az account get-access-token --resource
                          https://api.powerplatform.com`.
  2. --managed-identity [--mi-client-id <ID>]
                       -> Azure managed identity via IMDS. Only works on Azure
                          compute / self-hosted runners (not GitHub-hosted).
  3. --client-id <APP> --client-secret <SECRET>  (or env PP_SP_CLIENT_SECRET)
                       -> service-principal client-credentials flow.
  4. --client-id <APP> (no secret)
                       -> interactive OAuth 2.0 device-code flow (local use).
  5. (fallback) an Azure CLI token, if the signed-in client is scoped.

Behind an SSL-inspecting corporate proxy, set REQUESTS_CA_BUNDLE to a PEM that
includes the corporate root CA (same as run_kql_query.py).

Usage
-----
    # List the test sets defined on the agent (find the display name / id)
    python run_copilot_eval.py list --env-id <ENV> --bot-id <BOT> --client-id <APP>

    # Run a single test set by name, poll to completion, write results CSV
    python run_copilot_eval.py run --env-id <ENV> --bot-id <BOT> --client-id <APP> \
        --test-set-name "Agent regression" \
        --mcs-connection-id <CONN> --output results.csv

    # CI GATE: run every test set matching a glob, fail below a pass threshold
    python run_copilot_eval.py gate --env-id <ENV> --bot-id <BOT> \
        --pattern "deploy-test-*" --pass-threshold 1.0 --output eval-results.json
    # (auth via env POWERPLATFORM_TOKEN; add --config to drive selection from a file)

    # Fetch results for a prior run id
    python run_copilot_eval.py results --env-id <ENV> --bot-id <BOT> --client-id <APP> \
        --run-id <RUN> --output results.csv

Arguments common to all commands:
    --env-id       Power Platform Environment ID (GUID).
    --bot-id       Agent / Bot ID (GUID). Copilot Studio > agent > Settings.
    --client-id    Entra app registration (public client) ID for device-code auth.
    --tenant       Tenant ID for device-code auth (default: 'organizations').
    --token        Pre-acquired bearer token (skips interactive auth).
    --api-version  API version (default 2024-10-01).
"""

import argparse
import csv
import fnmatch
import json
import os
import shutil
import ssl
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

PPAPI_BASE = "https://api.powerplatform.com"
DEFAULT_API_VERSION = "2024-10-01"
POWERPLATFORM_RESOURCE = "https://api.powerplatform.com"
DEFAULT_SCOPE = "https://api.powerplatform.com/.default offline_access"
# App-only (service principal / client-credentials) scope -- no offline_access.
CLIENT_CRED_SCOPE = "https://api.powerplatform.com/.default"
# Azure Instance Metadata Service (IMDS) endpoint for managed-identity tokens.
# Only reachable when the job runs on Azure compute (self-hosted runner, VM,
# Container App, etc.). GitHub-hosted runners cannot reach IMDS -- use OIDC
# federation + `az account get-access-token` and pass --token instead.
IMDS_TOKEN_URL = "http://169.254.169.254/metadata/identity/oauth2/token"

# Run states that mean "still working"; anything else ends the poll loop.
RUNNING_STATES = {"running", "inprogress", "in_progress", "notstarted",
                  "queued", "pending"}


def _ssl_context() -> ssl.SSLContext | None:
    """Build an SSL context honoring REQUESTS_CA_BUNDLE / SSL_CERT_FILE."""
    ca = os.environ.get("REQUESTS_CA_BUNDLE") or os.environ.get("SSL_CERT_FILE")
    if ca and os.path.exists(ca):
        return ssl.create_default_context(cafile=ca)
    return None


# --------------------------------------------------------------------------- #
# Authentication
# --------------------------------------------------------------------------- #
def find_az() -> str | None:
    for cand in ("az", "az.cmd"):
        p = shutil.which(cand)
        if p:
            return p
    win = r"C:\Program Files\Microsoft SDKs\Azure\CLI2\wbin\az.cmd"
    return win if os.path.exists(win) else None


def token_via_az() -> str | None:
    az = find_az()
    if not az:
        return None
    try:
        out = subprocess.run(
            [az, "account", "get-access-token", "--resource",
             POWERPLATFORM_RESOURCE, "--query", "accessToken", "-o", "tsv"],
            capture_output=True, text=True, timeout=60)
    except Exception:
        return None
    if out.returncode != 0:
        return None
    tok = out.stdout.strip()
    return tok or None


def _post_form(url: str, fields: dict) -> tuple[int, dict]:
    data = urllib.parse.urlencode(fields).encode("utf-8")
    req = urllib.request.Request(url, data=data, method="POST")
    req.add_header("Content-Type", "application/x-www-form-urlencoded")
    try:
        with urllib.request.urlopen(req, context=_ssl_context(), timeout=60) as r:
            return r.status, json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "replace")
        try:
            return e.code, json.loads(body)
        except json.JSONDecodeError:
            return e.code, {"error": "http_error", "error_description": body}


def token_via_device_code(tenant: str, client_id: str,
                          scope: str = DEFAULT_SCOPE) -> str:
    """Interactive OAuth 2.0 device-code flow using only the standard library."""
    base = f"https://login.microsoftonline.com/{tenant}/oauth2/v2.0"
    status, dc = _post_form(f"{base}/devicecode",
                            {"client_id": client_id, "scope": scope})
    if status != 200 or "device_code" not in dc:
        print("Failed to start device-code flow:")
        print(json.dumps(dc, indent=2))
        sys.exit(1)

    print("\n" + "=" * 60)
    print(dc.get("message", "Sign in to continue."))
    print("=" * 60 + "\n", flush=True)

    interval = int(dc.get("interval", 5))
    deadline = time.time() + int(dc.get("expires_in", 900))
    device_code = dc["device_code"]
    while time.time() < deadline:
        time.sleep(interval)
        status, tok = _post_form(f"{base}/token", {
            "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
            "client_id": client_id,
            "device_code": device_code,
        })
        if status == 200 and "access_token" in tok:
            return tok["access_token"]
        err = tok.get("error")
        if err == "authorization_pending":
            continue
        if err == "slow_down":
            interval += 5
            continue
        print("Device-code auth failed:")
        print(json.dumps(tok, indent=2))
        sys.exit(1)
    print("Timed out waiting for device-code sign-in.")
    sys.exit(1)


def token_via_client_credentials(tenant: str, client_id: str,
                                 client_secret: str) -> str:
    """App-only OAuth 2.0 client-credentials flow (service principal)."""
    base = f"https://login.microsoftonline.com/{tenant}/oauth2/v2.0"
    status, tok = _post_form(f"{base}/token", {
        "grant_type": "client_credentials",
        "client_id": client_id,
        "client_secret": client_secret,
        "scope": CLIENT_CRED_SCOPE,
    })
    if status == 200 and "access_token" in tok:
        return tok["access_token"]
    print("Client-credentials auth failed:")
    print(json.dumps(tok, indent=2))
    sys.exit(1)


def token_via_managed_identity(client_id: str | None = None) -> str:
    """Fetch a Power Platform API token from the Azure IMDS managed-identity
    endpoint. `client_id` selects a specific user-assigned identity; omit it for
    the system-assigned identity. Requires the job to run on Azure compute."""
    params = {"api-version": "2018-02-01", "resource": POWERPLATFORM_RESOURCE}
    if client_id:
        params["client_id"] = client_id
    url = f"{IMDS_TOKEN_URL}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, method="GET")
    req.add_header("Metadata", "true")
    try:
        with urllib.request.urlopen(req, context=_ssl_context(), timeout=30) as r:
            tok = json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "replace")
        print(f"Managed-identity token request failed (HTTP {e.code}): {body[:500]}")
        sys.exit(1)
    except urllib.error.URLError as e:
        print("Could not reach the IMDS endpoint for managed identity "
              f"({e.reason}). Managed identity only works on Azure compute; on "
              "GitHub-hosted runners use OIDC federation + --token instead.")
        sys.exit(1)
    if "access_token" in tok:
        return tok["access_token"]
    print("Managed-identity endpoint returned no access_token:")
    print(json.dumps(tok, indent=2))
    sys.exit(1)


def get_token(args) -> str:
    if args.token:
        return args.token
    env_tok = os.environ.get("POWERPLATFORM_TOKEN")
    if env_tok:
        return env_tok
    if getattr(args, "managed_identity", False):
        return token_via_managed_identity(getattr(args, "mi_client_id", None))
    client_secret = getattr(args, "client_secret", None) or os.environ.get(
        "PP_SP_CLIENT_SECRET")
    if client_secret and args.client_id:
        return token_via_client_credentials(args.tenant, args.client_id,
                                            client_secret)
    if args.client_id:
        return token_via_device_code(args.tenant, args.client_id)
    tok = token_via_az()
    if tok:
        print("Note: using an Azure CLI token. If the API returns 403 "
              "InsufficientDelegatedPermissions, re-run with --client-id "
              "pointing at an app registration that has the Power Platform API "
              "'CopilotStudio.MakerOperations.ReadWrite' delegated permission.")
        return tok
    print("Error: no token available. Provide --token, --client-id, or sign in "
          "with the Azure CLI.")
    sys.exit(1)


# --------------------------------------------------------------------------- #
# Power Platform API calls
# --------------------------------------------------------------------------- #
def api_base(args) -> str:
    return (f"{PPAPI_BASE}/copilotstudio/environments/{args.env_id}"
            f"/bots/{args.bot_id}/api/makerevaluation")


def ppapi(method: str, url: str, token: str, body: dict | None = None) -> dict:
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Authorization", f"Bearer {token}")
    req.add_header("Accept", "application/json")
    if data is not None:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, context=_ssl_context(), timeout=120) as r:
            raw = r.read().decode("utf-8")
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "replace")
        print(f"API call failed (HTTP {e.code}) {method} {url}")
        print(detail[:2000])
        if e.code == 403 and "InsufficientDelegatedPermissions" in detail:
            print("\n-> The token's app is missing the Power Platform API "
                  "'CopilotStudio.MakerOperations.ReadWrite' delegated "
                  "permission (admin consent required). Use --client-id with a "
                  "properly-scoped app registration.")
        sys.exit(1)
    except urllib.error.URLError as e:
        print(f"Error: could not reach the Power Platform API: {e.reason}\n"
              "Behind an SSL-inspecting proxy? Set REQUESTS_CA_BUNDLE.")
        sys.exit(1)


def list_testsets(args, token: str) -> list[dict]:
    url = f"{api_base(args)}/testsets?api-version={args.api_version}"
    return ppapi("GET", url, token).get("value", [])


def resolve_testset_id(args, token: str) -> str:
    if args.test_set_id:
        return args.test_set_id
    sets = list_testsets(args, token)
    matches = [s for s in sets
               if s.get("displayName") == args.test_set_name]
    if not matches:
        names = ", ".join(repr(s.get("displayName")) for s in sets) or "(none)"
        print(f"No test set named {args.test_set_name!r}. Available: {names}")
        sys.exit(1)
    return matches[0]["id"]


def start_run(args, token: str, test_set_id: str, run_name: str | None = None,
              run_on_published: bool | None = None) -> dict:
    url = (f"{api_base(args)}/testsets/{test_set_id}/run"
           f"?api-version={args.api_version}")
    body: dict = {}
    if getattr(args, "mcs_connection_id", None):
        body["mcsConnectionId"] = args.mcs_connection_id
    if run_name:
        body["evaluationRunName"] = run_name
    if run_on_published is not None:
        body["runOnPublishedBot"] = run_on_published
    return ppapi("POST", url, token, body=body)


def get_run(args, token: str, run_id: str) -> dict:
    url = (f"{api_base(args)}/testruns/{run_id}"
           f"?api-version={args.api_version}")
    return ppapi("GET", url, token)


def poll_run(args, token: str, run_id: str) -> dict:
    print(f"Polling run {run_id} ...", flush=True)
    while True:
        run = get_run(args, token, run_id)
        state = str(run.get("state", "")).lower()
        processed = run.get("testCasesProcessed")
        total = run.get("totalTestCases")
        prog = f" ({processed}/{total})" if total is not None else ""
        print(f"  state={run.get('state')}{prog}", flush=True)
        if state not in RUNNING_STATES:
            return run
        time.sleep(args.poll_interval)


# --------------------------------------------------------------------------- #
# Results handling
# --------------------------------------------------------------------------- #
def flatten_results(run: dict) -> list[dict]:
    rows = []
    for tc in run.get("testCasesResults", []) or []:
        tc_id = tc.get("testCaseId")
        tc_state = tc.get("state")
        metrics = tc.get("metricsResults") or []
        if not metrics:
            rows.append({"testCaseId": tc_id, "testCaseState": tc_state,
                         "metric": "", "status": "", "abstention": "",
                         "relevance": "", "completeness": "",
                         "errorReason": tc.get("errorReason", ""),
                         "aiResultReason": ""})
            continue
        for m in metrics:
            result = m.get("result") or {}
            data = result.get("data") or {}
            rows.append({
                "testCaseId": tc_id,
                "testCaseState": tc_state,
                "metric": m.get("type", ""),
                "status": result.get("status", m.get("status", "")),
                "abstention": data.get("abstention", ""),
                "relevance": data.get("relevance", ""),
                "completeness": data.get("completeness", ""),
                "errorReason": result.get("errorReason", m.get("errorReason", "")),
                "aiResultReason": result.get("aiResultReason",
                                             m.get("aiResultReason", "")),
            })
    return rows


def write_results(rows: list[dict], path: str) -> None:
    fields = ["testCaseId", "testCaseState", "metric", "status", "abstention",
              "relevance", "completeness", "errorReason", "aiResultReason"]
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields, quoting=csv.QUOTE_ALL)
        w.writeheader()
        for r in rows:
            w.writerow(r)


def summarize(run: dict, rows: list[dict]) -> None:
    print("\n" + "=" * 60)
    print("EVALUATION SUMMARY")
    print("=" * 60)
    print(f"  Run id:      {run.get('id')}")
    print(f"  State:       {run.get('state')}")
    print(f"  Test set:    {run.get('testSetId')}")
    print(f"  Total cases: {run.get('totalTestCases')}")
    statuses: dict[str, int] = {}
    for r in rows:
        s = str(r.get("status") or r.get("testCaseState") or "unknown").lower()
        statuses[s] = statuses.get(s, 0) + 1
    if statuses:
        print("  Result breakdown (metric status):")
        for s, n in sorted(statuses.items(), key=lambda kv: -kv[1]):
            print(f"    - {s}: {n}")
    print("=" * 60)


# --------------------------------------------------------------------------- #
# Commands
# --------------------------------------------------------------------------- #
def select_test_sets(all_sets: list[dict], names: list[str],
                     patterns: list[str]) -> list[dict]:
    """Match test sets by exact displayName (case-insensitive) and/or glob."""
    names_lc = {n.strip().lower() for n in names if n and n.strip()}
    pats = [p.strip() for p in patterns if p and p.strip()]
    selected, seen = [], set()
    for ts in all_sets:
        disp_lc = str(ts.get("displayName", "")).lower()
        if disp_lc in names_lc or any(fnmatch.fnmatch(disp_lc, p.lower())
                                      for p in pats):
            if ts.get("id") not in seen:
                selected.append(ts)
                seen.add(ts.get("id"))
    return selected


def score_run(run: dict) -> tuple[int, int]:
    """Return (passed_cases, total_cases). Per the API schema a TestCaseResult has
    no Pass/Fail status (only Completed/Error/...); pass/fail lives on each
    metric at metric.result.status (MetricStatus: Pass/Fail/Error/Unknown). A case
    passes if it has metrics and all of them are Pass."""
    cases = run.get("testCasesResults") or []
    passed = 0
    for case in cases:
        cstate = str(case.get("state") or case.get("status") or "").lower()
        if cstate in ("error", "cancelled", "canceled", "fail", "failed"):
            continue
        metrics = case.get("metricsResults") or []
        statuses = []
        for m in metrics:
            st = (m.get("result") or {}).get("status")
            if st is None:  # tolerate a flattened shape
                st = m.get("status")
            statuses.append(str(st or "").lower())
        if statuses and all(s in ("pass", "passed") for s in statuses):
            passed += 1
    return passed, len(cases)


def load_config(path: str | None) -> dict:
    if not path:
        return {}
    if not os.path.isfile(path):
        print(f"Config file not found: {path}")
        sys.exit(1)
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def cmd_gate(args) -> None:
    """CI gate: select test sets by name/pattern, run each, and exit non-zero if
    the overall pass rate is below the threshold (or any run fails)."""
    cfg = load_config(args.config)
    names = list(args.test_set or []) + list(cfg.get("testSetNames", []))
    patterns = list(args.pattern or []) + list(cfg.get("testSetNamePatterns", []))
    if not names and not patterns:
        patterns = ["deploy-test-*"]  # default matching the naming convention
    threshold = (args.pass_threshold if args.pass_threshold is not None
                 else float(cfg.get("passThreshold", 1.0)))
    run_on_published = (args.run_on_published if args.run_on_published is not None
                        else bool(cfg.get("runOnPublishedBot", True)))

    token = get_token(args)
    all_sets = list_testsets(args, token)
    active = [s for s in all_sets
              if str(s.get("state", "Active")).lower() == "active"]
    selected = select_test_sets(active, names, patterns)
    print(f"Selecting by names={names or '[]'} patterns={patterns}; "
          f"{len(all_sets)} test set(s) on agent, {len(selected)} matched.")
    if not selected:
        avail = ", ".join(sorted(str(s.get("displayName")) for s in all_sets))
        print(f"No active test set matched. Available: {avail or '(none)'}")
        sys.exit(2)
    for ts in selected:
        print(f"  - {ts.get('displayName')} "
              f"({ts.get('totalTestCases', '?')} cases) id={ts.get('id')}")
    if args.dry_run:
        print("Dry run: not executing.")
        return

    results, total_passed, total_cases, any_failed = [], 0, 0, False
    stamp = time.strftime("%Y%m%d-%H%M%S")
    for ts in selected:
        name = ts.get("displayName")
        print(f"\nRunning evaluation: {name}")
        started = start_run(args, token, ts.get("id"),
                            run_name=f"{args.run_name_prefix}-{name}-{stamp}",
                            run_on_published=run_on_published)
        run_id = started.get("runId") or started.get("id")
        if not run_id:
            print("Did not receive a run id:")
            print(json.dumps(started, indent=2))
            sys.exit(1)
        run = poll_run(args, token, run_id)
        state = str(run.get("state", "")).lower()
        passed, cases = score_run(run)
        rate = (passed / cases) if cases else 0.0
        any_failed = any_failed or state in ("failed", "abandoned", "cancelled")
        total_passed += passed
        total_cases += cases
        print(f"  -> state={state} passed={passed}/{cases} ({rate:.0%})")
        results.append({"testSet": name, "testSetId": ts.get("id"),
                        "runId": run_id, "state": state, "passedCases": passed,
                        "totalCases": cases, "passRate": round(rate, 4)})

    overall = (total_passed / total_cases) if total_cases else 0.0
    gate_ok = (not any_failed) and overall >= threshold
    summary = {
        "generatedAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "environmentId": args.env_id, "botId": args.bot_id,
        "runOnPublishedBot": run_on_published, "passThreshold": threshold,
        "overallPassRate": round(overall, 4), "totalPassed": total_passed,
        "totalCases": total_cases, "anyRunFailed": any_failed,
        "gatePassed": gate_ok, "runs": results,
    }
    print("\n" + "=" * 60)
    print(f"Overall: {total_passed}/{total_cases} passed ({overall:.0%}); "
          f"threshold {threshold:.0%}; gate "
          f"{'PASSED' if gate_ok else 'FAILED'}.")
    if args.output:
        with open(args.output, "w", encoding="utf-8") as fh:
            json.dump(summary, fh, indent=2)
        print(f"Wrote summary -> {args.output}")
    sys.exit(0 if gate_ok else 1)


def cmd_list(args) -> None:
    token = get_token(args)
    sets = list_testsets(args, token)
    if not sets:
        print("No test sets found on this agent.")
        return
    print(f"{'displayName':40}  {'state':10}  {'cases':6}  id")
    for s in sets:
        print(f"{str(s.get('displayName'))[:40]:40}  "
              f"{str(s.get('state')):10}  "
              f"{str(s.get('totalTestCases')):6}  {s.get('id')}")


def cmd_run(args) -> None:
    token = get_token(args)
    test_set_id = resolve_testset_id(args, token)
    print(f"Starting evaluation for test set {test_set_id} ...")
    started = start_run(args, token, test_set_id)
    run_id = started.get("runId") or started.get("id")
    if not run_id:
        print("Did not receive a run id from the start call:")
        print(json.dumps(started, indent=2))
        sys.exit(1)
    print(f"Run id: {run_id}")
    run = poll_run(args, token, run_id)
    rows = flatten_results(run)
    if args.output:
        write_results(rows, args.output)
        print(f"Wrote {len(rows)} result rows -> {args.output}")
    summarize(run, rows)


def cmd_results(args) -> None:
    token = get_token(args)
    run = get_run(args, token, args.run_id)
    rows = flatten_results(run)
    if args.output:
        write_results(rows, args.output)
        print(f"Wrote {len(rows)} result rows -> {args.output}")
    summarize(run, rows)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="command", required=True)

    def common(sp):
        sp.add_argument("--env-id", required=True, help="Environment ID (GUID).")
        sp.add_argument("--bot-id", required=True, help="Agent/Bot ID (GUID).")
        sp.add_argument("--client-id", help="Entra app registration ID. Used for "
                        "device-code auth, or with --client-secret for "
                        "service-principal (client-credentials) auth.")
        sp.add_argument("--client-secret", help="Service-principal client secret "
                        "(or env PP_SP_CLIENT_SECRET) for client-credentials auth.")
        sp.add_argument("--managed-identity", action="store_true",
                        help="Authenticate via Azure managed identity (IMDS). "
                        "Only works on Azure compute / self-hosted runners.")
        sp.add_argument("--mi-client-id", help="User-assigned managed identity "
                        "client id (omit for system-assigned).")
        sp.add_argument("--tenant", default="organizations",
                        help="Tenant ID for device-code / client-credentials auth.")
        sp.add_argument("--token", help="Pre-acquired bearer token (or env "
                        "POWERPLATFORM_TOKEN). Use with workflow OIDC federation.")
        sp.add_argument("--api-version", default=DEFAULT_API_VERSION)

    p_list = sub.add_parser("list", help="List test sets on the agent.")
    common(p_list)
    p_list.set_defaults(func=cmd_list)

    p_run = sub.add_parser("run", help="Run a test set and poll for results.")
    common(p_run)
    g = p_run.add_mutually_exclusive_group(required=True)
    g.add_argument("--test-set-name", help="Test set display name to run.")
    g.add_argument("--test-set-id", help="Test set id to run.")
    p_run.add_argument("--mcs-connection-id", help="Copilot Studio connection "
                       "(user profile) id for an authenticated run.")
    p_run.add_argument("--output", help="Write per-test-case results CSV here.")
    p_run.add_argument("--poll-interval", type=int, default=15,
                       help="Seconds between status polls (default 15).")
    p_run.set_defaults(func=cmd_run)

    p_res = sub.add_parser("results", help="Fetch results for a prior run id.")
    common(p_res)
    p_res.add_argument("--run-id", required=True)
    p_res.add_argument("--output", help="Write per-test-case results CSV here.")
    p_res.set_defaults(func=cmd_results)

    p_gate = sub.add_parser("gate", help="CI gate: run test sets matched by "
                            "name/pattern and fail below a pass-rate threshold.")
    common(p_gate)
    p_gate.add_argument("--test-set", action="append", default=[],
                        help="Exact test set display name (repeatable).")
    p_gate.add_argument("--pattern", action="append", default=[],
                        help="Glob for test set names, e.g. 'deploy-test-*' "
                        "(repeatable). Default 'deploy-test-*' if none given.")
    p_gate.add_argument("--config", help="JSON config with testSetNames / "
                        "testSetNamePatterns / passThreshold / runOnPublishedBot.")
    p_gate.add_argument("--pass-threshold", type=float,
                        help="Minimum overall pass rate 0..1 (default 1.0).")
    p_gate.add_argument("--run-on-published", dest="run_on_published",
                        action="store_true", help="Evaluate published agent.")
    p_gate.add_argument("--run-on-draft", dest="run_on_published",
                        action="store_false", help="Evaluate draft agent.")
    p_gate.set_defaults(run_on_published=None)
    p_gate.add_argument("--run-name-prefix", default="ci",
                        help="Prefix for the generated evaluationRunName.")
    p_gate.add_argument("--mcs-connection-id", help="Copilot Studio connection "
                        "id for an authenticated run.")
    p_gate.add_argument("--poll-interval", type=int, default=15,
                        help="Seconds between status polls (default 15).")
    p_gate.add_argument("--output", help="Write a JSON results summary here.")
    p_gate.add_argument("--dry-run", action="store_true",
                        help="List matched test sets and exit without running.")
    p_gate.set_defaults(func=cmd_gate)
    return p


def main() -> None:
    args = build_parser().parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
