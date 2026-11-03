from __future__ import annotations

import asyncio
import json
import random
import secrets
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

from aiohttp import WSMsgType, web


STARTING_CHIPS = 100
ANTE = 1
MAX_BET = 5
MAX_ACTIONS = 12
RANK_NAMES = {11: "J", 12: "Q", 13: "K", 14: "A"}
SUITS = ["♠", "♥", "♦", "♣"]


class Phase(str, Enum):
    WAITING = "waiting"
    PLAYING = "playing"
    ROUND_END = "round_end"


@dataclass
class Player:
    id: str
    name: str
    ws: web.WebSocketResponse
    ready: bool = False
    chips: int = STARTING_CHIPS
    hand: list[tuple[int, str]] = field(default_factory=list)
    folded: bool = False
    action_count: int = 0
    again: bool = False


@dataclass
class Room:
    id: str
    players: list[Player] = field(default_factory=list)
    phase: Phase = Phase.WAITING
    pot: int = 0
    current_bet: int = ANTE
    turn_index: int = 0
    total_actions: int = 0
    winner_id: str | None = None
    end_reason: str | None = None
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)


ROOMS: dict[str, Room] = {}
PLAYER_ROOM: dict[str, str] = {}
WS_PLAYER: dict[web.WebSocketResponse, str] = {}


def clean_name(name: Any) -> str:
    text = str(name or "").strip()
    return text[:12] or f"玩家{secrets.token_hex(2).upper()}"


def new_room_id() -> str:
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    while True:
        room_id = "".join(secrets.choice(alphabet) for _ in range(4))
        if room_id not in ROOMS:
            return room_id


def make_deck() -> list[tuple[int, str]]:
    return [(rank, suit) for suit in SUITS for rank in range(2, 15)]


def format_card(card: tuple[int, str]) -> str:
    rank, suit = card
    return f"{RANK_NAMES.get(rank, str(rank))}{suit}"


def straight_high(ranks: list[int]) -> int | None:
    unique = sorted(set(ranks))
    if len(unique) != 3:
        return None
    if unique == [2, 3, 14]:
        return 3
    if unique[0] + 1 == unique[1] and unique[1] + 1 == unique[2]:
        return unique[2]
    return None


def evaluate_hand(hand: list[tuple[int, str]]) -> tuple[int, tuple[int, ...], str]:
    ranks = sorted((rank for rank, _ in hand), reverse=True)
    suits = [suit for _, suit in hand]
    counts = {rank: ranks.count(rank) for rank in set(ranks)}
    flush = len(set(suits)) == 1
    high = straight_high(ranks)

    if 3 in counts.values():
        triple_rank = next(rank for rank, count in counts.items() if count == 3)
        return 5, (triple_rank,), "豹子"
    if flush and high is not None:
        return 4, (high,), "同花顺"
    if flush:
        return 3, tuple(ranks), "同花"
    if high is not None:
        return 2, (high,), "顺子"
    if 2 in counts.values():
        pair_rank = next(rank for rank, count in counts.items() if count == 2)
        kicker = next(rank for rank, count in counts.items() if count == 1)
        return 1, (pair_rank, kicker), "对子"
    return 0, tuple(ranks), "散牌"


def compare_hands(hand_a: list[tuple[int, str]], hand_b: list[tuple[int, str]]) -> int:
    score_a = evaluate_hand(hand_a)[:2]
    score_b = evaluate_hand(hand_b)[:2]
    if score_a > score_b:
        return 1
    if score_a < score_b:
        return -1
    return 0


def find_player(player_id: str) -> tuple[Room, Player] | tuple[None, None]:
    room_id = PLAYER_ROOM.get(player_id)
    if not room_id:
        return None, None
    room = ROOMS.get(room_id)
    if not room:
        return None, None
    player = next((p for p in room.players if p.id == player_id), None)
    if not player:
        return None, None
    return room, player


def other_player(room: Room, player: Player) -> Player | None:
    return next((p for p in room.players if p.id != player.id), None)


def player_summary(room: Room, player: Player, viewer: Player) -> dict[str, Any]:
    reveal = room.phase == Phase.ROUND_END or player.id == viewer.id
    cards = [format_card(card) for card in player.hand] if reveal and player.hand else None
    hand_name = evaluate_hand(player.hand)[2] if room.phase == Phase.ROUND_END and player.hand else None
    return {
        "id": player.id,
        "name": player.name,
        "ready": player.ready,
        "chips": player.chips,
        "folded": player.folded,
        "action_count": player.action_count,
        "again": player.again,
        "cards": cards,
        "hand_name": hand_name,
    }


def serialize_room(room: Room, viewer: Player) -> dict[str, Any]:
    can_compare = (
        room.phase == Phase.PLAYING
        and len(room.players) == 2
        and all(p.action_count >= 1 for p in room.players)
    )
    turn_player_id = None
    turn_player_name = None
    if room.phase == Phase.PLAYING and len(room.players) == 2:
        turn = room.players[room.turn_index]
        turn_player_id = turn.id
        turn_player_name = turn.name

    return {
        "room_id": room.id,
        "phase": room.phase.value,
        "you": viewer.id,
        "pot": room.pot,
        "current_bet": room.current_bet,
        "round": min(6, room.total_actions // 2 + 1) if room.phase == Phase.PLAYING else 0,
        "max_rounds": 6,
        "can_compare": can_compare,
        "turn_player_id": turn_player_id,
        "turn_player_name": turn_player_name,
        "players": [player_summary(room, p, viewer) for p in room.players],
        "winner_id": room.winner_id,
        "end_reason": room.end_reason,
    }


async def safe_send(ws: web.WebSocketResponse, payload: dict[str, Any]) -> None:
    if not ws.closed:
        await ws.send_json(payload)


async def send_error(ws: web.WebSocketResponse, message: str) -> None:
    await safe_send(ws, {"type": "error", "message": message})


async def broadcast_state(room: Room) -> None:
    for player in list(room.players):
        await safe_send(player.ws, {"type": "state", "state": serialize_room(room, player)})


def reset_waiting_player(player: Player) -> None:
    player.ready = False
    player.hand.clear()
    player.folded = False
    player.action_count = 0
    player.again = False


def remove_player(room: Room, player: Player) -> None:
    if player in room.players:
        room.players.remove(player)
    PLAYER_ROOM.pop(player.id, None)
    WS_PLAYER.pop(player.ws, None)


def start_round(room: Room) -> None:
    deck = make_deck()
    random.shuffle(deck)

    room.phase = Phase.PLAYING
    room.pot = 0
    room.current_bet = ANTE
    room.total_actions = 0
    room.winner_id = None
    room.end_reason = None
    room.turn_index = random.randrange(2)

    for player in room.players:
        player.ready = True
        player.folded = False
        player.action_count = 0
        player.again = False
        player.hand = [deck.pop(), deck.pop(), deck.pop()]
        player.chips -= ANTE
        room.pot += ANTE


def award_pot_to(room: Room, player: Player) -> None:
    player.chips += room.pot
    room.pot = 0


def split_pot(room: Room) -> None:
    share, remainder = divmod(room.pot, len(room.players))
    for index, player in enumerate(room.players):
        player.chips += share + (1 if index < remainder else 0)
    room.pot = 0


def finish_round(room: Room, reason: str, actor: Player | None = None, winner: Player | None = None) -> None:
    if winner:
        room.winner_id = winner.id
        award_pot_to(room, winner)
    else:
        result = compare_hands(room.players[0].hand, room.players[1].hand)
        if result > 0:
            room.winner_id = room.players[0].id
            award_pot_to(room, room.players[0])
        elif result < 0:
            room.winner_id = room.players[1].id
            award_pot_to(room, room.players[1])
        elif reason == "compare" and actor:
            loser = actor
            winner_player = other_player(room, loser)
            if winner_player:
                room.winner_id = winner_player.id
                award_pot_to(room, winner_player)
        else:
            room.winner_id = None
            split_pot(room)

    room.phase = Phase.ROUND_END
    room.end_reason = reason
    for player in room.players:
        player.again = False


def require_chips(player: Player, amount: int) -> bool:
    return amount >= 0 and player.chips >= amount


def advance_turn(room: Room) -> None:
    room.turn_index = 1 - room.turn_index


async def handle_create(ws: web.WebSocketResponse, data: dict[str, Any]) -> None:
    if ws in WS_PLAYER:
        await send_error(ws, "你已经在一个房间中")
        return
    room = Room(id=new_room_id())
    player = Player(id=secrets.token_urlsafe(12), name=clean_name(data.get("name")), ws=ws)
    room.players.append(player)
    ROOMS[room.id] = room
    PLAYER_ROOM[player.id] = room.id
    WS_PLAYER[ws] = player.id
    await safe_send(ws, {"type": "joined", "room_id": room.id, "player_id": player.id})
    await broadcast_state(room)


async def handle_join(ws: web.WebSocketResponse, data: dict[str, Any]) -> None:
    if ws in WS_PLAYER:
        await send_error(ws, "你已经在一个房间中")
        return
    room_id = str(data.get("room_id", "")).strip().upper()
    room = ROOMS.get(room_id)
    if not room:
        await send_error(ws, "房间不存在")
        return
    async with room.lock:
        if room.phase != Phase.WAITING:
            await send_error(ws, "游戏已经开始，不能加入")
            return
        if len(room.players) >= 2:
            await send_error(ws, "房间已满")
            return
        player = Player(id=secrets.token_urlsafe(12), name=clean_name(data.get("name")), ws=ws)
        room.players.append(player)
        PLAYER_ROOM[player.id] = room.id
        WS_PLAYER[ws] = player.id
        for p in room.players:
            p.ready = False
        await safe_send(ws, {"type": "joined", "room_id": room.id, "player_id": player.id})
        await broadcast_state(room)


async def handle_ready(player: Player, room: Room) -> None:
    if room.phase != Phase.WAITING:
        await send_error(player.ws, "当前不能准备")
        return
    player.ready = True
    if len(room.players) == 2 and all(p.ready for p in room.players):
        if any(p.chips < ANTE for p in room.players):
            await send_error(player.ws, "筹码不足，无法开始")
        else:
            start_round(room)
    await broadcast_state(room)


async def handle_leave(player: Player, room: Room) -> None:
    if room.phase != Phase.WAITING:
        await send_error(player.ws, "游戏开始后不能主动退出房间")
        return
    remove_player(room, player)
    await safe_send(player.ws, {"type": "left"})
    if not room.players:
        ROOMS.pop(room.id, None)
        return
    for p in room.players:
        reset_waiting_player(p)
    await broadcast_state(room)


async def handle_action(player: Player, room: Room, data: dict[str, Any]) -> None:
    if room.phase != Phase.PLAYING:
        await send_error(player.ws, "当前不在游戏中")
        return
    if len(room.players) != 2:
        await send_error(player.ws, "需要两名玩家才能行动")
        return
    if room.players[room.turn_index].id != player.id:
        await send_error(player.ws, "还没轮到你")
        return
    if player.folded:
        await send_error(player.ws, "你已经弃牌")
        return

    move = data.get("move")
    if move == "call":
        amount = room.current_bet
        if not require_chips(player, amount):
            await send_error(player.ws, "筹码不足，无法跟注")
            return
        player.chips -= amount
        room.pot += amount
        player.action_count += 1
        room.total_actions += 1
        if room.total_actions >= MAX_ACTIONS:
            finish_round(room, "showdown")
        else:
            advance_turn(room)

    elif move == "raise":
        try:
            amount = int(data.get("amount"))
        except (TypeError, ValueError):
            await send_error(player.ws, "加注金额必须是数字")
            return
        if amount <= room.current_bet:
            await send_error(player.ws, "加注必须高于当前注额")
            return
        if amount > MAX_BET:
            await send_error(player.ws, "当前注额最高只能加到 5")
            return
        if not require_chips(player, amount):
            await send_error(player.ws, "筹码不足，无法加注")
            return
        player.chips -= amount
        room.pot += amount
        room.current_bet = amount
        player.action_count += 1
        room.total_actions += 1
        if room.total_actions >= MAX_ACTIONS:
            finish_round(room, "showdown")
        else:
            advance_turn(room)

    elif move == "fold":
        player.folded = True
        winner = other_player(room, player)
        if winner:
            finish_round(room, "fold", winner=winner)

    elif move == "compare":
        if not all(p.action_count >= 1 for p in room.players):
            await send_error(player.ws, "双方至少各行动一次后才能比牌")
            return
        amount = room.current_bet
        if not require_chips(player, amount):
            await send_error(player.ws, "筹码不足，无法比牌")
            return
        player.chips -= amount
        room.pot += amount
        finish_round(room, "compare", actor=player)

    else:
        await send_error(player.ws, "未知行动")
        return

    await broadcast_state(room)


async def handle_again(player: Player, room: Room) -> None:
    if room.phase != Phase.ROUND_END:
        await send_error(player.ws, "当前不能再来一局")
        return
    player.again = True
    if len(room.players) == 2 and all(p.again for p in room.players):
        if any(p.chips < ANTE for p in room.players):
            for p in room.players:
                p.ready = False
                p.again = False
            room.phase = Phase.WAITING
            room.winner_id = None
            room.end_reason = None
            await send_error(player.ws, "有玩家筹码不足，已回到等待房间")
        else:
            start_round(room)
    await broadcast_state(room)


async def handle_message(ws: web.WebSocketResponse, data: dict[str, Any]) -> None:
    msg_type = data.get("type")
    if msg_type == "create":
        await handle_create(ws, data)
        return
    if msg_type == "join":
        await handle_join(ws, data)
        return

    player_id = WS_PLAYER.get(ws)
    if not player_id:
        await send_error(ws, "请先创建或加入房间")
        return
    room, player = find_player(player_id)
    if not room or not player:
        await send_error(ws, "房间状态异常，请刷新页面")
        return

    async with room.lock:
        if msg_type == "ready":
            await handle_ready(player, room)
        elif msg_type == "leave":
            await handle_leave(player, room)
        elif msg_type == "action":
            await handle_action(player, room, data)
        elif msg_type == "again":
            await handle_again(player, room)
        else:
            await send_error(ws, "未知操作")


async def handle_disconnect(ws: web.WebSocketResponse) -> None:
    player_id = WS_PLAYER.get(ws)
    if not player_id:
        return
    room, player = find_player(player_id)
    if not room or not player:
        WS_PLAYER.pop(ws, None)
        return

    async with room.lock:
        if room.phase == Phase.PLAYING and len(room.players) == 2:
            winner = other_player(room, player)
            if winner:
                finish_round(room, "disconnect", winner=winner)
            remove_player(room, player)
            if room.players:
                await broadcast_state(room)
            else:
                ROOMS.pop(room.id, None)
        elif room.phase == Phase.ROUND_END:
            remove_player(room, player)
            if room.players:
                survivor = room.players[0]
                reset_waiting_player(survivor)
                room.phase = Phase.WAITING
                room.pot = 0
                room.current_bet = ANTE
                room.total_actions = 0
                room.winner_id = None
                room.end_reason = None
                await broadcast_state(room)
            else:
                ROOMS.pop(room.id, None)
        else:
            remove_player(room, player)
            if room.players:
                for p in room.players:
                    reset_waiting_player(p)
                await broadcast_state(room)
            else:
                ROOMS.pop(room.id, None)


async def index(_: web.Request) -> web.FileResponse:
    return web.FileResponse(Path(__file__).with_name("index.html"))


async def websocket_handler(request: web.Request) -> web.WebSocketResponse:
    ws = web.WebSocketResponse(heartbeat=20)
    await ws.prepare(request)

    try:
        async for msg in ws:
            if msg.type == WSMsgType.TEXT:
                try:
                    data = json.loads(msg.data)
                except json.JSONDecodeError:
                    await send_error(ws, "消息格式错误")
                    continue
                if not isinstance(data, dict):
                    await send_error(ws, "消息格式错误")
                    continue
                await handle_message(ws, data)
            elif msg.type == WSMsgType.ERROR:
                break
    finally:
        await handle_disconnect(ws)

    return ws


def create_app() -> web.Application:
    app = web.Application()
    app.router.add_get("/", index)
    app.router.add_get("/ws", websocket_handler)
    return app


if __name__ == "__main__":
    web.run_app(create_app(), host="127.0.0.1", port=8000)
