from __future__ import annotations

import os
from dataclasses import dataclass
from environs import Env


@dataclass
class TariffConfig:
    sub_price_kop: int
    sub_duration_days: int
    autorenew_enabled: bool
    notify_days_before: int


@dataclass
class TgBot:
    token: str
    admin_ids: list[int]
    channel_id: str
    support_chat_id: str


@dataclass
class WebConfig:
    url: str
    verification_token: str


@dataclass
class Config:
    tg_bot: TgBot
    tariff: TariffConfig


def _env_bool(name: str, default: bool) -> bool:
    v = os.getenv(name)
    if v is None:
        return default
    return v.strip().lower() in ("1", "true", "yes", "on")


def load_config(path: str | None = None) -> Config:
    env = Env()
    env.read_env(path)

    return Config(
        tg_bot=TgBot(
            token=env("BOTV_TOKEN"),
            admin_ids=env.list("ADMIN_IDS", subcast=int),
            channel_id=env("CHANNEL_ID"),
            support_chat_id=env("GROUP_ID"),
        ),
        tariff=TariffConfig(
            sub_price_kop=int(env("SUB_PRICE_RUB", "299")) * 100,
            sub_duration_days=int(env("SUB_DURATION_DAYS", "30")),
            autorenew_enabled=_env_bool("SUB_AUTORENEW_ENABLED", True),
            notify_days_before=int(env("SUB_NOTIFY_DAYS_BEFORE", "3")),
        ),
    )
