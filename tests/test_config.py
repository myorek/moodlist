import textwrap

import pytest

from moodlist.config import load_config


def test_load_config_reads_toml(temp_home):
    cfg_path = temp_home / "config.toml"
    cfg_path.write_text(textwrap.dedent("""
        [anthropic]
        api_key = "sk-ant-test"
        model   = "claude-haiku-4-5-20251001"

        [library]
        root = "~/Music"
        extensions = ["flac"]

        [foobar2000]
        app = "foobar2000"

        [playlist]
        default_count = 20
        temperature   = 0.4
    """))
    cfg = load_config(cfg_path)
    assert cfg.api_key == "sk-ant-test"
    assert cfg.model == "claude-haiku-4-5-20251001"
    assert cfg.library_root.name == "Music"
    assert cfg.extensions == ["flac"]
    assert cfg.foobar_app == "foobar2000"
    assert cfg.default_count == 20
    assert cfg.temperature == 0.4


def test_load_config_missing_file_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_config(tmp_path / "nope.toml")


def test_load_config_missing_api_key_raises(temp_home):
    cfg_path = temp_home / "config.toml"
    cfg_path.write_text('[anthropic]\nmodel = "x"\n')
    with pytest.raises(ValueError, match="anthropic.api_key"):
        load_config(cfg_path)
