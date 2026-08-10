#
# Copyright (c) 2024-2026, Daily
#
# SPDX-License-Identifier: BSD 2-Clause License
#

"""Pipecat voice bot, adapted for self-hosting on Cloud Run.

Changes from the upstream quickstart:

- Uses the plain **WebSocket** transport (Cloud Run speaks HTTP/WebSocket, not
  WebRTC/UDP). One WebSocket connection == one conversation, which pairs with
  Cloud Run ``concurrency=1`` to give the "one container = one slot" rule.
- Ships a tiny raw-PCM serializer so the timing harness can detect first audio
  as the first binary frame.
- Emits structured, greppable timing logs (``COLDSTART ...``) so we can break
  down where the startup seconds go: process start -> imports done -> first
  client connected -> first audio out.

Run locally::

    python bot.py -t websocket --host 0.0.0.0 --port 7860
"""

import json
import os
import time

# t0 for the cold-start breakdown: the earliest point we can observe in-process.
_T_PROC_START = time.time()


def _log_event(event: str, **fields) -> None:
    """Emit a single-line JSON log that's trivial to grep/parse from Cloud Run."""
    record = {"coldstart_event": event, "t_wall": round(time.time(), 4)}
    record.update(fields)
    print("COLDSTART " + json.dumps(record), flush=True)


_log_event("process_start", note="module import beginning")

from dotenv import load_dotenv  # noqa: E402
from loguru import logger  # noqa: E402

# The heavy imports below (Silero VAD weights + the pipecat pipeline graph) are
# what make the first cold start ~20s even with the image already on disk.
_t_import_start = time.time()

logger.info("Loading Silero VAD model...")
from pipecat.audio.vad.silero import SileroVADAnalyzer  # noqa: E402

logger.info("Loading pipeline components...")
from pipecat.frames.frames import Frame, LLMRunFrame, OutputAudioRawFrame, TTSSpeakFrame  # noqa: E402
from pipecat.pipeline.pipeline import Pipeline  # noqa: E402
from pipecat.pipeline.runner import PipelineRunner  # noqa: E402
from pipecat.pipeline.task import PipelineParams, PipelineTask  # noqa: E402
from pipecat.processors.aggregators.llm_context import LLMContext  # noqa: E402
from pipecat.processors.aggregators.llm_response_universal import (  # noqa: E402
    LLMContextAggregatorPair,
    LLMUserAggregatorParams,
)
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor  # noqa: E402
from pipecat.runner.types import RunnerArguments  # noqa: E402
from pipecat.runner.utils import create_transport  # noqa: E402
from pipecat.services.deepgram.stt import DeepgramSTTService  # noqa: E402
from pipecat.services.deepgram.tts import DeepgramTTSService  # noqa: E402
from pipecat.services.openai.llm import OpenAILLMService  # noqa: E402


class NvidiaLLMService(OpenAILLMService):
    """OpenAI-compatible client pointed at NVIDIA integrate.api.nvidia.com."""

    supports_developer_role = False


def _env_key(name: str) -> str | None:
    val = os.getenv(name)
    if not val or val.strip().lower() in {"unused", "none", "placeholder"}:
        return None
    return val
from pipecat.transports.base_transport import BaseTransport  # noqa: E402
from pipecat.transports.websocket.fastapi import FastAPIWebsocketParams  # noqa: E402

from raw_serializer import RawAudioServerSerializer  # noqa: E402

_IMPORT_SECONDS = time.time() - _t_import_start
logger.info("✅ All components loaded successfully!")
_log_event(
    "imports_done",
    import_seconds=round(_IMPORT_SECONDS, 3),
    since_process_start=round(time.time() - _T_PROC_START, 3),
)

load_dotenv(override=True)

_SYSTEM_INSTRUCTION = (
    "You are a friendly AI assistant. Respond naturally and keep your "
    "answers conversational."
)


def _create_llm():
    """Pick LLM backend from env: NVIDIA (Llama) > OpenAI."""
    nvidia_key = _env_key("NVIDIA_API_KEY")
    if nvidia_key:
        logger.info("Using NVIDIA NIM LLM (Llama)")
        return NvidiaLLMService(
            api_key=nvidia_key,
            base_url=os.getenv("NVIDIA_BASE_URL", "https://integrate.api.nvidia.com/v1"),
            settings=NvidiaLLMService.Settings(
                model=os.getenv("NVIDIA_MODEL", "meta/llama-3.1-8b-instruct"),
                system_instruction=_SYSTEM_INSTRUCTION,
                temperature=0.2,
                top_p=0.7,
                max_tokens=int(os.getenv("NVIDIA_MAX_TOKENS", "48")),
            ),
        )
    openai_key = _env_key("OPENAI_API_KEY")
    if not openai_key:
        raise RuntimeError("Set NVIDIA_API_KEY or OPENAI_API_KEY")
    logger.info("Using OpenAI LLM")
    return OpenAILLMService(
        api_key=openai_key,
        settings=OpenAILLMService.Settings(system_instruction=_SYSTEM_INSTRUCTION),
    )


class FirstAudioMarker(FrameProcessor):
    """Logs the moment the first output audio frame passes, per conversation.

    Placed between TTS and the transport output so we can measure the
    server-side slice of first-audio latency (connect -> greeting audio),
    independent of network time measured by the harness.
    """

    def __init__(self) -> None:
        super().__init__()
        self._connected_at: float | None = None
        self._fired = False

    def mark_connected(self) -> None:
        self._connected_at = time.time()
        self._fired = False

    async def process_frame(self, frame: Frame, direction: FrameDirection):
        await super().process_frame(frame, direction)
        if (
            not self._fired
            and isinstance(frame, OutputAudioRawFrame)
            and self._connected_at is not None
        ):
            self._fired = True
            _log_event(
                "first_audio",
                connect_to_first_audio_seconds=round(time.time() - self._connected_at, 3),
            )
        await self.push_frame(frame, direction)


async def run_bot(transport: BaseTransport, runner_args: RunnerArguments):
    logger.info("Starting bot")

    stt = DeepgramSTTService(api_key=os.getenv("DEEPGRAM_API_KEY"))

    # Deepgram Aura TTS shares the STT API key; 45 concurrent WSS streams on PAYG
    # vs Cartesia free tier's limit of 2 (which blocked the section-5 burst test).
    tts = DeepgramTTSService(
        api_key=os.getenv("DEEPGRAM_API_KEY"),
        settings=DeepgramTTSService.Settings(
            voice=os.getenv("DEEPGRAM_TTS_VOICE", "aura-2-helena-en"),
        ),
    )

    llm = _create_llm()

    context = LLMContext()
    user_aggregator, assistant_aggregator = LLMContextAggregatorPair(
        context,
        user_params=LLMUserAggregatorParams(vad_analyzer=SileroVADAnalyzer()),
    )

    first_audio_marker = FirstAudioMarker()

    pipeline = Pipeline(
        [
            transport.input(),
            stt,
            user_aggregator,
            llm,
            tts,
            first_audio_marker,
            transport.output(),
            assistant_aggregator,
        ]
    )

    task = PipelineTask(
        pipeline,
        params=PipelineParams(
            enable_metrics=True,
            enable_usage_metrics=True,
        ),
    )

    @transport.event_handler("on_client_connected")
    async def on_client_connected(transport, client):
        _log_event("client_connected", since_process_start=round(time.time() - _T_PROC_START, 3))
        first_audio_marker.mark_connected()
        # Kick off the conversation: the bot greets immediately, which is the
        # "first audio" the caller hears and the metric we optimize for.
        greeting_mode = os.getenv("GREETING_MODE", "llm").lower()
        if greeting_mode == "tts":
            # Direct TTS path (skips LLM). Useful to isolate warm-pool latency.
            await task.queue_frames(
                [
                    TTSSpeakFrame(
                        os.getenv(
                            "TTS_GREETING",
                            "Hello! How can I help you today?",
                        )
                    )
                ]
            )
        else:
            context.add_message(
                {
                    "role": "user",
                    "content": os.getenv(
                        "LLM_GREETING_PROMPT",
                        "Say hello in one short sentence.",
                    ),
                }
            )
            await task.queue_frames([LLMRunFrame()])

    @transport.event_handler("on_client_disconnected")
    async def on_client_disconnected(transport, client):
        logger.info("Client disconnected")
        await task.cancel()

    runner = PipelineRunner(handle_sigint=runner_args.handle_sigint)

    await runner.run(task)


async def bot(runner_args: RunnerArguments):
    """Main bot entry point invoked by the Pipecat runner."""
    transport_params = {
        "websocket": lambda: FastAPIWebsocketParams(
            audio_in_enabled=True,
            audio_out_enabled=True,
            add_wav_header=False,
            serializer=RawAudioServerSerializer(),
        ),
    }

    transport = await create_transport(runner_args, transport_params)

    await run_bot(transport, runner_args)


if __name__ == "__main__":
    from pipecat.runner.run import main

    main()
