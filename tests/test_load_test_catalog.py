import pytest

from scripts.load_test_catalog import (
    local_search_count,
    parse_user_levels,
    percentile,
    validate_target,
)


def test_parse_user_levels_requires_positive_unique_increasing_values():
    assert parse_user_levels("1,5,10") == [1, 5, 10]

    with pytest.raises(ValueError, match="positive"):
        parse_user_levels("1,0,5")
    with pytest.raises(ValueError, match="increasing"):
        parse_user_levels("5,1")
    with pytest.raises(ValueError, match="maximum"):
        parse_user_levels("201")


def test_load_test_refuses_remote_targets_without_explicit_permission():
    with pytest.raises(ValueError, match="--allow-remote"):
        validate_target(
            "https://catalog.example.com",
            [1, 5],
            ["csv"],
            allow_remote=False,
            allow_high_load=False,
            allow_remote_zip=False,
        )


def test_remote_target_requires_https():
    with pytest.raises(ValueError, match="HTTPS"):
        validate_target(
            "http://catalog.example.com",
            [1],
            ["csv"],
            allow_remote=True,
            allow_high_load=False,
            allow_remote_zip=False,
        )


def test_remote_concurrency_and_zip_require_explicit_high_load_opt_in():
    with pytest.raises(ValueError, match="20 users"):
        validate_target(
            "https://catalog.example.com",
            [1, 25],
            ["csv"],
            allow_remote=True,
            allow_high_load=False,
            allow_remote_zip=False,
        )
    with pytest.raises(ValueError, match="ZIP"):
        validate_target(
            "https://catalog.example.com",
            [1],
            ["zip"],
            allow_remote=True,
            allow_high_load=False,
            allow_remote_zip=False,
        )


def test_local_search_counts_case_insensitive_product_matches():
    products = [
        {"Nome": "Luminária Trilho", "Codigo": "6148", "Categoria": "Trilho"},
        {"Nome": "Pendente", "Codigo": "7020", "Categoria": "Decorativo"},
    ]

    assert local_search_count(products, "LUMINÁRIA") == 1
    assert local_search_count(products, "70") == 1
    assert local_search_count(products, "inexistente") == 0


def test_percentile_uses_nearest_rank_and_handles_empty_samples():
    assert percentile([5, 1, 3, 2, 4], 0.95) == 5
    assert percentile([5, 1, 3, 2, 4], 0.5) == 3
    assert percentile([], 0.95) == 0
