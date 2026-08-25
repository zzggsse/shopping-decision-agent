"""本地配置加载的行为约束。

这里守两件事，错了会很难排查：
  1. 终端里显式指定的环境变量不能被文件默默覆盖
  2. 文件不存在不是错误（不配任何凭据也要能跑）
"""

from __future__ import annotations

import os
import pathlib

import pytest

from app.env import load_local_env


@pytest.fixture
def env_file():
    """在仓库内建临时文件。不用 tmp_path：部分环境下系统临时目录不可写。"""
    target = pathlib.Path(__file__).with_name("_tmp_local.env")
    yield target
    target.unlink(missing_ok=True)


def test_missing_file_is_not_an_error(env_file) -> None:
    assert not env_file.exists()
    assert load_local_env(env_file) == []


def test_loads_key_value_pairs(env_file, monkeypatch) -> None:
    env_file.write_text(
        "# 注释行\n"
        "\n"
        "LLM_PROVIDER=ark\n"
        'ARK_MODEL="ep-123"\n'
        "EMPTY=\n"
        "不是配置行\n",
        encoding="utf-8",
    )
    # 用 setenv 先占位再删，让 monkeypatch 接管这两个变量的恢复，
    # 否则 load_local_env 写进 os.environ 的值会泄到其他测试里
    monkeypatch.setenv("LLM_PROVIDER", "")
    monkeypatch.setenv("ARK_MODEL", "")
    monkeypatch.delenv("LLM_PROVIDER")
    monkeypatch.delenv("ARK_MODEL")

    applied = load_local_env(env_file)

    assert set(applied) == {"LLM_PROVIDER", "ARK_MODEL"}
    assert os.environ["LLM_PROVIDER"] == "ark"
    # 引号应被剔除
    assert os.environ["ARK_MODEL"] == "ep-123"
    # 空值不写入，避免用空串覆盖默认值
    assert "EMPTY" not in applied


def test_existing_env_wins(env_file, monkeypatch) -> None:
    env_file.write_text("LLM_PROVIDER=ark\n", encoding="utf-8")
    monkeypatch.setenv("LLM_PROVIDER", "openai")

    applied = load_local_env(env_file)

    assert "LLM_PROVIDER" not in applied
    assert os.environ["LLM_PROVIDER"] == "openai"
