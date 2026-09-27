"""Redis client construction and connectivity check."""

from redis import Redis

from app.core.config import Settings


def create_redis_client(settings: Settings) -> Redis:
    return Redis.from_url(
        settings.redis_url.get_secret_value(),
        socket_connect_timeout=3,
        socket_timeout=3,
        health_check_interval=30,
    )


def ping_redis(client: Redis) -> None:
    if not client.ping():
        raise ConnectionError("Redis did not answer PING")
