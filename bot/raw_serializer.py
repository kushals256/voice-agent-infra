"""A minimal frame serializer for the plain WebSocket transport.

The stock Pipecat WebSocket transport requires a serializer; if it is ``None``
nothing is ever written to the socket (see ``FastAPIWebsocketOutputTransport.
_write_frame``). We only need one direction for the cold-start benchmark: the
bot speaks a greeting on connect and we time the first audio the caller hears.

So this serializer:

- ``serialize``: emits the raw PCM bytes of any output audio frame and drops
  everything else. Because the client wrapper sends ``bytes`` as a binary
  WebSocket message, the harness can treat "first binary message" as
  "first audio out" with zero decoding.
- ``deserialize``: ignores anything the client sends (the harness never needs
  to send real microphone audio to trigger the greeting).
"""

from pipecat.frames.frames import Frame, OutputAudioRawFrame
from pipecat.serializers.base_serializer import FrameSerializer


class RawAudioServerSerializer(FrameSerializer):
    """Emit output audio as raw PCM binary; ignore inbound messages."""

    async def serialize(self, frame: Frame) -> str | bytes | None:
        if isinstance(frame, OutputAudioRawFrame):
            return bytes(frame.audio)
        return None

    async def deserialize(self, data: str | bytes) -> Frame | None:
        return None
