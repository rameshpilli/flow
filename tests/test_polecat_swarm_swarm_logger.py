from __future__ import annotations

import json
import time

from examples.polecat_swarm.swarm_logger import SwarmLogger
from examples.polecat_swarm.types import TraceContext


def test_swarm_logger_emits_json_with_trace_fields(caplog) -> None:
    trace = TraceContext(trace_id="convoy-1", span_id="bd-1", expert_role="EES", repo_name="demo")
    log = SwarmLogger(trace)

    with caplog.at_level("INFO"):
        log.info("event_test", foo="bar")

    payload = json.loads(caplog.records[-1].message)
    assert payload["event"] == "event_test"
    assert payload["trace_id"] == "convoy-1"
    assert payload["span_id"] == "bd-1"
    assert payload["role"] == "EES"
    assert payload["foo"] == "bar"


def test_child_trace_sets_sub_span_and_elapsed_resets() -> None:
    parent = TraceContext(trace_id="convoy-1", span_id="bd-2", expert_role="EES", repo_name="demo")
    time.sleep(0.01)
    child = parent.child("ArchitectureAdvisor")

    assert child.sub_span_id == "ArchitectureAdvisor"
    assert child.trace_id == parent.trace_id
    assert child.span_id == parent.span_id
    assert child.elapsed() < parent.elapsed()
