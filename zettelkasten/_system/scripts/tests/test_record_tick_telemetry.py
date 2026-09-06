"""Tests for scripts/scheduler/record_tick_telemetry.py — the tick odometer.

Every test builds a hermetic fake `projects/` tree (never this machine's real
`~/.claude/projects`) shaped exactly like the transcripts Claude Code writes,
and exercises the production functions the tick calls.

Two properties get the most coverage, because both are load-bearing and
neither is visible in the output when it silently breaks:

  * a streamed response is appended once per chunk under one `message.id`, so
    counting rows instead of ids multiplies a single response by its chunk
    count;
  * the script must exit 0 on every failure path, because a scheduler prompt
    trips failure-handling on any non-zero exit from a helper — instrumentation
    that can abort a tick is worse than none.
"""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

_REPO = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(_REPO / "scripts" / "scheduler"))

import record_tick_telemetry as rt  # noqa: E402

SESSION = "11111111-2222-3333-4444-555555555555"


def usage(**kw) -> dict:
    """One `usage` block in the runtime's real shape."""
    block = {
        "input_tokens": kw.get("input", 0),
        "output_tokens": kw.get("output", 0),
        "cache_creation_input_tokens": kw.get("cw", 0),
        "cache_read_input_tokens": kw.get("cr", 0),
        "output_tokens_details": {"thinking_tokens": kw.get("thinking", 0)},
        "cache_creation": {
            "ephemeral_1h_input_tokens": kw.get("cw_1h", kw.get("cw", 0)),
            "ephemeral_5m_input_tokens": kw.get("cw_5m", 0),
        },
        "server_tool_use": {
            "web_search_requests": kw.get("web_search", 0),
            "web_fetch_requests": 0,
        },
        "service_tier": "standard",
    }
    return block


def assistant(msg_id: str, model: str = "claude-opus-5", **kw) -> str:
    return json.dumps(
        {
            "type": "assistant",
            "message": {"id": msg_id, "model": model, "usage": usage(**kw)},
        }
    )


def agent_call(tool_id: str) -> str:
    """A dispatch as the runtime actually writes it — with usage attached.

    Verified against a real transcript: of 246 assistant messages carrying a
    `tool_use` block, every one also carried `usage`. A fixture without it
    would exercise a shape the runtime does not produce.
    """
    return json.dumps(
        {
            "type": "assistant",
            "message": {
                "id": "m-" + tool_id,
                "model": "claude-opus-5",
                "usage": usage(output=1),
                "content": [
                    {"type": "tool_use", "id": tool_id, "name": "Agent", "input": {}}
                ],
            },
        }
    )


def _write_lf(path, text: str) -> None:
    with open(path, "w", encoding="utf-8", newline="") as handle:
        handle.write(text)


class Tree:
    """A throwaway `projects/` root holding one session."""

    def __init__(self, tmp: Path, slug: str = "-home-user-minder-memory"):
        self.root = tmp / "projects"
        self.slug_dir = self.root / slug
        self.slug_dir.mkdir(parents=True)
        self.main = self.slug_dir / (SESSION + ".jsonl")

    def write_main(self, lines) -> None:
        _write_lf(self.main, "\n".join(lines) + "\n")

    def add_subagent(self, name: str, lines, meta: dict, first_user: str | None = None):
        sub_dir = self.slug_dir / SESSION / "subagents"
        sub_dir.mkdir(parents=True, exist_ok=True)
        body = list(lines)
        if first_user is not None:
            body.insert(
                0,
                json.dumps({"type": "user", "message": {"content": first_user}}),
            )
        _write_lf(sub_dir / (name + ".jsonl"), "\n".join(body) + "\n")
        _write_lf(sub_dir / (name + ".meta.json"), json.dumps(meta))


class ExtractUsageTest(unittest.TestCase):
    def test_every_countable_field_is_kept(self):
        got = rt.extract_usage(
            usage(input=7, output=100, thinking=40, cw=500, cw_1h=300, cw_5m=200, cr=9000, web_search=2)
        )
        self.assertEqual(got["input"], 7)
        self.assertEqual(got["output"], 100)
        self.assertEqual(got["thinking"], 40)
        self.assertEqual(got["cache_write_total"], 500)
        self.assertEqual(got["cache_write_1h"], 300)
        self.assertEqual(got["cache_write_5m"], 200)
        self.assertEqual(got["cache_read"], 9000)
        self.assertEqual(got["web_search_requests"], 2)

    def test_absent_subblocks_do_not_raise(self):
        got = rt.extract_usage({"input_tokens": 3, "output_tokens": 4})
        self.assertEqual(got["input"], 3)
        self.assertEqual(got["thinking"], 0)
        self.assertEqual(got["cache_write_1h"], 0)

    def test_null_valued_fields_count_as_zero(self):
        # The runtime writes explicit nulls rather than omitting keys in some
        # responses; `or 0` must absorb them without a TypeError downstream.
        got = rt.extract_usage(
            {"input_tokens": None, "output_tokens": 5, "cache_read_input_tokens": None}
        )
        self.assertEqual(got["input"], 0)
        self.assertEqual(got["cache_read"], 0)
        self.assertEqual(got["output"], 5)


class CollectTest(unittest.TestCase):
    def test_streamed_chunks_of_one_response_count_once(self):
        with tempfile.TemporaryDirectory() as tmp:
            tree = Tree(Path(tmp))
            # Same id three times with a growing usage block — the shape a
            # streamed response actually lands in.
            tree.write_main(
                [
                    assistant("msg-a", output=10, cr=1000),
                    assistant("msg-a", output=50, cr=1000),
                    assistant("msg-a", output=90, cr=1000),
                    assistant("msg-b", output=5, cr=2000),
                ]
            )
            got = rt.collect(SESSION, tree.root)
            self.assertEqual(got["api_msgs"], 2)
            self.assertEqual(got["totals"]["output"], 95)  # last-wins: 90 + 5
            self.assertEqual(got["totals"]["cache_read"], 3000)

    def test_subagent_usage_is_counted_not_dropped(self):
        with tempfile.TemporaryDirectory() as tmp:
            tree = Tree(Path(tmp))
            tree.write_main([agent_call("toolu_1"), assistant("m1", output=100)])
            tree.add_subagent(
                "agent-aaa",
                [assistant("s1", output=7000, cr=500000)],
                {"agentType": "general-purpose", "description": "whatever"},
            )
            got = rt.collect(SESSION, tree.root)
            # 100 main + 7000 sub + 1 carried by the dispatch message itself
            self.assertEqual(got["totals"]["output"], 7101)
            labels = {b["agent"] for b in got["by_agent"]}
            self.assertEqual(labels, {"main", "agent:general-purpose"})

    def test_role_id_comes_from_the_assignment_path_not_the_description(self):
        with tempfile.TemporaryDirectory() as tmp:
            tree = Tree(Path(tmp))
            tree.write_main([agent_call("toolu_1"), assistant("m1", output=1)])
            tree.add_subagent(
                "agent-bbb",
                [assistant("s1", output=42)],
                # Description is free prose the dispatching model wrote — it
                # names a different role on purpose here.
                {"agentType": "minder-mem-role", "description": "Second run of shturman"},
                first_user="Your complete assignment is in this file:\n\n  /tmp/minder-mem-roles-abc/prompt-minder-pm.md\n\nRead it in full.",
            )
            got = rt.collect(SESSION, tree.root)
            labels = {b["agent"] for b in got["by_agent"]}
            self.assertIn("role:minder-pm", labels)
            self.assertNotIn("role:shturman", labels)

    def test_role_without_a_recoverable_id_is_named_not_guessed(self):
        with tempfile.TemporaryDirectory() as tmp:
            tree = Tree(Path(tmp))
            tree.write_main([assistant("m1", output=1)])
            tree.add_subagent(
                "agent-ccc",
                [assistant("s1", output=9)],
                {"agentType": "minder-mem-role", "description": "Run something"},
                first_user="No assignment path in this text at all.",
            )
            got = rt.collect(SESSION, tree.root)
            labels = {b["agent"] for b in got["by_agent"]}
            self.assertIn("role:unattributed", labels)

    def test_per_agent_totals_sum_to_the_grand_total(self):
        with tempfile.TemporaryDirectory() as tmp:
            tree = Tree(Path(tmp))
            tree.write_main([assistant("m1", output=100, cw=10, cr=1)])
            tree.add_subagent(
                "agent-a",
                [assistant("s1", output=200, cw=20, cr=2)],
                {"agentType": "Explore"},
            )
            tree.add_subagent(
                "agent-b",
                [assistant("s2", output=300, cw=30, cr=3)],
                {"agentType": "Explore"},
            )
            got = rt.collect(SESSION, tree.root)
            for field in ("output", "cache_write_total", "cache_read"):
                self.assertEqual(
                    sum(b[field] for b in got["by_agent"]),
                    got["totals"][field],
                    field,
                )
            # Same agentType collapses to one bucket — a lens tick spawns
            # hundreds and a line per file would be unreadable.
            explore = [b for b in got["by_agent"] if b["agent"] == "agent:Explore"]
            self.assertEqual(len(explore), 1)
            self.assertEqual(explore[0]["output"], 500)

    def test_models_are_counted_per_message(self):
        with tempfile.TemporaryDirectory() as tmp:
            tree = Tree(Path(tmp))
            tree.write_main(
                [
                    assistant("m1", model="claude-opus-5", output=1),
                    assistant("m2", model="claude-sonnet-5", output=1),
                    assistant("m3", model="claude-sonnet-5", output=1),
                ]
            )
            got = rt.collect(SESSION, tree.root)
            self.assertEqual(got["models"], {"claude-opus-5": 1, "claude-sonnet-5": 2})

    def test_each_agent_carries_its_own_model_tally(self):
        # A roles tick can put each role on a different model. A tick-level
        # tally answers "how many sonnet messages" and never "which role was
        # on sonnet" — the question a cost or quality comparison asks.
        with tempfile.TemporaryDirectory() as tmp:
            tree = Tree(Path(tmp))
            tree.write_main([assistant("m1", model="claude-opus-5", output=1)])
            tree.add_subagent(
                "agent-a",
                [assistant("s1", model="claude-sonnet-5", output=1),
                 assistant("s2", model="claude-sonnet-5", output=1)],
                {"agentType": "minder-mem-role"},
                first_user="assignment: /tmp/x/prompt-shturman.md",
            )
            got = rt.collect(SESSION, tree.root)
            per = {b["agent"]: b["models"] for b in got["by_agent"]}
            self.assertEqual(per["main"], {"claude-opus-5": 1})
            self.assertEqual(per["role:shturman"], {"claude-sonnet-5": 2})
            # the tick-level tally still sums to the same messages
            self.assertEqual(got["models"], {"claude-opus-5": 1, "claude-sonnet-5": 2})

    def test_truncated_final_line_is_skipped_and_the_rest_survives(self):
        with tempfile.TemporaryDirectory() as tmp:
            tree = Tree(Path(tmp))
            _write_lf(tree.main, assistant("m1", output=11) + "\n" + '{"type":"assistant","mess')
            got = rt.collect(SESSION, tree.root)
            self.assertEqual(got["status"], "measured")
            self.assertEqual(got["totals"]["output"], 11)

    def test_missing_transcript_reports_unmeasured(self):
        with tempfile.TemporaryDirectory() as tmp:
            tree = Tree(Path(tmp))
            got = rt.collect("no-such-session", tree.root)
            self.assertEqual(got["status"], "unmeasured")
            self.assertIn("no transcript", got["note"])


class ExplanatoryFieldsTest(unittest.TestCase):
    """The fields that turn a number into an explanation.

    All of them live only in the transcript, which a cloud tick destroys
    minutes after it finishes — so a field not taken here is not "available
    from the source later", it is gone.
    """

    def test_cache_miss_reason_and_its_cost_are_kept(self):
        with tempfile.TemporaryDirectory() as tmp:
            tree = Tree(Path(tmp))
            a = json.loads(assistant("m1", output=1))
            a["message"]["diagnostics"] = {
                "cache_miss_reason": {
                    "type": "system_changed",
                    "cache_missed_input_tokens": 427299,
                }
            }
            b = json.loads(assistant("m2", output=1))
            b["message"]["diagnostics"] = {
                "cache_miss_reason": {"type": "previous_message_not_found"}
            }
            tree.write_main([json.dumps(a), json.dumps(b)])
            got = rt.collect(SESSION, tree.root)
            self.assertEqual(
                got["cache_misses"]["system_changed"],
                {"count": 1, "tokens": 427299},
            )
            # a reason with no token figure still counts as an occurrence
            self.assertEqual(
                got["cache_misses"]["previous_message_not_found"]["count"], 1
            )

    def test_tool_calls_are_tallied_once_per_message_not_per_chunk(self):
        with tempfile.TemporaryDirectory() as tmp:
            tree = Tree(Path(tmp))
            # one streamed reply, repeated — its tool call must count once
            tree.write_main([agent_call("toolu_1"), agent_call("toolu_1")])
            got = rt.collect(SESSION, tree.root)
            self.assertEqual(got["tools"], {"Agent": 1})

    def test_stop_reasons_are_counted(self):
        with tempfile.TemporaryDirectory() as tmp:
            tree = Tree(Path(tmp))
            rows = []
            for i, reason in enumerate(("tool_use", "tool_use", "max_tokens")):
                d = json.loads(assistant(f"m{i}", output=1))
                d["message"]["stop_reason"] = reason
                rows.append(json.dumps(d))
            tree.write_main(rows)
            got = rt.collect(SESSION, tree.root)
            self.assertEqual(got["stop_reasons"], {"tool_use": 2, "max_tokens": 1})

    def test_runtime_context_and_time_window_are_recorded(self):
        with tempfile.TemporaryDirectory() as tmp:
            tree = Tree(Path(tmp))
            rows = []
            for i, stamp in enumerate(("2026-01-01T10:00:00Z", "2026-01-01T10:09:00Z")):
                d = json.loads(assistant(f"m{i}", output=1))
                d["timestamp"] = stamp
                rows.append(json.dumps(d))
            tree.write_main(rows)
            got = rt.collect(SESSION, tree.root)
            self.assertEqual(got["first_message"], "2026-01-01T10:00:00Z")
            self.assertEqual(got["last_message"], "2026-01-01T10:09:00Z")
            self.assertEqual(got["runtime"]["service_tier"], {"standard": 2})


class CrossCheckTest(unittest.TestCase):
    """The one guard against the layout moving underneath the parser.

    Sub-agent transcripts have lived in more than one place across releases.
    If they move again, every count still parses and every number still looks
    plausible — only smaller. Comparing dispatches seen in the main transcript
    against files found on disk is what makes that visible the same night.
    """

    def test_dispatches_with_no_files_is_drift(self):
        with tempfile.TemporaryDirectory() as tmp:
            tree = Tree(Path(tmp))
            tree.write_main([agent_call("toolu_1"), agent_call("toolu_2")])
            got = rt.collect(SESSION, tree.root)
            self.assertEqual(got["agent_dispatches"], 2)
            self.assertEqual(got["subagent_files"], 0)
            self.assertEqual(got["layout_check"], "drift")

    def test_more_files_than_dispatches_is_fine(self):
        # A continued agent or a nested spawn legitimately leaves more files
        # than there were top-level dispatches; only the shortfall is drift.
        with tempfile.TemporaryDirectory() as tmp:
            tree = Tree(Path(tmp))
            tree.write_main([agent_call("toolu_1"), assistant("m1", output=1)])
            tree.add_subagent("agent-a", [assistant("s1", output=1)], {"agentType": "Explore"})
            tree.add_subagent("agent-b", [assistant("s2", output=1)], {"agentType": "Explore"})
            got = rt.collect(SESSION, tree.root)
            self.assertEqual(got["layout_check"], "ok")

    def test_no_agents_at_all_is_ok(self):
        with tempfile.TemporaryDirectory() as tmp:
            tree = Tree(Path(tmp))
            tree.write_main([assistant("m1", output=1)])
            got = rt.collect(SESSION, tree.root)
            self.assertEqual(got["layout_check"], "ok")

    def test_repeated_chunks_of_one_dispatch_count_as_one(self):
        with tempfile.TemporaryDirectory() as tmp:
            tree = Tree(Path(tmp))
            tree.write_main([agent_call("toolu_1"), agent_call("toolu_1")])
            got = rt.collect(SESSION, tree.root)
            self.assertEqual(got["agent_dispatches"], 1)


class SoftFailureTest(unittest.TestCase):
    """No path through this script may return non-zero."""

    def test_absent_session_id_still_writes_a_line_and_exits_zero(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "tick-telemetry.jsonl"
            code = rt.main(["process", "--session-id", "", "--out", str(out)])
            self.assertEqual(code, 0)
            line = json.loads(out.read_text(encoding="utf-8").strip())
            self.assertEqual(line["status"], "unmeasured")
            self.assertIn("CLAUDE_CODE_SESSION_ID", line["note"])

    def test_unreadable_projects_root_exits_zero(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "tick-telemetry.jsonl"
            code = rt.main(
                [
                    "lint",
                    "--session-id",
                    SESSION,
                    "--projects-root",
                    str(Path(tmp) / "nope"),
                    "--out",
                    str(out),
                ]
            )
            self.assertEqual(code, 0)
            self.assertEqual(
                json.loads(out.read_text(encoding="utf-8").strip())["status"],
                "unmeasured",
            )

    def test_collector_exception_is_absorbed_into_the_line(self):
        original = rt.collect
        rt.collect = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom"))
        try:
            line = rt.build_line("roles", SESSION, Path("/nonexistent"))
        finally:
            rt.collect = original
        self.assertEqual(line["status"], "unmeasured")
        self.assertIn("boom", line["note"])

    def test_unwritable_output_still_exits_zero(self):
        with tempfile.TemporaryDirectory() as tmp:
            blocker = Path(tmp) / "blocker"
            _write_lf(blocker, "not a directory")
            code = rt.main(
                ["process", "--session-id", "", "--out", str(blocker / "tick-telemetry.jsonl")]
            )
            self.assertEqual(code, 0)


    def test_missing_tick_tag_records_instead_of_exiting_nonzero(self):
        # A required positional would make argparse exit 2, and a scheduler
        # prompt abandons the tick on any non-zero exit from a helper. The
        # malformed call must still be recorded, never fatal.
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "tick-telemetry.jsonl"
            code = rt.main(["--session-id", "", "--out", str(out)])
            self.assertEqual(code, 0)
            line = json.loads(out.read_text(encoding="utf-8").strip())
            self.assertEqual(line["tick"], "unknown")


class OutputFormatTest(unittest.TestCase):
    def test_lines_append_and_are_lf_terminated(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "state" / "tick-telemetry.jsonl"
            rt.append_line(out, {"ts": "a", "tick": "process"})
            rt.append_line(out, {"ts": "b", "tick": "lint"})
            raw = out.read_bytes()
            self.assertNotIn(b"\r", raw)
            self.assertTrue(raw.endswith(b"\n"))
            rows = [json.loads(x) for x in raw.decode("utf-8").splitlines()]
            self.assertEqual([r["tick"] for r in rows], ["process", "lint"])

    def test_line_carries_the_horizon_and_schema(self):
        with tempfile.TemporaryDirectory() as tmp:
            tree = Tree(Path(tmp))
            tree.write_main([assistant("m1", output=1)])
            line = rt.build_line("agent-lens", SESSION, tree.root)
            self.assertEqual(line["format_version"], rt.FORMAT_VERSION)
            self.assertEqual(line["tick"], "agent-lens")
            self.assertIn("measured_through", line)
            self.assertTrue(line["measured_through"].endswith("Z"))


if __name__ == "__main__":
    unittest.main()
