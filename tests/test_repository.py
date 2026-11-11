import pytest

from backend.app.services.repository import RepositoryError, _validate_repository_url


def test_rejects_non_https_repository():
    with pytest.raises(RepositoryError):
        _validate_repository_url("file:///tmp/repository")


def test_rejects_unapproved_host():
    with pytest.raises(RepositoryError):
        _validate_repository_url("https://example.com/repository.git")
