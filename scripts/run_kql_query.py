"""
Application Insights KQL Runner
===============================
Runs a single named query from app_insights_queries.kql against an Application
Insights resource and writes the result as CSV. This replaces the manual "run
in the Azure portal and download CSV" step of the eval pipeline.

Two authentication modes:
  1. API key (recommended for limited/least-privilege access) — uses the App
     Insights REST API with an "API Access" Application ID + API key. No Azure
     RBAC/role assignment required. Pass --api-key or set APPINSIGHTS_API_KEY.
  2. Azure CLI / AAD — uses `az monitor app-insights query` with your signed-in
     identity (which must have Reader on the App Insights resource).

Prerequisites (API-key mode):
    - Generate an API key in the App Insights resource: API Access > Create API
      key > check "Read telemetry". Note the Application ID + the key.

Prerequisites (Azure CLI mode):
    - Azure CLI installed, with the application-insights extension:
        az extension add --name application-insights
    - Signed in to the tenant that owns the App Insights resource:
        az login --tenant <TENANT_ID>          (use the credentials with access)
      Verify with: az account show
    - Behind an SSL-inspecting corporate proxy, set REQUESTS_CA_BUNDLE to a PEM
      that includes the corporate root CA.

Usage:
    # API-key mode
    python run_kql_query.py --export-pair --app-id <APP_ID> --api-key <KEY> --output-dir .
    python run_kql_query.py --query 6 --app-id <APP_ID> --api-key <KEY> --output messages.csv

    # Azure CLI / AAD mode (omit --api-key)
    python run_kql_query.py --query 6  --app-id <APP_ID> --output messages.csv
    python run_kql_query.py --query 6b --app-id <APP_ID> --output toolcalls.csv

Arguments:
    --query        Query id as it appears in the .kql header (e.g. 1, 6, 6b).
    --app-id       App Insights "Application ID" GUID (API Access blade), or set
                   env APPINSIGHTS_APP_ID.
    --api-key      App Insights API key (or env APPINSIGHTS_API_KEY). If set,
                   uses the REST API instead of the Azure CLI.
    --output       Output CSV path.
    --kql-file     Path to the .kql file (default: app_insights_queries.kql next
                   to this script).
    --timespan     ISO-8601 duration (e.g. P14D). Optional; the queries already
                   filter with `ago(14d)`.
    --tenant       Optional tenant id (documentation only; set at az login time).
    --subscription Optional subscription id/name forwarded to az (AAD mode).

The .kql file bundles several queries separated by `// QUERY <id>:` headers.
This script extracts just the requested query's KQL body (dropping the comment
lines) and runs it via the chosen auth mode.
"""

import argparse
import csv
import json
import os
import re
import shutil
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

QUERY_HEADER_RE = re.compile(r"^//\s*QUERY\s+([0-9A-Za-z]+)\s*:", re.IGNORECASE)

# The two queries the eval pipeline consumes.
EXPORT_PAIR = [("6", "messages.csv"), ("6b", "toolcalls.csv")]

APPINSIGHTS_API_BASE = "https://api.applicationinsights.io/v1/apps"


def run_api_key_query(app_id: str, api_key: str, query: str,
                      timespan: str | None) -> dict:
    """Execute the KQL via the App Insights REST API using an API key.

    Returns the standard {"tables":[...]} payload. Honors REQUESTS_CA_BUNDLE /
    SSL_CERT_FILE for corporate proxy CA bundles.
    """
    body = {"query": query}
    if timespan:
        body["timespan"] = timespan
    data = json.dumps(body).encode("utf-8")
    url = f"{APPINSIGHTS_API_BASE}/{app_id}/query"
    req = urllib.request.Request(url, data=data, method="POST")
    req.add_header("X-Api-Key", api_key)
    req.add_header("Content-Type", "application/json")

    ctx = None
    ca = os.environ.get("REQUESTS_CA_BUNDLE") or os.environ.get("SSL_CERT_FILE")
    if ca and os.path.exists(ca):
        import ssl
        ctx = ssl.create_default_context(cafile=ca)

    try:
        with urllib.request.urlopen(req, context=ctx, timeout=120) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "replace")
        if e.code in (401, 403):
            print("Error: API key rejected or lacks 'Read telemetry' access. "
                  "Regenerate the key in App Insights > API Access and ensure "
                  "the Application ID matches.")
        print(f"REST query failed (HTTP {e.code}):\n{detail[:2000]}")
        sys.exit(1)
    except urllib.error.URLError as e:
        print(f"Error: could not reach App Insights API: {e.reason}\n"
              "Behind an SSL-inspecting proxy? Set REQUESTS_CA_BUNDLE to a PEM "
              "that includes the corporate root CA.")
        sys.exit(1)


def find_az() -> str:
    """Locate the az CLI executable (PATH may not be refreshed after install)."""
    for cand in ("az", "az.cmd"):
        p = shutil.which(cand)
        if p:
            return p
    for p in (
        r"C:\Program Files\Microsoft SDKs\Azure\CLI2\wbin\az.cmd",
        r"C:\Program Files (x86)\Microsoft SDKs\Azure\CLI2\wbin\az.cmd",
    ):
        if os.path.exists(p):
            return p
    print("Error: Azure CLI ('az') not found on PATH. Install it and retry.")
    sys.exit(2)


def parse_queries(kql_path: Path) -> dict:
    """Split the .kql file into {query_id: kql_body} by `// QUERY <id>:` headers.

    The KQL body is every non-comment, non-blank line between one query header
    block and the next (or EOF).
    """
    if not kql_path.exists():
        print(f"Error: KQL file not found: {kql_path}")
        sys.exit(2)

    lines = kql_path.read_text(encoding="utf-8").splitlines()
    # Locate header lines and their query ids.
    headers = [(i, m.group(1).lower())
               for i, ln in enumerate(lines)
               for m in [QUERY_HEADER_RE.match(ln.strip())] if m]
    if not headers:
        print(f"Error: no `// QUERY <id>:` headers found in {kql_path}")
        sys.exit(2)

    queries = {}
    for idx, (start, qid) in enumerate(headers):
        end = headers[idx + 1][0] if idx + 1 < len(headers) else len(lines)
        body_lines = []
        for ln in lines[start:end]:
            stripped = ln.strip()
            if not stripped or stripped.startswith("//"):
                continue
            body_lines.append(ln)
        body = "\n".join(body_lines).strip()
        if body:
            queries[qid] = body
    return queries


def run_az_query(az: str, app_id: str, query: str, timespan: str | None,
                 tenant: str | None, subscription: str | None) -> dict:
    """Execute the KQL via `az monitor app-insights query` and return parsed JSON."""
    cmd = [az, "monitor", "app-insights", "query",
           "--app", app_id, "--analytics-query", query, "-o", "json"]
    if timespan:
        cmd += ["--offset", timespan]
    if subscription:
        cmd += ["--subscription", subscription]
    # Note: tenant is selected at sign-in time (az login --tenant ...), not per
    # command; --tenant is accepted by this script only to document that intent.

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        err = result.stderr.strip() or result.stdout.strip()
        if "az login" in err.lower() or "not logged in" in err.lower() or \
           "please run 'az login'" in err.lower():
            print("Error: not signed in. Run `az login --tenant <TENANT_ID>` "
                  "with the appropriate credentials, then retry.")
        print(f"az query failed (exit {result.returncode}):\n{err}")
        sys.exit(1)
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError:
        print("Error: could not parse az output as JSON:\n" + result.stdout[:2000])
        sys.exit(1)


def result_to_rows(payload: dict):
    """Flatten the az query JSON into (headers, rows).

    az returns either {"tables":[{"columns":[...],"rows":[...]}]} or a already
    flattened list of dict records depending on version. Handle both. Dynamic
    (array/object) cell values are serialized back to compact JSON strings so
    they match the portal CSV export consumed by convert_appinsights_to_eval.py.
    """
    def encode(v):
        if isinstance(v, (dict, list)):
            return json.dumps(v, separators=(",", ":"), ensure_ascii=False)
        if v is None:
            return ""
        return v

    if isinstance(payload, dict) and payload.get("tables"):
        table = payload["tables"][0]
        headers = [c["name"] for c in table["columns"]]
        rows = [[encode(v) for v in row] for row in table["rows"]]
        return headers, rows

    if isinstance(payload, list):
        if not payload:
            return [], []
        headers = list(payload[0].keys())
        rows = [[encode(rec.get(h)) for h in headers] for rec in payload]
        return headers, rows

    print("Error: unexpected az result shape.")
    sys.exit(1)


def write_csv(headers, rows, out_path: Path):
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(headers)
        w.writerows(rows)


def run_one(queries, qid, app_id, out_path, timespan, *, az=None, api_key=None,
            tenant=None, subscription=None):
    qid = qid.lower()
    if qid not in queries:
        print(f"Error: query '{qid}' not found. Available: {', '.join(sorted(queries))}")
        sys.exit(2)
    if api_key:
        payload = run_api_key_query(app_id, api_key, queries[qid], timespan)
    else:
        payload = run_az_query(az, app_id, queries[qid], timespan, tenant, subscription)
    headers, rows = result_to_rows(payload)
    write_csv(headers, rows, out_path)
    print(f"Query {qid}: wrote {len(rows)} rows -> {out_path}")


def main():
    ap = argparse.ArgumentParser(description="Run a named KQL query from the "
                                             "eval .kql file (API key or Azure CLI).")
    ap.add_argument("--query", help="Query id (e.g. 1, 6, 6b)")
    ap.add_argument("--app-id", default=os.environ.get("APPINSIGHTS_APP_ID"),
                    help="App Insights Application ID GUID (or env APPINSIGHTS_APP_ID)")
    ap.add_argument("--api-key", default=os.environ.get("APPINSIGHTS_API_KEY"),
                    help="App Insights API key (or env APPINSIGHTS_API_KEY). "
                         "If set, uses the REST API instead of the Azure CLI.")
    ap.add_argument("--output", help="Output CSV path")
    ap.add_argument("--export-pair", action="store_true",
                    help="Run both export queries (6 -> messages.csv, 6b -> toolcalls.csv)")
    ap.add_argument("--output-dir", default=".",
                    help="Directory for --export-pair outputs (default: .)")
    ap.add_argument("--kql-file", default=None, help="Path to the .kql file")
    ap.add_argument("--timespan", default=None,
                    help="ISO-8601 duration (e.g. P14D). Optional.")
    ap.add_argument("--tenant", default=None, help="Tenant id (documentation only; set at az login)")
    ap.add_argument("--subscription", default=None, help="Subscription id/name (forwarded to az)")
    args = ap.parse_args()

    if not args.app_id:
        print("Error: provide --app-id or set APPINSIGHTS_APP_ID.")
        sys.exit(2)

    kql_path = Path(args.kql_file) if args.kql_file else \
        Path(__file__).with_name("app_insights_queries.kql")
    queries = parse_queries(kql_path)
    az = None if args.api_key else find_az()

    if args.export_pair:
        out_dir = Path(args.output_dir)
        for qid, fname in EXPORT_PAIR:
            run_one(queries, qid, args.app_id, out_dir / fname, args.timespan,
                    az=az, api_key=args.api_key, tenant=args.tenant,
                    subscription=args.subscription)
        print("Done. Next: python convert_appinsights_to_eval.py "
              f"--messages {out_dir / 'messages.csv'} --tools {out_dir / 'toolcalls.csv'} "
              "--output eval_from_real.jsonl")
        return

    if not args.query or not args.output:
        print("Error: provide --query and --output (or use --export-pair).")
        sys.exit(2)

    run_one(queries, args.query, args.app_id, Path(args.output), args.timespan,
            az=az, api_key=args.api_key, tenant=args.tenant,
            subscription=args.subscription)


if __name__ == "__main__":
    main()
