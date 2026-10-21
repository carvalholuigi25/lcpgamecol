import enum

from pydantic import BaseModel


class AchievementStatus(str, enum.Enum):
    LOCKED = "Locked"
    UNLOCKED = "Unlocked"

class AchievementType(str, enum.Enum):
    PLATINUM = "Platinum"
    GOLD = "Gold"
    SILVER = "Silver"
    BRONZE = "Bronze"

class AchievementCreate(BaseModel):
    title: str
    description: str | None = None
    image_url: str | None = None
    points: int | None = None
    unlocked: bool = False
    date_unlocked: str | None = None
    status: AchievementStatus = AchievementStatus.LOCKED
    achievement_type: AchievementType = AchievementType.BRONZE


class Achievement(AchievementCreate):
    achievement_id: int
    game_id: int