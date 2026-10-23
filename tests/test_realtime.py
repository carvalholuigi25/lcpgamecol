import json
import socket
import threading
import time

import pytest
import uvicorn
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

import backend.auth.auth as auth
import backend.database.database as database
from backend.realtime.hub import RECORD_SEPARATOR, hub
from main import app

GAME = {"title": "Hades", "genre": "Roguelike", "platforms": "PC", "release_year": 2020}
HANDSHAKE = json.dumps({"protocol": "json", "version": 1}) + RECORD_SEPARATOR


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(database, "DATABASE_PATH", tmp_path / "test.db")
    auth._login_attempts.clear()
    database.initialize_database()
    with TestClient(app) as test_client:
        app.middleware_stack.app.requests.clear()
        yield test_client


def sign_in(client, username, password):
    response = client.post("/auth/token", data={"username": username, "password": password})
    assert response.status_code == 200
    client.cookies.clear()
    return response.json()["access_token"]


@pytest.fixture()
def admin_token(client):
    return sign_in(client, "admin", "1234")


@pytest.fixture()
def viewer_token(client, monkeypatch):
    monkeypatch.setitem(auth.AUTH_USERS, "viewer", ("viewer-pass", auth.ROLE_VIEWER))
    return sign_in(client, "viewer", "viewer-pass")


def bearer(token):
    return {"Authorization": f"Bearer {token}"}


def negotiate(client, token):
    response = client.post("/hubs/library/negotiate?negotiateVersion=1", headers=bearer(token))
    assert response.status_code == 200
    return response.json()


def read_message(websocket):
    return json.loads(websocket.receive_text().rstrip(RECORD_SEPARATOR))


def connect(client, token):
    connection_token = negotiate(client, token)["connectionToken"]
    websocket = client.websocket_connect(
        f"/hubs/library?id={connection_token}", headers=bearer(token)
    ).__enter__()
    websocket.send_text(HANDSHAKE)
    assert websocket.receive_text() == "{}" + RECORD_SEPARATOR
    return websocket


def test_negotiate_requires_authentication(client):
    assert client.post("/hubs/library/negotiate").status_code == 401


def test_negotiate_describes_the_websocket_transport(client, admin_token):
    body = negotiate(client, admin_token)

    assert body["negotiateVersion"] == 1
    assert body["connectionId"] == body["connectionToken"]
    assert body["availableTransports"] == [{"transport": "WebSockets", "transferFormats": ["Text"]}]


def test_hub_rejects_anonymous_connections(client):
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect("/hubs/library") as websocket:
            websocket.receive_text()


def test_hub_rejects_cookie_connections_from_other_sites(client, admin_token):
    client.cookies.set(auth.AUTH_COOKIE_NAME, admin_token)
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect(
            "/hubs/library", headers={"Origin": "https://evil.example"}
        ) as websocket:
            websocket.receive_text()


def test_connection_token_is_single_use_and_bound_to_the_user(client, admin_token, viewer_token):
    connection_token = negotiate(client, admin_token)["connectionToken"]
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect(
            f"/hubs/library?id={connection_token}", headers=bearer(viewer_token)
        ) as websocket:
            websocket.receive_text()
    # The failed attempt consumed it, so the owner cannot reuse it either.
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect(
            f"/hubs/library?id={connection_token}", headers=bearer(admin_token)
        ) as websocket:
            websocket.receive_text()


def test_hub_rejects_unsupported_protocols(client, admin_token):
    with client.websocket_connect("/hubs/library", headers=bearer(admin_token)) as websocket:
        websocket.send_text(json.dumps({"protocol": "messagepack", "version": 1}) + RECORD_SEPARATOR)
        assert "error" in read_message(websocket)


def test_game_changes_are_pushed_to_connected_clients(client, admin_token):
    websocket = connect(client, admin_token)
    try:
        created = client.post("/games", json=GAME, headers=bearer(admin_token)).json()
        assert read_message(websocket) == {
            "type": 1,
            "target": "gameChanged",
            "arguments": [{"action": "created", "game_id": created["id"], "title": "Hades"}],
        }

        client.post(
            f"/games/{created['id']}/achievements",
            json={"title": "Escape"},
            headers=bearer(admin_token),
        )
        message = read_message(websocket)
        assert message["target"] == "achievementChanged"
        assert message["arguments"][0]["action"] == "created"

        client.delete(f"/games/{created['id']}", headers=bearer(admin_token))
        assert read_message(websocket)["arguments"] == [
            {"action": "deleted", "game_id": created["id"], "title": None}
        ]
    finally:
        websocket.__exit__(None, None, None)


def test_list_changes_only_reach_their_owner(client, admin_token, viewer_token):
    game_id = client.post("/games", json=GAME, headers=bearer(admin_token)).json()["id"]
    admin_socket = connect(client, admin_token)
    viewer_socket = connect(client, viewer_token)
    try:
        client.put(f"/games/{game_id}/wishlist", headers=bearer(viewer_token))
        assert read_message(viewer_socket) == {
            "type": 1,
            "target": "listsChanged",
            "arguments": [{"game_id": game_id, "wishlisted": True, "favorite": False}],
        }

        # Events are delivered in order, so the admin's next message being the game
        # update proves the viewer's list change was not sent to the admin.
        client.put(f"/games/{game_id}", json=GAME, headers=bearer(admin_token))
        assert read_message(admin_socket)["target"] == "gameChanged"
    finally:
        viewer_socket.__exit__(None, None, None)
        admin_socket.__exit__(None, None, None)


def test_invocations_get_an_error_completion(client, admin_token):
    websocket = connect(client, admin_token)
    try:
        websocket.send_text(
            json.dumps({"type": 1, "invocationId": "7", "target": "Anything", "arguments": []})
            + RECORD_SEPARATOR
        )
        message = read_message(websocket)
        assert message["type"] == 3
        assert message["invocationId"] == "7"
        assert message["error"]
    finally:
        websocket.__exit__(None, None, None)


def test_publish_without_connections_is_a_no_op():
    hub.publish("gameChanged", {"action": "created"})


@pytest.fixture()
def live_server(tmp_path, monkeypatch):
    monkeypatch.setattr(database, "DATABASE_PATH", tmp_path / "live.db")
    database.initialize_database()
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.monotonic() + 10
    while not server.started:
        assert time.monotonic() < deadline, "uvicorn did not start"
        time.sleep(0.05)
    app.middleware_stack.app.requests.clear()
    yield f"http://127.0.0.1:{port}"
    server.should_exit = True
    thread.join(timeout=10)


def test_signalrcore_client_receives_game_events(live_server):
    signalrcore = pytest.importorskip("signalrcore.hub_connection_builder")
    import httpx2 as httpx

    token = httpx.post(
        f"{live_server}/auth/token", data={"username": "admin", "password": "1234"}
    ).json()["access_token"]
    received = []
    got_event = threading.Event()
    opened = threading.Event()

    connection = (
        signalrcore.HubConnectionBuilder()
        .with_url(f"{live_server}/hubs/library", options={"access_token_factory": lambda: token})
        .build()
    )
    connection.on_open(opened.set)
    connection.on("gameChanged", lambda arguments: (received.append(arguments), got_event.set()))
    connection.start()
    try:
        assert opened.wait(10), "signalrcore did not finish the handshake"
        created = httpx.post(
            f"{live_server}/games", json=GAME, headers=bearer(token)
        ).json()
        assert got_event.wait(10), "no gameChanged event arrived"
        assert received[0] == [{"action": "created", "game_id": created["id"], "title": "Hades"}]
    finally:
        connection.stop()
