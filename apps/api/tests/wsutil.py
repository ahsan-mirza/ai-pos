"""Open a socket and authenticate on the first frame. The URL never carries the credential."""

from collections.abc import Iterator
from contextlib import contextmanager


@contextmanager
def authed(client, path: str, token: str, role: str | None = None, **fields: str) -> Iterator[object]:
    with client.websocket_connect(path) as socket:
        body: dict[str, str] = {"type": "auth", "token": token}
        if role:
            body["role"] = role
        body.update(fields)
        socket.send_json(body)
        yield socket
