import pytest

from app.config import Settings
from app.llm_client import ModelGateway


@pytest.mark.asyncio
async def test_router_mock_decision_web_and_memory():
    cfg = Settings(
        hachi_mock_mode=True,
        memory_max_messages=2,
        memory_max_tokens=5,
    )
    gateway = ModelGateway(cfg)

    plan = await gateway.router_plan(
        question="What is the latest AI news today?",
        allow_web=True,
        allow_memory_compress=True,
        message_count=3,
        token_count=10,
        memory_exists=False,
    )

    assert plan["need_web_search"] is True
    assert plan["need_memory_compress"] is True
    assert plan["search_queries"]


def test_deepseek_router_and_answer_bindings():
    cfg = Settings(
        _env_file=None,
        router_base_url="https://api.deepseek.com",
        router_api_key="sk-test",
        router_model="deepseek-v4-flash",
        answer_base_url="https://api.deepseek.com",
        answer_model="deepseek-v4-flash",
    )

    assert cfg.resolved_router_base_url == "https://api.deepseek.com"
    assert cfg.resolved_router_api_key == "sk-test"
    assert cfg.resolved_router_model == "deepseek-v4-flash"
    assert cfg.resolved_answer_base_url == "https://api.deepseek.com"
    assert cfg.resolved_answer_api_key == "sk-test"
    assert cfg.resolved_answer_model == "deepseek-v4-flash"
    assert cfg.role_bindings["router"] == "deepseek-v4-flash"
    assert cfg.role_bindings["answer"] == "deepseek-v4-flash"
