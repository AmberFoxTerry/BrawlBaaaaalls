import asyncio
import json
import uuid

from aiohttp import web


waiting_player = None
rooms = {}


BALLS = {
    "normal": {
        "speed": 0.45,
        "push": 8.0,
        "radius": 35
    },

    "bowling": {
        "speed": 0.20,
        "push": 10.0,
        "radius": 45
    },

    "pingpong": {
        "speed": 0.60,
        "push": 0.6,
        "radius": 25
    }
}


class Player:

    def __init__(self, websocket):

        self.id = str(uuid.uuid4())

        self.websocket = websocket

        self.room = None

        self.name = "Player"

        self.ball_type = "normal"

        self.x = 0
        self.y = 0

        self.vx = 0
        self.vy = 0

        self.alive = True


class Room:

    def __init__(self, p1, p2):

        self.id = str(uuid.uuid4())

        self.players = [p1, p2]

        p1.room = self
        p2.room = self

        # Player 1 = bottom
        p1.x = 0
        p1.y = 170

        # Player 2 = top
        p2.x = 0
        p2.y = -170

        self.finished = False


async def send(player, data):

    try:

        await player.websocket.send_str(
            json.dumps(data)
        )

    except Exception:

        pass


async def broadcast(room, data):

    await asyncio.gather(
        *[
            send(player, data)
            for player in room.players
        ]
    )


async def make_match(p1, p2):

    room = Room(p1, p2)

    rooms[room.id] = room

    await broadcast(
        room,
        {
            "type": "match_found",

            "players": [

                {
                    "id": p1.id,
                    "name": p1.name,
                    "ball": p1.ball_type,
                    "x": p1.x,
                    "y": p1.y
                },

                {
                    "id": p2.id,
                    "name": p2.name,
                    "ball": p2.ball_type,
                    "x": p2.x,
                    "y": p2.y
                }

            ]
        }
    )


async def matchmaking(player):

    global waiting_player

    if waiting_player is None:

        waiting_player = player

        await send(
            player,
            {
                "type": "waiting"
            }
        )

        return

    other = waiting_player

    waiting_player = None

    await make_match(
        other,
        player
    )


async def game_loop():

    while True:

        for room in list(rooms.values()):

            if room.finished:
                continue

            p1 = room.players[0]
            p2 = room.players[1]

            # =========================
            # MOVEMENT
            # =========================

            for player in room.players:

                player.x += player.vx
                player.y += player.vy

                player.vx *= 0.90
                player.vy *= 0.90

            # =========================
            # BALL COLLISION
            # =========================

            dx = p2.x - p1.x
            dy = p2.y - p1.y

            distance = (
                dx * dx +
                dy * dy
            ) ** 0.5

            r1 = BALLS[
                p1.ball_type
            ]["radius"]

            r2 = BALLS[
                p2.ball_type
            ]["radius"]

            collision_distance = r1 + r2

            if (
                distance > 0
                and distance < collision_distance
            ):

                nx = dx / distance
                ny = dy / distance

                overlap = (
                    collision_distance -
                    distance
                )

                p1.x -= nx * overlap / 2
                p1.y -= ny * overlap / 2

                p2.x += nx * overlap / 2
                p2.y += ny * overlap / 2

                push1 = BALLS[
                    p1.ball_type
                ]["push"]

                push2 = BALLS[
                    p2.ball_type
                ]["push"]

                p1.vx -= nx * push1
                p1.vy -= ny * push1

                p2.vx += nx * push2
                p2.vy += ny * push2

            # =========================
            # PLATFORM
            # =========================

            PLATFORM_RADIUS = 300

            for player in room.players:

                ball_radius = BALLS[
                    player.ball_type
                ]["radius"]

                distance = (
                    player.x ** 2 +
                    player.y ** 2
                ) ** 0.5

                if distance > (
                    PLATFORM_RADIUS -
                    ball_radius
                ):

                    player.alive = False

                    room.finished = True

                    winner = (
                        p2
                        if player == p1
                        else p1
                    )

                    await broadcast(
                        room,
                        {
                            "type": "game_over",

                            "winner":
                                winner.id,

                            "loser":
                                player.id
                        }
                    )

            # =========================
            # GAME STATE
            # =========================

            if not room.finished:

                await broadcast(
                    room,
                    {
                        "type": "state",

                        "players": [

                            {
                                "id":
                                    player.id,

                                "x":
                                    player.x,

                                "y":
                                    player.y,

                                "vx":
                                    player.vx,

                                "vy":
                                    player.vy

                            }

                            for player
                            in room.players

                        ]
                    }
                )

        await asyncio.sleep(
            1 / 60
        )


async def websocket_handler(request):

    websocket = web.WebSocketResponse()

    await websocket.prepare(request)

    player = Player(websocket)

    try:

        async for message in websocket:

            if (
                message.type !=
                web.WSMsgType.TEXT
            ):

                continue

            try:

                data = json.loads(
                    message.data
                )

            except Exception:

                continue

            # =========================
            # PLAYER INFO
            # =========================

            if data.get("type") == "player_info":

                player.name = data.get(
                    "name",
                    "Player"
                )

                requested_ball = data.get(
                    "ball",
                    "normal"
                )

                if requested_ball in BALLS:

                    player.ball_type = (
                        requested_ball
                    )

            # =========================
            # PLAY
            # =========================

            elif data.get("type") == "play":

                await matchmaking(
                    player
                )

            # =========================
            # INPUT
            # =========================

            elif data.get("type") == "input":

                if player.room is None:
                    continue

                try:

                    x = float(
                        data.get(
                            "x",
                            0
                        )
                    )

                    y = float(
                        data.get(
                            "y",
                            0
                        )
                    )

                except Exception:

                    continue

                x = max(
                    -1,
                    min(1, x)
                )

                y = max(
                    -1,
                    min(1, y)
                )

                speed = BALLS[
                    player.ball_type
                ]["speed"]

                player.vx += x * speed
                player.vy += y * speed

    finally:

        global waiting_player

        if waiting_player == player:

            waiting_player = None

        if player.room:

            room = player.room

            for other in room.players:

                if other != player:

                    await send(
                        other,
                        {
                            "type":
                                "opponent_left"
                        }
                    )

            rooms.pop(
                room.id,
                None
            )

    return websocket


async def start():

    app = web.Application()

    app.router.add_get(
        "/ws",
        websocket_handler
    )

    runner = web.AppRunner(app)

    await runner.setup()

    site = web.TCPSite(
        runner,
        "0.0.0.0",
        8080
    )

    await site.start()

    print(
        "Brawl Baaaaalls server running!"
    )

    await game_loop()


asyncio.run(start())
