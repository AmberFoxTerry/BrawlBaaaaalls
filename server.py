import asyncio
import json
import random
import uuid

from aiohttp import web


waiting_player = None
rooms = {}


COLORS = [
    "#ff4444",
    "#44aaff",
    "#44ff77",
    "#ff44dd",
    "#ffaa22",
    "#aa66ff"
]


class Player:

    def __init__(self, websocket):

        self.id = str(uuid.uuid4())

        self.websocket = websocket

        self.room = None

        self.name = "Player"

        self.color = random.choice(COLORS)

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

        # TOP-DOWN ARENA
        #
        # Player 1 = bottom
        # Player 2 = top

        p1.x = 0
        p1.y = 170

        p2.x = 0
        p2.y = -170

        while p2.color == p1.color:
            p2.color = random.choice(COLORS)

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
                    "color": p1.color,
                    "x": p1.x,
                    "y": p1.y
                },

                {
                    "id": p2.id,
                    "name": p2.name,
                    "color": p2.color,
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

                # Friction

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


            BALL_DIAMETER = 70


            if (
                distance > 0
                and distance < BALL_DIAMETER
            ):

                nx = dx / distance
                ny = dy / distance

                overlap = (
                    BALL_DIAMETER -
                    distance
                )


                # Push balls apart

                p1.x -= nx * overlap / 2
                p1.y -= ny * overlap / 2

                p2.x += nx * overlap / 2
                p2.y += ny * overlap / 2


                # Bounce / push force

                push = 3.5


                p1.vx -= nx * push
                p1.vy -= ny * push

                p2.vx += nx * push
                p2.vy += ny * push


            # =========================
            # PLATFORM EDGE
            # =========================

            PLATFORM_RADIUS = 300

            BALL_RADIUS = 35


            for player in room.players:

                distance = (
                    player.x ** 2 +
                    player.y ** 2
                ) ** 0.5


                # Ball has fallen

                if distance > (
                    PLATFORM_RADIUS +
                    BALL_RADIUS
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
            # SEND GAME STATE
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


            data = json.loads(
                message.data
            )


            # =========================
            # PLAYER INFO
            # =========================

            if data["type"] == "player_info":

                player.name = data.get(
                    "name",
                    "Player"
                )


            # =========================
            # PLAY
            # =========================

            elif data["type"] == "play":

                await matchmaking(
                    player
                )


            # =========================
            # MOVEMENT
            # =========================

            elif data["type"] == "input":

                if player.room is None:
                    continue


                x = float(
                    data.get("x", 0)
                )

                y = float(
                    data.get("y", 0)
                )


                SPEED = 0.7


                player.vx += x * SPEED
                player.vy += y * SPEED


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
