from types import SimpleNamespace

from signal_agent.agent import Agent
from signal_agent.llm_planner import Directive, LLMPlanner
from signal_agent.mission import run_mission


class FakeMessages:
    """Stands in for client.messages; returns scripted directives."""

    def __init__(self, directives):
        self.directives = list(directives)
        self.calls = []

    def parse(self, **kwargs):
        self.calls.append(kwargs)
        if not self.directives:
            raise RuntimeError("no more scripted answers")
        d = self.directives.pop(0)
        if d == "refuse":
            return SimpleNamespace(stop_reason="refusal", parsed_output=None)
        return SimpleNamespace(stop_reason="end_turn", parsed_output=d)


def fake_client(*directives):
    return SimpleNamespace(messages=FakeMessages(directives))


def test_llm_directive_drives_actions(small_config):
    client = fake_client(Directive(action="listen", reasoning="get a fix"), Directive(action="goto_and_scan", target=[3, 7], reasoning="go east"))
    planner = LLMPlanner(client=client, max_calls=5)
    mem = Agent.create(small_config, planner).mem
    d1 = planner.decide(mem)
    assert d1.action.kind == "listen" and d1.source == "llm" and "[Claude]" in d1.reasoning
    d2 = planner.decide(mem)
    assert d2.action.kind == "move" and d2.goal == (3, 7)
    call = client.messages.calls[0]
    assert call["model"] == "claude-opus-5-5" and call["output_format"] is Directive


def test_scan_end_and_recharge_directives(small_config):
    planner = LLMPlanner(client=fake_client(
        Directive(action="scan_here", reasoning="r"),
        Directive(action="recharge", reasoning="r"),
        Directive(action="end_mission", reasoning="r"),
    ), max_calls=5)
    mem = Agent.create(small_config, planner).mem
    assert planner.decide(mem).action.kind == "scan"
    mem.battery = 60.0
    assert planner.decide(mem).action.kind == "recharge"
    planner._directive = None
    assert planner.decide(mem).action.kind == "end"


def test_investigate_clue_directive(small_config):
    planner = LLMPlanner(client=fake_client(Directive(action="investigate_clue", clue_id="clue-1", reasoning="r")), max_calls=5)
    mem = Agent.create(small_config, planner).mem
    mem.pending_clues["clue-1"] = (2, 7)
    assert planner.decide(mem).action.kind == "move"
    mem.position = (2, 7)
    assert planner.decide(mem).action.kind == "inspect"


def test_infeasible_directive_falls_back(small_config):
    planner = LLMPlanner(client=fake_client(Directive(action="investigate_clue", clue_id="nope", reasoning="x")), max_calls=5)
    d = planner.decide(Agent.create(small_config, planner).mem)
    assert d.source == "llm->classical" and "infeasible" in d.reasoning


def test_out_of_bounds_target_falls_back(small_config):
    planner = LLMPlanner(client=fake_client(Directive(action="goto_and_scan", target=[99, 99], reasoning="x")), max_calls=5)
    assert planner.decide(Agent.create(small_config, planner).mem).source == "llm->classical"


def test_refusal_falls_back(small_config):
    planner = LLMPlanner(client=fake_client("refuse"), max_calls=5)
    assert planner.decide(Agent.create(small_config, planner).mem).source == "llm->classical"


def test_call_budget_caps_api_use(small_config):
    planner = LLMPlanner(client=fake_client(*[Directive(action="listen", reasoning="r")] * 50), max_calls=3)
    result = run_mission(small_config, planner)
    assert planner.calls == 3
    assert result.outcome == "eve_located"


def test_situation_is_built_from_memory_only(small_config):
    s = LLMPlanner.situation(Agent.create(small_config).mem)
    assert "eve" not in s and s["ranked_targets"]
    assert s["position"] == [0, 7]
