"""End-to-end tests of the MCP tools through an in-memory client session.

These go through the real JSON-RPC layer (tool listing, argument validation, result
content), with the YouTube backends replaced by the fakes in conftest.py.
"""

from __future__ import annotations

from typing import Any

import pytest
from mcp.shared.memory import create_connected_server_and_client_session
from mcp.types import TextContent

from tests.conftest import FakeSearcher, FakeTranscripts
from youtube_recap.config import AppConfig
from youtube_recap.server import build_server, build_service, prepare_runtime
from youtube_recap.service import RecapService

pytestmark = pytest.mark.anyio


async def _call(service: RecapService, tool: str, args: dict[str, Any]) -> str:
    async with create_connected_server_and_client_session(build_server(service)) as client:
        result = await client.call_tool(tool, args)
    assert not result.isError, result.content
    (content,) = result.content
    assert isinstance(content, TextContent)
    return content.text


async def test_lists_the_three_tools(service: RecapService) -> None:
    async with create_connected_server_and_client_session(build_server(service)) as client:
        tools = (await client.list_tools()).tools
    assert sorted(t.name for t in tools) == ["get_transcript", "recap", "search_videos"]
    assert all(t.description for t in tools)


async def test_search_videos_tool(service: RecapService, searcher: FakeSearcher) -> None:
    out = await _call(service, "search_videos", {"query": "q", "max_results": 3})
    assert out.index("High") < out.index("Low") < out.index("Unknown views")
    assert searcher.calls == [("q", 3)]


async def test_get_transcript_tool(service: RecapService, transcripts: FakeTranscripts) -> None:
    out = await _call(service, "get_transcript", {"video_id": "aaaaaaaaaaa", "languages": ["de"]})
    assert out == "hello world"
    assert transcripts.calls == [("aaaaaaaaaaa", ("de",))]


async def test_get_transcript_tool_missing(service: RecapService) -> None:
    out = await _call(service, "get_transcript", {"video_id": "zzzzzzzzzzz"})
    assert out == "[transcript unavailable: zzzzzzzzzzz: TranscriptsDisabled]"


async def test_recap_tool(service: RecapService) -> None:
    out = await _call(service, "recap", {"query": "q", "num_videos": 2})
    assert out.startswith("## High")
    assert "## Low" in out


async def test_recap_tool_no_results(service: RecapService, searcher: FakeSearcher) -> None:
    searcher.videos = []
    assert await _call(service, "recap", {"query": "nothing"}) == "No results for 'nothing'."


async def test_invalid_input_is_reported_as_tool_error(service: RecapService) -> None:
    async with create_connected_server_and_client_session(build_server(service)) as client:
        result = await client.call_tool("get_transcript", {"video_id": "nope"})
    assert result.isError
    content = result.content[0]
    assert isinstance(content, TextContent)
    assert "not a YouTube video id" in content.text


def test_build_service_wires_real_adapters(config: AppConfig) -> None:
    service = build_service(config)
    assert service.config is config


@pytest.mark.parametrize("enabled", [True, False])
def test_prepare_runtime_trust_store_follows_config(
    config: AppConfig, monkeypatch: pytest.MonkeyPatch, enabled: bool
) -> None:
    calls: list[None] = []
    monkeypatch.setattr("truststore.inject_into_ssl", lambda: calls.append(None))
    network = config.network.model_copy(update={"use_os_trust_store": enabled})
    prepare_runtime(config.model_copy(update={"network": network}))
    assert len(calls) == int(enabled)
