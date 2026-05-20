#!/usr/bin/env bash
# Restore the flight DuckDB + corpus LanceDB index used by data-backed eval
# questions. CI cannot rebuild the multi-GB BTS dataset per run, so the data
# is fetched from a prebuilt tarball whose URL lives in the EVAL_DATA_URL repo
# variable (see docs/deploy.md for how to publish it).
#
# When EVAL_DATA_URL is unset the restore is skipped: flight/corpus eval
# questions then degrade gracefully (the agent reports the data as
# unavailable, per R3) while weather / NOTAM / refusal / security questions
# still run against live APIs.
set -euo pipefail

if [ -z "${EVAL_DATA_URL:-}" ]; then
  echo "::notice title=Eval data::EVAL_DATA_URL not set — skipping eval-data restore."
  echo "Flight- and corpus-backed questions will degrade gracefully."
  echo "Set the EVAL_DATA_URL repo variable to a prebuilt data tarball to enable them."
  exit 0
fi

mkdir -p data
echo "Downloading eval data tarball…"
curl --fail --silent --show-error --location "$EVAL_DATA_URL" -o /tmp/eval-data.tar.gz
echo "Extracting to ./data …"
tar -xzf /tmp/eval-data.tar.gz -C data
rm -f /tmp/eval-data.tar.gz
echo "Eval data restored:"
ls -la data
