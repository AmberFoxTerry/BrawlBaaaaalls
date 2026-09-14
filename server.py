import asyncio
import json
import uuid

from aiohttp import web


# ============================================================
# WEAPONS
# ============================================================

WEAPONS = {

    "pistol": {
        "name": "Pistol",
        "rarity": "Common",

        "damage": 20,
        "fire_rate": 4.0,
        "bullet_speed": 10.0,
        "range": 500,
        "spread": 0
    },

}


# ============================================================
# MATCHMAKING
# ============================================================

waiting_players = []
rooms = {}


def weapon_power(weapon_id):

    weapon = WEAPONS.get(weapon_id)

    if weapon is None:
        return 0

    # Simple power calculation.
    # We can balance this properly later.
    damage = weapon["damage"]
    fire_rate = weapon["fire_rate"]
    bullet_speed = weapon["bullet_speed"]
    weapon_range = weapon["range"]

    return (
        damage * 2
        + fire_rate * 10
        + bullet_speed * 2
        + weapon_range * 0.05
    )


# ============================================================
# PLAYER
# ============================================================

class Player:

    def __init__(self, websocket):

        self.id = str(uuid.uuid4())

        self.websocket = websocket

        self.name = "Player"

        self.equipped_weapon = "pistol"

        self.room = None

        self.x = 0
        self.y = 0

        self.angle = 0

        self.input_x = 0
        self.input_y = 0

        self.shooting = False

        self.alive = True


    @property
    def weapon(self):

        return WEAPONS[self.equipped_weapon]


    @property
    def power(self):

        return weapon_power(
            self.equipped_weapon
        )


# ============================================================
# ROOM
# ============================================================

class Room:

    def __init__(self, player1, player2):

        self.id = str(uuid.uuid4())

        self.players = [
            player1,
            player2
        ]

        player1.room = self
        player2.room = self

        # Spawn positions.
        # Map will replace these later.

        player1.x = -100
        player1.y = 0

        player2.x = 100
        player2.y = 0

        self.started = False
        self.finished = False


# ============================================================
# NETWORK
# ============================================================

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


# ============================================================
# MATCHMAKING
# ============================================================

MATCH_POWER_RANGE = 20


async def matchmaking(player):

    # Remove ourselves from the queue
    if player in waiting_players:
        waiting_players.remove(player)


    best_match = None
    best_difference = None


    for other in waiting_players:

        if other.room is not None:
            continue

        difference = abs(
            player.power -
            other.power
        )

        if difference > MATCH_POWER_RANGE:
            continue

        if (
            best_difference is None
            or difference < best_difference
        ):

            best_match = other
            best_difference = difference


    if best_match is None:

        waiting_players.append(player)

        await send(
            player,
            {
                "type": "waiting"
            }
        )

        return


    waiting_players.remove(best_match)

    await create_room(
        best_match,
        player
    )


# ============================================================
# CREATE ROOM
# ============================================================

async def create_room(player1, player2):

    room = Room(
        player1,
        player2
    )

    rooms[room.id] = room

    room.started = True


    await broadcast(
        room,
        {
            "type": "match_found",

            "room_id": room.id,

            "players": [

                {
                    "id": player.id,
                    "name": player.name,

                    "weapon":
                        player.equipped_weapon,

                    "weapon_power":
                        player.power,

                    "x": player.x,
                    "y": player.y

                }

                for player in room.players

            ]
        }
    )


# ============================================================
# GAME LOOP
# ============================================================

async def game_loop():

    while True:

        for room in list(rooms.values()):

            if room.finished:
                continue


            # ------------------------------------------------
            # MOVEMENT
            # ------------------------------------------------

            for player in room.players:

                if not player.alive:
                    continue

                speed = 4.0

                player.x += (
                    player.input_x *
                    speed
                )

                player.y += (
                    player.input_y *
                    speed
                )


            # ------------------------------------------------
            # STATE
            # ------------------------------------------------

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

                            "angle":
                                player.angle,

                            "alive":
                                player.alive

                        }

                        for player
                        in room.players

                    ]
                }
            )


        await asyncio.sleep(
            1 / 60
        )


# ============================================================
# WEBSOCKET
# ============================================================

async def websocket_handler(request):

    websocket = web.WebSocketResponse()

    await websocket.prepare(request)


    player = Player(websocket)


    # Tell client its ID.

    await send(
        player,
        {
            "type": "connected",

            "player_id":
                player.id
        }
    )


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


            message_type = data.get(
                "type"
            )


            # =================================================
            # PLAYER INFO
            # =================================================

            if message_type == "player_info":

                player.name = data.get(
                    "name",
                    "Player"
                )


                weapon = data.get(
                    "weapon",
                    "pistol"
                )


                # Never trust unknown weapons.

                if weapon in WEAPONS:

                    player.equipped_weapon = weapon


            # =================================================
            # PLAY
            # =================================================

            elif message_type == "play":

                if player.room is None:

                    await matchmaking(
                        player
                    )


            # =================================================
            # INPUT
            # =================================================

            elif message_type == "input":

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

                    angle = float(
                        data.get(
                            "angle",
                            0
                        )
                    )

                    shooting = bool(
                        data.get(
                            "shooting",
                            False
                        )
                    )

                except Exception:

                    continue


                # Clamp movement.

                player.input_x = max(
                    -1,
                    min(1, x)
                )

                player.input_y = max(
                    -1,
                    min(1, y)
                )


                player.angle = angle

                player.shooting = shooting


    finally:

        # ----------------------------------------------------
        # MATCHMAKING QUEUE
        # ----------------------------------------------------

        if player in waiting_players:

            waiting_players.remove(
                player
            )


        # ----------------------------------------------------
        # ROOM
        # ----------------------------------------------------

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

                    other.room = None


            rooms.pop(
                room.id,
                None
            )


    return websocket


# ============================================================
# SERVER START
# ============================================================

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
        "Shooter server running!"
    )


    await game_loop()


# ============================================================
# RUN
# ============================================================

asyncio.run(start())
