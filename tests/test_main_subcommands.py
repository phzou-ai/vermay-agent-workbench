from __future__ import annotations

import json

from mini_agent.cli import subcommands as cli


def test_memory_cli_add_list_disable(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(cli, "DEFAULT_AGENT_STORE_PATH", tmp_path / "agent.sqlite")

    cli.run_memory_command(["add", "Prefer safe tools.", "--tag", "preference"])
    cli.run_memory_command(["list"])
    output = capsys.readouterr().out

    assert "added memory 1" in output
    assert "Prefer safe tools." in output

    cli.run_memory_command(["disable", "1"])
    assert "disabled memory 1" in capsys.readouterr().out


def test_eval_cli_replay_scenario(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(cli, "DEFAULT_AGENT_STORE_PATH", tmp_path / "agent.sqlite")
    monkeypatch.setattr(cli, "ROOT", tmp_path)
    scenario = tmp_path / "scenario.json"
    scenario.write_text(
        json.dumps(
            {
                "input": "weather",
                "tool_observations": [{"name": "weather_forecast"}],
                "final_answer": "Shanghai Weather",
                "expect": {"tool_sequence": ["weather_forecast"], "final_contains": ["Shanghai"]},
            }
        ),
        encoding="utf-8",
    )

    cli.run_eval_command(["replay", "--scenario", str(scenario)])
    output = capsys.readouterr().out

    assert '"status": "passed"' in output
    assert (tmp_path / "data" / "eval_runs").exists()
