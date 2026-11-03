"""MCP server: the app's facts, the configured user's permissions, no release tools."""

import asyncio
import json
import os
import sys
from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from app import mcp_server
from app.core import migrations
from app.core.config import get_settings
from app.core.database import scratch_schema
from app.models import Batch

BACKEND = Path(__file__).resolve().parents[1]


@pytest.fixture
def as_user(db_session, monkeypatch):
    """Point the server at the test session and return a user switcher."""
    monkeypatch.setattr(
        mcp_server,
        "SessionLocal",
        sessionmaker(bind=db_session.get_bind(), expire_on_commit=False),
    )

    def _as(email):
        """Act as the user with this email."""
        monkeypatch.setattr(get_settings(), "mcp_user", email)

    _as("arjun@batchgate.dev")
    return _as


def test_batches_needing_attention_groups_by_status(as_user):
    out = mcp_server.batches_needing_attention()
    assert [b["batch"] for b in out["on_hold"]] == ["FC-2611-07"]
    assert [b["batch"] for b in out["pending_approval"]] == ["MT-2610-31"]
    assert "Insoluble matter" in out["on_hold"][0]["summary"]


def test_get_batch_has_the_findings_and_the_coa_readings(as_user):
    (b,) = mcp_server.get_batch("fc-2611-07")
    assert b["decision"] == "hold" and b["order_line"].startswith("PO-1042 line 1")
    assert any(p["name"] == "Insoluble matter" for p in b["check"]["parameters"])
    assert {c["source"] for c in b["coas"]["coas"]} == {"factory", "lab"}
    with pytest.raises(mcp_server.NotAllowedError, match="No batch"):
        mcp_server.get_batch("NOPE-1")


def test_get_spec_respects_customer_scope(as_user):
    (spec,) = mcp_server.get_spec("Ferric Chloride", grade="40% solution")
    assert any(
        t["name"] == "Insoluble matter" and t["if_it_fails"] == "hold" for t in spec["tests"]
    )
    assert mcp_server.get_spec("Piroctone Olamine")  # analysts see every customer

    as_user("sara@batchgate.dev")  # sales: Ridgeway only
    assert mcp_server.get_spec("Piroctone Olamine") == []


def test_factory_history(as_user):
    out = mcp_server.factory_history("kutch", "Ferric Chloride")
    assert out["factory"] == "Kutch Coastal Chemicals"
    assert {b["batch"] for b in out["batches"]} == {"FC-2611-07", "FC-2611-12"}


def test_rerun_check_needs_permission_and_skips_closed_batches(as_user, db_session):
    (b,) = mcp_server.rerun_check("FC-2611-07")
    assert b["decision"] == "hold"

    batch = db_session.scalar(select(Batch).where(Batch.batch_number == "MT-2610-31"))
    batch.status = batch.status.__class__("released")
    db_session.commit()
    (closed,) = mcp_server.rerun_check("MT-2610-31")
    assert "Closed" in closed["note"]

    as_user("sara@batchgate.dev")
    with pytest.raises(mcp_server.NotAllowedError, match="can't do this"):
        mcp_server.rerun_check("FC-2611-07")


def test_search_knowledge(as_user):
    hits = mcp_server.search_knowledge("retest policy", customer="ridgeway")
    assert hits[0]["source"].endswith("4.2 Retests")
    as_user("sara@batchgate.dev")
    with pytest.raises(mcp_server.NotAllowedError):
        mcp_server.search_knowledge("retest policy")


def test_unknown_user_is_refused(as_user):
    as_user("nobody@example.com")
    with pytest.raises(mcp_server.NotAllowedError, match="BATCHGATE_MCP_USER"):
        mcp_server.batches_needing_attention()


def test_no_tool_can_release_hold_or_reject():
    names = {t.name for t in asyncio.run(mcp_server.server.list_tools())}
    assert names == {
        "batches_needing_attention",
        "get_batch",
        "get_spec",
        "factory_history",
        "search_knowledge",
        "rerun_check",
    }


def test_works_over_stdio_like_claude_desktop():
    """Talk MCP to the real server over stdio."""
    schema = "batchgate_mcp_test"
    with scratch_schema(schema) as engine:
        migrations.upgrade(engine)
        from app.seed import seed

        with sessionmaker(bind=engine, expire_on_commit=False)() as s:
            seed(s)
        env = os.environ | {
            "BATCHGATE_DB_SCHEMA": schema,
            "BATCHGATE_MCP_USER": "meera@batchgate.dev",
        }
        names, result = _talk_to_server(env)
    assert "get_batch" in names
    payload = result.structured_content or json.loads(result.content[0].text)
    payload = payload.get("result", payload)
    assert payload["on_hold"][0]["batch"] == "FC-2611-07"


def _talk_to_server(env):
    """Start the server, list tools and call one."""
    from mcp import ClientSession
    from mcp.client.stdio import StdioServerParameters, stdio_client

    params = StdioServerParameters(
        command=sys.executable, args=["-m", "app.mcp_server"], env=env, cwd=str(BACKEND)
    )

    async def talk():
        """Run the MCP client session."""
        async with stdio_client(params) as (read, write), ClientSession(read, write) as session:
            await session.initialize()
            tools = await session.list_tools()
            result = await session.call_tool("batches_needing_attention", {})
            return {t.name for t in tools.tools}, result

    return asyncio.run(asyncio.wait_for(talk(), timeout=60))
