import logging as _log
import aiohttp as _ahttp
import resultes_jsonrpc.websockets.types as _rjwt

_LOGGER = _log.getLogger(__name__)


async def start_receiving_messages(
    websocket: _rjwt.ReadWebSocket, message_receiver: _rjwt.MessageReceiver
) -> None:
    _LOGGER.info("Start receiving messages.")

    async for message in websocket:
        if message.type == _ahttp.WSMsgType.TEXT:
            data = message.data
            _LOGGER.debug("Received message: %s.", data)
            await message_receiver.on_message_received(data)
        elif message.type == _ahttp.WSMsgType.ERROR:
            _LOGGER.error(
                "WebSocket connectionw as closed with exception %s.",
                websocket.exception(),
            )
        elif message.type == _ahttp.WSMsgType.CLOSED:
            _LOGGER.info("Websocket connection closed.")
            break
