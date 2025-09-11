import builtins
import sys
from types import SimpleNamespace
import subprocess
import pytest

import branch_vacuum as bv


# --- run_git_command tests ---

def test_run_git_command_capture_true_returns_lines(monkeypatch):
    # Arrange
    class DummyCompleted:
        stdout = "line1\nline2\n"
    calls = {}

    def fake_run(cmd, capture_output, text, check):
        # Assert internal parameters
        calls["capture_output"] = capture_output
        calls["text"] = text
        calls["check"] = check
        return DummyCompleted()

    monkeypatch.setattr(subprocess, "run", fake_run)

    # Act
    result = bv.run_git_command(["status"], repo_dir="/repo", capture=True)

    # Assert
    assert result == ["line1", "line2"]
    assert calls["capture_output"] is True
    assert calls["text"] is True
    assert calls["check"] is True


def test_run_git_command_capture_false_returns_empty_and_no_capture(monkeypatch):
    # Arrange
    class DummyCompleted:
        stdout = "should not be read"

    calls = {}

    def fake_run(cmd, capture_output, text, check):
        calls["cmd"] = cmd
        calls["capture_output"] = capture_output
        return DummyCompleted()

    monkeypatch.setattr(subprocess, "run", fake_run)

    # Act
    result = bv.run_git_command(["fetch"], repo_dir="C:/repo", capture=False)

    # Assert
    assert result == []
    # Ensure we passed the repo directory correctly and capture_output is False
    assert calls["cmd"][:3] == ["git", "-C", "C:/repo"]
    assert calls["capture_output"] is False


# --- get_local_branches / get_remote_branches tests ---

def test_get_local_branches_proxies_to_run_git_command(monkeypatch):
    # Arrange
    expected = ["main", "feature/a"]

    def fake_run_git_command(args, repo_dir, silent=False, capture=True):
        assert args == ["branch", "--format", "%(refname:short)"]
        assert repo_dir == "C:/repo"
        return expected

    monkeypatch.setattr(bv, "run_git_command", fake_run_git_command)

    # Act
    branches = bv.get_local_branches("C:/repo")

    # Assert
    assert branches is expected


def test_get_remote_branches_filters_and_strips_origin_prefix(monkeypatch):
    # Arrange
    def fake_run_git_command(args, repo_dir, silent=False, capture=True):
        assert args == ["branch", "-r", "--format", "%(refname:short)"]
        assert repo_dir == "X:/repo"
        return [
            "origin/main",
            " origin/feature/x ",
            "upstream/dev",
            "random/branch",
        ]

    monkeypatch.setattr(bv, "run_git_command", fake_run_git_command)

    # Act
    branches = bv.get_remote_branches("X:/repo")

    # Assert
    assert branches == ["main", "feature/x"]


# --- delete_branch tests ---

def test_delete_branch_success_prints_message(monkeypatch, capsys):
    # Arrange
    calls = {}

    def fake_run(cmd, check):
        calls["cmd"] = cmd
        return SimpleNamespace()

    monkeypatch.setattr(subprocess, "run", fake_run)

    # Act
    bv.delete_branch("feature/1", repo_dir="D:/repo", force=True)

    # Assert
    out = capsys.readouterr().out
    assert "Deleted branch: feature/1" in out
    assert calls["cmd"] == ["git", "-C", "D:/repo", "branch", "-D", "feature/1"]


def test_delete_branch_failure_prints_error(monkeypatch, capsys):
    # Arrange
    def fake_run(cmd, check):
        raise subprocess.CalledProcessError(returncode=1, cmd=cmd)

    monkeypatch.setattr(subprocess, "run", fake_run)

    # Act
    bv.delete_branch("main", repo_dir="/repo", force=False)

    # Assert
    out = capsys.readouterr().out
    assert "Could not delete branch 'main'" in out


# --- main() tests ---

def test_main_invalid_repo_exits_with_message(monkeypatch, capsys):
    # Arrange
    # Make rev-parse fail
    def fake_run_git_command(args, repo_dir, silent=False, capture=True):
        if args[:2] == ["rev-parse", "--is-inside-work-tree"]:
            raise subprocess.CalledProcessError(returncode=128, cmd="git rev-parse")
        return []

    monkeypatch.setattr(bv, "run_git_command", fake_run_git_command)

    monkeypatch.setenv("PYTHONWARNINGS", "ignore")
    monkeypatch.setattr(sys, "argv", ["prog", "C:/not-a-repo"])

    # Act
    with pytest.raises(SystemExit) as exc:
        bv.main()

    # Assert
    assert exc.value.code == 1
    out = capsys.readouterr().out
    assert "is not a valid git repository" in out


def test_main_no_local_only_branches_prints_message(monkeypatch, capsys):
    # Arrange
    def fake_run_git_command(args, repo_dir, silent=False, capture=True):
        # Pretend fetch works and rev-parse passes
        return []

    monkeypatch.setattr(bv, "run_git_command", fake_run_git_command)
    monkeypatch.setattr(bv, "get_local_branches", lambda repo: ["main", "feature/x"])
    monkeypatch.setattr(bv, "get_remote_branches", lambda repo: ["main", "feature/x"])

    monkeypatch.setattr(sys, "argv", ["prog", "C:/repo"])

    # Act
    bv.main()

    # Assert
    out = capsys.readouterr().out
    assert "Fetch complete" in out
    assert "No local-only branches" in out


def test_main_delete_yes_calls_delete_branch(monkeypatch, capsys):
    # Arrange
    def fake_run_git_command(args, repo_dir, silent=False, capture=True):
        return []

    monkeypatch.setattr(bv, "run_git_command", fake_run_git_command)
    monkeypatch.setattr(bv, "get_local_branches", lambda repo: ["feature/x"])
    monkeypatch.setattr(bv, "get_remote_branches", lambda repo: [])

    called = {}

    def fake_delete_branch(branch, repo_dir, force):
        called["branch"] = branch
        called["repo_dir"] = repo_dir
        called["force"] = force

    monkeypatch.setattr(bv, "delete_branch", fake_delete_branch)

    # First input is 'y'
    monkeypatch.setattr(builtins, "input", lambda prompt='': "y")

    monkeypatch.setattr(sys, "argv", ["prog", "C:/repo"])  # no --safe

    # Act
    bv.main()

    # Assert
    assert called == {"branch": "feature/x", "repo_dir": "C:/repo", "force": True}


def test_main_keep_no_prints_message(monkeypatch, capsys):
    # Arrange
    monkeypatch.setattr(bv, "run_git_command", lambda *a, **k: [])
    monkeypatch.setattr(bv, "get_local_branches", lambda repo: ["feature/x"])
    monkeypatch.setattr(bv, "get_remote_branches", lambda repo: [])
    monkeypatch.setattr(builtins, "input", lambda prompt='': "n")
    monkeypatch.setattr(sys, "argv", ["prog", "C:/repo"])  # no --safe

    # Act
    bv.main()

    # Assert
    out = capsys.readouterr().out
    assert "Keeping branch: feature/x" in out


def test_main_keep_default_empty_prints_message(monkeypatch, capsys):
    # Arrange
    monkeypatch.setattr(bv, "run_git_command", lambda *a, **k: [])
    monkeypatch.setattr(bv, "get_local_branches", lambda repo: ["feature/x"])
    monkeypatch.setattr(bv, "get_remote_branches", lambda repo: [])
    monkeypatch.setattr(builtins, "input", lambda prompt='': " ")  # -> "" after strip
    monkeypatch.setattr(sys, "argv", ["prog", "C:/repo"])  # no --safe

    # Act
    bv.main()

    # Assert
    out = capsys.readouterr().out
    assert "Keeping branch: feature/x" in out


def test_main_invalid_then_yes_prompts_again_and_deletes(monkeypatch, capsys):
    # Arrange
    monkeypatch.setattr(bv, "run_git_command", lambda *a, **k: [])
    monkeypatch.setattr(bv, "get_local_branches", lambda repo: ["f1"])
    monkeypatch.setattr(bv, "get_remote_branches", lambda repo: [])

    inputs = iter(["maybe", "y"])  # invalid first, then yes
    monkeypatch.setattr(builtins, "input", lambda prompt='': next(inputs))

    called = {"count": 0}

    def fake_delete_branch(branch, repo_dir, force):
        called["count"] += 1
        called["last"] = (branch, repo_dir, force)

    monkeypatch.setattr(bv, "delete_branch", fake_delete_branch)

    monkeypatch.setattr(sys, "argv", ["prog", "C:/repo", "--safe"])  # with --safe

    # Act
    bv.main()

    # Assert
    out = capsys.readouterr().out
    assert "Please answer with 'y' or 'n'" in out
    assert called["count"] == 1
    # With --safe, force should be False
    assert called["last"] == ("f1", "C:/repo", False)
