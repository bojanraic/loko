import os
import pytest
from unittest.mock import patch, MagicMock
from loko.validators import check_docker_running, check_config_file, check_base_dir_writable, ensure_docker_running, ensure_config_file, ensure_base_dir_writable

@patch("subprocess.run")
def test_check_docker_running_success(mock_run):
    mock_run.return_value.returncode = 0
    assert check_docker_running() is True

@patch("subprocess.run")
def test_check_docker_running_failure(mock_run):
    mock_run.return_value.returncode = 1
    assert check_docker_running() is False

def test_check_config_file(mock_config_path):
    assert check_config_file(mock_config_path) is True
    assert check_config_file("non_existent_file.yaml") is False

def test_check_base_dir_writable(temp_dir):
    assert check_base_dir_writable(temp_dir) is True
    # Testing non-writable dir is tricky without root or specific OS setup, skipping for now

@patch("loko.validators.check_docker_running")
@patch("sys.exit")
def test_ensure_docker_running_success(mock_exit, mock_check):
    mock_check.return_value = True
    ensure_docker_running()
    mock_exit.assert_not_called()

@patch("loko.validators.check_docker_running")
@patch("sys.exit")
def test_ensure_docker_running_failure(mock_exit, mock_check):
    mock_check.return_value = False
    ensure_docker_running()
    mock_exit.assert_called_with(1)

@patch("loko.validators.check_config_file")
@patch("sys.exit")
def test_ensure_config_file_failure(mock_exit, mock_check):
    mock_check.return_value = False
    ensure_config_file("config.yaml")
    mock_exit.assert_called_with(1)


@patch("loko.validators.check_config_file")
@patch("sys.exit")
def test_ensure_config_file_success(mock_exit, mock_check):
    """Test ensure_config_file when file exists."""
    mock_check.return_value = True
    ensure_config_file("config.yaml")
    mock_exit.assert_not_called()


@patch("loko.validators.check_base_dir_writable")
@patch("sys.exit")
def test_ensure_base_dir_writable_success(mock_exit, mock_check):
    """Test ensure_base_dir_writable when directory is writable."""
    mock_check.return_value = True
    ensure_base_dir_writable("/tmp/test")
    mock_exit.assert_not_called()


@patch("loko.validators.check_base_dir_writable")
@patch("sys.exit")
def test_ensure_base_dir_writable_failure(mock_exit, mock_check):
    """Test ensure_base_dir_writable when directory is not writable."""
    mock_check.return_value = False
    ensure_base_dir_writable("/tmp/test")
    mock_exit.assert_called_with(1)


def test_check_base_dir_writable_nonexistent():
    """Test checking writable status of non-existent directory."""
    result = check_base_dir_writable("/nonexistent/path/to/dir")
    assert result is False
