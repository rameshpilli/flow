#!/usr/bin/env bash
set -euo pipefail

if ! command -v bd >/dev/null 2>&1; then
  echo "bd CLI not found. Install/configure bd before seeding tasks."
  exit 1
fi

echo "Seeding Coder Pad MVP beads..."

bd --sandbox create "Build calculator core" \
  --type task \
  --priority 1 \
  --description "Create calculator package with add/subtract/multiply/divide and tests." \
  --labels "coder-pad,calculator,qa,docs" \
  --owner "Ramesh Pilli"

bd --sandbox create "Add calculator CLI" \
  --type task \
  --priority 2 \
  --description "Add CLI entrypoint for calculator operations and usage docs." \
  --labels "coder-pad,calculator,cli,docs" \
  --owner "Ramesh Pilli"

bd --sandbox create "Strengthen calculator QA" \
  --type task \
  --priority 2 \
  --description "Add additional edge-case tests and update runbook guidance." \
  --labels "coder-pad,qa,tests,runbook" \
  --owner "Ramesh Pilli"

bd --sandbox export

echo "Bead seed complete."
