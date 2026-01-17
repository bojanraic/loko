import pytest
from typer.testing import CliRunner
from loko.cli import app


runner = CliRunner()


def test_version_command():
    """Test loko version command."""
    result = runner.invoke(app, ["version"])
    assert result.exit_code == 0
    # Should output version number
    assert result.stdout.strip() != ""


def test_help_command():
    """Test loko --help command."""
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "loko" in result.stdout.lower()


def test_help_short_flag():
    """Test loko -h command."""
    result = runner.invoke(app, ["-h"])
    assert result.exit_code == 0
    assert "loko" in result.stdout.lower()


def test_check_prerequisites_command():
    """Test loko check-prerequisites command."""
    result = runner.invoke(app, ["check-prerequisites"])
    # Exit code may be 0 or 1 depending on system prerequisites
    # Just check that it runs without crashing
    assert result.exit_code in [0, 1]


def test_config_help():
    """Test loko config --help command."""
    result = runner.invoke(app, ["config", "--help"])
    assert result.exit_code == 0
    assert "config" in result.stdout.lower()


def test_init_help():
    """Test loko init --help command."""
    result = runner.invoke(app, ["init", "--help"])
    assert result.exit_code == 0
    assert "init" in result.stdout.lower()


def test_create_help():
    """Test loko create --help command."""
    result = runner.invoke(app, ["create", "--help"])
    assert result.exit_code == 0
    assert "create" in result.stdout.lower()


def test_destroy_help():
    """Test loko destroy --help command."""
    result = runner.invoke(app, ["destroy", "--help"])
    assert result.exit_code == 0
    assert "destroy" in result.stdout.lower()


def test_start_help():
    """Test loko start --help command."""
    result = runner.invoke(app, ["start", "--help"])
    assert result.exit_code == 0
    assert "start" in result.stdout.lower()


def test_stop_help():
    """Test loko stop --help command."""
    result = runner.invoke(app, ["stop", "--help"])
    assert result.exit_code == 0
    assert "stop" in result.stdout.lower()


def test_status_help():
    """Test loko status --help command."""
    result = runner.invoke(app, ["status", "--help"])
    assert result.exit_code == 0
    assert "status" in result.stdout.lower()


def test_validate_help():
    """Test loko validate --help command."""
    result = runner.invoke(app, ["validate", "--help"])
    assert result.exit_code == 0
    assert "validate" in result.stdout.lower()


def test_config_generate_help():
    """Test loko config generate --help command."""
    result = runner.invoke(app, ["config", "generate", "--help"])
    assert result.exit_code == 0
    assert "generate" in result.stdout.lower()


def test_config_validate_help():
    """Test loko config validate --help command."""
    result = runner.invoke(app, ["config", "validate", "--help"])
    assert result.exit_code == 0
    assert "validate" in result.stdout.lower()


def test_config_port_check_help():
    """Test loko config port-check --help command."""
    result = runner.invoke(app, ["config", "port-check", "--help"])
    assert result.exit_code == 0
    assert "port" in result.stdout.lower()


def test_no_args_shows_help():
    """Test that running loko without args shows help."""
    result = runner.invoke(app, [])
    # Should show help or usage information
    assert "loko" in result.stdout.lower() or "usage" in result.stdout.lower()


def test_completion_help():
    """Test loko completion --help command."""
    result = runner.invoke(app, ["completion", "--help"])
    assert result.exit_code == 0
    assert "completion" in result.stdout.lower()
    assert "bash" in result.stdout.lower()
    assert "zsh" in result.stdout.lower()
    assert "fish" in result.stdout.lower()


def test_completion_bash():
    """Test loko completion bash outputs valid bash completion script."""
    result = runner.invoke(app, ["completion", "bash"])
    assert result.exit_code == 0
    assert "_loko_completion" in result.stdout
    assert "complete" in result.stdout
    assert "COMPREPLY" in result.stdout


def test_completion_zsh():
    """Test loko completion zsh outputs valid zsh completion script."""
    result = runner.invoke(app, ["completion", "zsh"])
    assert result.exit_code == 0
    assert "#compdef loko" in result.stdout
    assert "_loko_completion" in result.stdout
    assert "compdef" in result.stdout


def test_completion_fish():
    """Test loko completion fish outputs valid fish completion script."""
    result = runner.invoke(app, ["completion", "fish"])
    assert result.exit_code == 0
    assert "complete" in result.stdout and "loko" in result.stdout


def test_completion_invalid_shell():
    """Test loko completion with invalid shell argument."""
    result = runner.invoke(app, ["completion", "powershell"])
    assert result.exit_code != 0
