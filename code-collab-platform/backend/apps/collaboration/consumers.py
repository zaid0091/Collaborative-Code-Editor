"""WebSocket consumer for Yjs collaboration relay."""

from __future__ import annotations

import asyncio
import base64
import json
import os
import socket
import time
import uuid

import redis.asyncio as aioredis
from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncJsonWebsocketConsumer
from django.conf import settings
from django.contrib.auth.models import AnonymousUser

from apps.collaboration.ws_abuse import WSAbuseGuard
from apps.core.metrics import ws_active_connections, ws_messages_total
from core.logging import log_ws_connect, log_ws_disconnect
from core.middleware import bind_correlation_id


class CollaborationConsumer(AsyncJsonWebsocketConsumer):
    MAX_UPDATE_SIZE_BYTES = 512 * 1024
    MAX_WS_FRAME_BYTES = 512 * 1024
    HEARTBEAT_TIMEOUT_SEC = 75
    TOKEN_EXPIRY_WARN_SEC = 300

    _redis_override = None
    DRAIN_MESSAGE = "Server restarting. Please reconnect."

    async def _check_node_draining(self) -> bool:
        """
        Called on connect. If node is marked draining,
        immediately send drain notice and close.
        """
        node_id = os.environ.get("NODE_ID", socket.gethostname())
        redis_client = await self.get_redis()
        is_draining = await redis_client.exists(f"node:{node_id}:draining")
        if is_draining:
            await self.accept()
            await self.send_json(
                {
                    "type": "server_draining",
                    "message": self.DRAIN_MESSAGE,
                }
            )
            await self.close(code=4010)
            return True
        return False

    async def connect(self):
        self.file_id = self.scope["url_route"]["kwargs"]["file_id"]
        self.user = self.scope.get("user")
        self.session_id = str(uuid.uuid4())
        self.group_name = f"file_{self.file_id}"
        self.last_ping = time.monotonic()
        self._connected = False
        self._token_expiring_notified = False

        if await self._check_node_draining():
            return

        if not self.user or isinstance(self.user, AnonymousUser):
            await self.close(code=4001)
            return

        redis_client = await self.get_redis()
        self.abuse_guard = WSAbuseGuard(redis_client)

        # SECURITY: ws:ban:{user_id} Redis ban check — close 4003 before joining group.
        if await self.abuse_guard.is_banned(str(self.user.id)):
            from apps.core.metrics import ws_abuse_disconnects_total

            ws_abuse_disconnects_total.labels("banned").inc()
            await self.close(code=4003)
            return

        # SECURITY: WorkspaceMember must exist and file must belong to that workspace.
        has_access = await self.check_file_access(self.file_id, self.user)
        if not has_access:
            await self.close(code=4001)
            return

        await self.redis_connect()
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()

        self._connected = True
        self.connected_at = time.monotonic()

        bind_correlation_id(self.session_id)

        version = await self.get_current_version()
        await self.send_json({"type": "server_version", "version": version})

        log_ws_connect(
            user_id=self.user.id,
            file_id=self.file_id,
            session_id=self.session_id,
            node_id=socket.gethostname(),
        )
        ws_active_connections.labels("aggregate").inc()

        self._heartbeat_task = asyncio.ensure_future(self.heartbeat_monitor())
        asyncio.create_task(self._broadcast_user_joined())
        await self._maybe_warn_token_expiry()

    async def receive(self, text_data=None, bytes_data=None, **kwargs):
        frame_size = len(bytes_data) if bytes_data is not None else len(text_data or "")
        # SECURITY: reject oversized raw WebSocket frames before JSON parsing.
        if frame_size > self.MAX_WS_FRAME_BYTES:
            await self.close(code=1009)
            return
        await super().receive(text_data=text_data, bytes_data=bytes_data, **kwargs)

    async def _maybe_warn_token_expiry(self):
        exp = self.scope.get("jwt_exp")
        if not exp or self._token_expiring_notified:
            return
        if exp - time.time() < self.TOKEN_EXPIRY_WARN_SEC:
            self._token_expiring_notified = True
            await self.send_json({"type": "token_expiring_soon"})

    async def heartbeat_monitor(self):
        while True:
            await asyncio.sleep(25)
            elapsed = time.monotonic() - self.last_ping
            if elapsed > self.HEARTBEAT_TIMEOUT_SEC:
                await self.close(code=4002)
                return

    async def _broadcast_user_joined(self):
        await self.channel_layer.group_send(
            self.group_name,
            {
                "type": "broadcast.user_joined",
                "user_id": str(self.user.id),
                "display_name": self.user.display_name,
                "session_id": self.session_id,
            },
        )

    async def disconnect(self, close_code):
        if hasattr(self, "_heartbeat_task"):
            self._heartbeat_task.cancel()

        if not getattr(self, "_connected", False):
            return

        duration_sec = round(time.monotonic() - getattr(self, "connected_at", time.monotonic()), 2)
        log_ws_disconnect(
            user_id=self.user.id,
            file_id=self.file_id,
            session_id=self.session_id,
            reason=str(close_code),
            duration_sec=duration_sec,
        )
        ws_active_connections.labels("aggregate").dec()

        await self.redis_disconnect()
        await self.channel_layer.group_discard(self.group_name, self.channel_name)
        await self.channel_layer.group_send(
            self.group_name,
            {
                "type": "broadcast.user_left",
                "user_id": str(self.user.id),
                "session_id": self.session_id,
            },
        )

        editors_remaining = await self.get_editor_count()
        if editors_remaining == 0:
            from tasks.persist_updates import idle_compact

            idle_compact.apply_async(
                args=[self.file_id],
                queue="crdt.persist",
                countdown=30,
            )

    async def receive_json(self, content, **kwargs):
        # SECURITY: rate-limit / abuse guard runs before any other message handling.
        result = await self.abuse_guard.check(
            self.session_id,
            str(self.user.id),
            content.get("type", "unknown"),
        )

        if result == "disconnect":
            await self.abuse_guard.record_violation(
                str(self.user.id),
                self.session_id,
                "message_rate_exceeded",
                force_disconnect=True,
            )
            await self.send_json(
                {
                    "type": "error",
                    "code": "rate_limit_exceeded",
                    "message": "Disconnecting: message rate exceeded",
                }
            )
            await self.close(code=1008)
            return

        if result == "warn":
            await self.send_json(
                {
                    "type": "rate_limit_warning",
                    "retry_after_ms": 1000,
                }
            )

        if result == "drop":
            return

        ws_messages_total.labels(content.get("type", "unknown"), "inbound").inc()

        await self.refresh_connection_ttl()
        self.last_ping = time.monotonic()
        await self._maybe_warn_token_expiry()

        msg_type = content.get("type")
        handlers = {
            "ping": self.handle_ping,
            "update": self.handle_update,
            "awareness": self.handle_awareness,
            "cursor": self.handle_cursor,
            "sync_request": self.handle_sync_request,
            "comment_event": self.handle_comment_event,
        }

        handler = handlers.get(msg_type)
        if handler:
            await handler(content)

    async def handle_ping(self, content):
        await self.send_json({"type": "pong"})

    async def handle_update(self, content):
        update_b64 = content.get("update", "")

        try:
            raw = base64.b64decode(update_b64, validate=True)
        except Exception:
            await self.close(code=1007)
            return

        if len(raw) > self.MAX_UPDATE_SIZE_BYTES:
            # SECURITY: oversized Yjs update — drop message and record abuse strike.
            await self.abuse_guard.record_violation(
                str(self.user.id),
                self.session_id,
                "oversized_update",
            )
            return

        new_version = await self.append_to_buffer(update_b64)
        await self.send_json({"type": "ack", "version": new_version})

        await self.channel_layer.group_send(
            self.group_name,
            {
                "type": "broadcast.update",
                "update": update_b64,
                "sender_channel": self.channel_name,
            },
        )

        await self.maybe_schedule_flush()

    async def handle_awareness(self, content):
        await self.channel_layer.group_send(
            self.group_name,
            {
                "type": "broadcast.awareness",
                "data": content.get("data", ""),
                "sender_channel": self.channel_name,
            },
        )

    async def handle_cursor(self, content):
        await self.channel_layer.group_send(
            self.group_name,
            {
                "type": "broadcast.cursor",
                "position": content.get("position", {}),
                "selection": content.get("selection", {}),
                "user_id": str(self.user.id),
                "session_id": self.session_id,
                "sender_channel": self.channel_name,
            },
        )

    async def handle_sync_request(self, content):
        from apps.collaboration.sync_engine import build_sync_response

        response = await build_sync_response(
            self.file_id,
            content.get("last_known_version"),
            content.get("client_state_vector"),
        )
        await self.send_json({"type": "sync_response", **response})
        if "error" not in response:
            await self.send_json(
                {
                    "type": "sync_complete",
                    "server_version": response["server_version"],
                }
            )

    async def handle_comment_event(self, content):
        payload = content.get("payload", content)
        await self.channel_layer.group_send(
            self.group_name,
            {
                "type": "broadcast.comment_event",
                "payload": payload,
                "sender_channel": self.channel_name,
            },
        )

    async def broadcast_update(self, event):
        if event.get("sender_channel") != self.channel_name:
            await self.send_json({"type": "update", "update": event["update"]})

    async def broadcast_awareness(self, event):
        if event.get("sender_channel") != self.channel_name:
            await self.send_json({"type": "awareness", "data": event["data"]})

    async def broadcast_cursor(self, event):
        if event.get("sender_channel") != self.channel_name:
            await self.send_json(
                {
                    "type": "cursor",
                    "position": event["position"],
                    "selection": event["selection"],
                    "user_id": event["user_id"],
                    "session_id": event["session_id"],
                }
            )

    async def broadcast_user_joined(self, event):
        await self.send_json(
            {
                "type": "user_joined",
                "user_id": event["user_id"],
                "display_name": event["display_name"],
                "session_id": event["session_id"],
            }
        )

    async def broadcast_user_left(self, event):
        await self.send_json(
            {
                "type": "user_left",
                "user_id": event["user_id"],
                "session_id": event["session_id"],
            }
        )

    async def broadcast_server_draining(self, event):
        await self.send_json(
            {
                "type": "server_draining",
                "message": event.get("message", self.DRAIN_MESSAGE),
            }
        )
        await self.close(code=4010)

    async def broadcast_comment_event(self, event):
        if event.get("sender_channel") == self.channel_name:
            return
        await self.send_json(event.get("payload", event))

    async def redis_connect(self):
        redis_client = await self.get_redis()
        await redis_client.sadd(f"file:{self.file_id}:editors", str(self.user.id))
        await redis_client.set(
            f"file:{self.file_id}:conn:{self.session_id}",
            json.dumps(
                {
                    "user_id": str(self.user.id),
                    "connected_at": str(time.monotonic()),
                }
            ),
            ex=90,
        )
        if not await redis_client.exists(f"file:{self.file_id}:version"):
            await redis_client.set(f"file:{self.file_id}:version", 0)

    async def redis_disconnect(self):
        redis_client = await self.get_redis()
        await redis_client.srem(f"file:{self.file_id}:editors", str(self.user.id))
        await redis_client.delete(f"file:{self.file_id}:conn:{self.session_id}")

    async def refresh_connection_ttl(self):
        redis_client = await self.get_redis()
        await redis_client.expire(f"file:{self.file_id}:conn:{self.session_id}", 90)

    async def get_current_version(self) -> int:
        redis_client = await self.get_redis()
        value = await redis_client.get(f"file:{self.file_id}:version")
        return int(value) if value else 0

    async def get_editor_count(self) -> int:
        redis_client = await self.get_redis()
        return await redis_client.scard(f"file:{self.file_id}:editors")

    async def append_to_buffer(self, update_b64: str) -> int:
        redis_client = await self.get_redis()
        pipe = redis_client.pipeline()
        pipe.rpush(f"file:{self.file_id}:updates", update_b64)
        pipe.incr(f"file:{self.file_id}:op_count")
        pipe.incr(f"file:{self.file_id}:version")
        results = await pipe.execute()
        return int(results[2])

    async def maybe_schedule_flush(self):
        redis_client = await self.get_redis()
        flush_interval = settings.YJS_FLUSH_INTERVAL_SEC
        flush_threshold = settings.YJS_FLUSH_OP_THRESHOLD

        op_count = int(await redis_client.get(f"file:{self.file_id}:op_count") or 0)
        already_scheduled = await redis_client.exists(f"file:{self.file_id}:flush_scheduled")

        if not already_scheduled or op_count >= flush_threshold:
            await redis_client.set(
                f"file:{self.file_id}:flush_scheduled",
                1,
                ex=flush_interval,
            )
            from tasks.persist_updates import flush_operations_to_db

            flush_operations_to_db.apply_async(
                args=[self.file_id],
                queue="crdt.persist",
            )

    @staticmethod
    async def get_redis():
        if CollaborationConsumer._redis_override is not None:
            return CollaborationConsumer._redis_override

        return aioredis.from_url(settings.REDIS_URL, decode_responses=True)

    @database_sync_to_async
    def check_file_access(self, file_id, user) -> bool:
        from apps.files.models import File
        from apps.workspaces.models import WorkspaceMember

        try:
            file_obj = File.objects.select_related("project__workspace").get(id=file_id)
        except File.DoesNotExist:
            return False

        return WorkspaceMember.objects.filter(
            workspace=file_obj.project.workspace,
            user=user,
        ).exists()
