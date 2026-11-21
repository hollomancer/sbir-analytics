"""Tests for the environment-variable readers in ``sbir_etl.config.loader``."""

import pytest

from sbir_etl.config.loader import env_bool, env_float, env_int


pytestmark = pytest.mark.unit

KEY = "SBIR_ETL__TEST__ENV_NUMBER"


@pytest.mark.parametrize(("reader", "default"), [(env_float, 0.6), (env_int, 1000)])
def test_unset_returns_default(monkeypatch, reader, default):
    monkeypatch.delenv(KEY, raising=False)
    assert reader(KEY, default) == default


@pytest.mark.parametrize("raw", ["", "   ", "\t\n"])
@pytest.mark.parametrize(("reader", "default"), [(env_float, 0.6), (env_int, 1000)])
def test_empty_or_blank_returns_default(monkeypatch, reader, default, raw):
    monkeypatch.setenv(KEY, raw)
    assert reader(KEY, default) == default


@pytest.mark.parametrize(
    ("raw", "expected"),
    [("0.8", 0.8), (" 0.8 ", 0.8), ("1", 1.0), ("-0.25", -0.25), ("1e-3", 0.001)],
)
def test_env_float_valid(monkeypatch, raw, expected):
    monkeypatch.setenv(KEY, raw)
    assert env_float(KEY, 0.6) == pytest.approx(expected)


@pytest.mark.parametrize(("raw", "expected"), [("5000", 5000), (" 42\n", 42), ("-1", -1), ("0", 0)])
def test_env_int_valid(monkeypatch, raw, expected):
    monkeypatch.setenv(KEY, raw)
    assert env_int(KEY, 1000) == expected


@pytest.mark.parametrize("raw", ["abc", "0,8", "1e", "nan", "NaN", "inf", "-inf", "80%"])
def test_env_float_rejects_unparseable_or_non_finite(monkeypatch, raw):
    monkeypatch.setenv(KEY, raw)
    with pytest.raises(ValueError) as excinfo:
        env_float(KEY, 0.6)
    message = str(excinfo.value)
    assert KEY in message
    assert repr(raw) in message


@pytest.mark.parametrize("raw", ["abc", "0,8", "1e", "5.0", "1e3", "10,000"])
def test_env_int_rejects_unparseable(monkeypatch, raw):
    monkeypatch.setenv(KEY, raw)
    with pytest.raises(ValueError) as excinfo:
        env_int(KEY, 1000)
    message = str(excinfo.value)
    assert KEY in message
    assert repr(raw) in message


@pytest.mark.parametrize("raw", [None, "", "   "])
@pytest.mark.parametrize("default", [True, False])
def test_env_bool_unset_or_blank_returns_default(monkeypatch, raw, default):
    if raw is None:
        monkeypatch.delenv(KEY, raising=False)
    else:
        monkeypatch.setenv(KEY, raw)
    assert env_bool(KEY, default) is default


@pytest.mark.parametrize("raw", ["1", "true", "TRUE", " Yes ", "on"])
def test_env_bool_true_words(monkeypatch, raw):
    monkeypatch.setenv(KEY, raw)
    assert env_bool(KEY, False) is True


@pytest.mark.parametrize("raw", ["0", "false", "False", " no ", "OFF"])
def test_env_bool_false_words(monkeypatch, raw):
    monkeypatch.setenv(KEY, raw)
    # Default True so a false word cannot pass by falling through to the default.
    assert env_bool(KEY, True) is False


@pytest.mark.parametrize("raw", ["ture", "flase", "y", "n", "2", "enabled", "1.0"])
def test_env_bool_rejects_unknown_words(monkeypatch, raw):
    monkeypatch.setenv(KEY, raw)
    with pytest.raises(ValueError, match=KEY):
        env_bool(KEY, False)
