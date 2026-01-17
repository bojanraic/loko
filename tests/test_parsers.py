import pytest
from loko.updates.parsers import parse_updater_comment


def test_parse_docker_comment():
    """Test parsing Docker loko-updater comments."""
    comment = "# loko-updater: datasource=docker depName=kindest/node"
    result = parse_updater_comment(comment)
    assert result is not None
    assert result['datasource'] == 'docker'
    assert result['depName'] == 'kindest/node'
    assert 'repositoryUrl' not in result


def test_parse_helm_comment():
    """Test parsing Helm loko-updater comments."""
    comment = "# loko-updater: datasource=helm depName=traefik repositoryUrl=https://traefik.github.io/charts"
    result = parse_updater_comment(comment)
    assert result is not None
    assert result['datasource'] == 'helm'
    assert result['depName'] == 'traefik'
    assert result['repositoryUrl'] == 'https://traefik.github.io/charts'


def test_parse_helm_comment_with_http():
    """Test parsing Helm comment with http URL."""
    comment = "# loko-updater: datasource=helm depName=mysql repositoryUrl=http://charts.example.com"
    result = parse_updater_comment(comment)
    assert result is not None
    assert result['datasource'] == 'helm'
    assert result['depName'] == 'mysql'
    assert result['repositoryUrl'] == 'http://charts.example.com'


def test_parse_comment_with_special_chars_in_depname():
    """Test parsing depName with dots, dashes, slashes."""
    comment = "# loko-updater: datasource=docker depName=my-org/my.app-name"
    result = parse_updater_comment(comment)
    assert result is not None
    assert result['depName'] == 'my-org/my.app-name'


def test_parse_comment_no_updater_keyword():
    """Test that comments without 'loko-updater:' return None."""
    comment = "# This is just a regular comment"
    result = parse_updater_comment(comment)
    assert result is None


def test_parse_comment_missing_datasource():
    """Test that comments without datasource return None."""
    comment = "# loko-updater: depName=kindest/node"
    result = parse_updater_comment(comment)
    assert result is None


def test_parse_comment_missing_depname():
    """Test that comments without depName return None."""
    comment = "# loko-updater: datasource=docker"
    result = parse_updater_comment(comment)
    assert result is None


def test_parse_comment_with_extra_whitespace():
    """Test parsing comments with extra whitespace."""
    comment = "  # loko-updater:   datasource=docker   depName=kindest/node  "
    result = parse_updater_comment(comment)
    assert result is not None
    assert result['datasource'] == 'docker'
    assert result['depName'] == 'kindest/node'


def test_parse_comment_with_multiple_fields():
    """Test parsing comment with all fields."""
    comment = "# loko-updater: datasource=helm depName=chart-name repositoryUrl=https://example.com/charts"
    result = parse_updater_comment(comment)
    assert result is not None
    assert result['datasource'] == 'helm'
    assert result['depName'] == 'chart-name'
    assert result['repositoryUrl'] == 'https://example.com/charts'


def test_parse_empty_comment():
    """Test parsing empty comment."""
    result = parse_updater_comment("")
    assert result is None


def test_parse_comment_with_unsupported_datasource():
    """Test parsing comment with unsupported datasource (should still parse)."""
    comment = "# loko-updater: datasource=npm depName=react"
    result = parse_updater_comment(comment)
    assert result is not None
    assert result['datasource'] == 'npm'
    assert result['depName'] == 'react'
