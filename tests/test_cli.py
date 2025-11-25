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


def test_generate_config_help():
    """Test loko generate-config --help command."""
    result = runner.invoke(app, ["generate-config", "--help"])
    assert result.exit_code == 0
    assert "generate" in result.stdout.lower() or "config" in result.stdout.lower()


def test_no_args_shows_help():
    """Test that running loko without args shows help."""
    result = runner.invoke(app, [])
    # Should show help or usage information
    assert "loko" in result.stdout.lower() or "usage" in result.stdout.lower()
