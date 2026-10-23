import enum
from datetime import datetime

from pydantic import BaseModel, Field, field_serializer, field_validator


class Gameplatforms(str, enum.Enum):
    PC = "PC"
    WINDOWS = "Windows"
    LINUX = "Linux"
    MAC = "MAC"
    STEAMOS = "SteamOS"
    SEGA = "Sega"
    SEGA_GENESIS_MEGA_DRIVE = "Sega Genesis Mega Drive"
    PLAYSTATION = "PlayStation"
    PLAYSTATION_2 = "PlayStation 2"
    PLAYSTATION_3 = "PlayStation 3"
    PLAYSTATION_4 = "PlayStation 4"
    PLAYSTATION_5 = "PlayStation 5"
    PLAYSTATION_PORTABLE = "PlayStation Portable"
    PLAYSTATION_VITA = "PlayStation Vita"
    PLAYSTATION_REMOTE_PLAY = "PlayStation Remote Play"
    XBOX = "Xbox"
    XBOX_360 = "Xbox 360"
    XBOX_ONE = "Xbox One"
    XBOX_SERIES_X = "Xbox Series X"
    XBOX_SERIES_S = "Xbox Series S"
    NINTENDO = "Nintendo"
    NINTENDO_64 = "Nintendo 64"
    NINTENDO_GAMECUBE = "Nintendo GameCube"
    NINTENDO_WII = "Nintendo Wii"
    NINTENDO_WII_U = "Nintendo Wii U"
    NINTENDO_SWITCH = "Nintendo Switch"
    NINTENDO_2DS = "Nintendo 2DS"
    NINTENDO_3DS = "Nintendo 3DS"
    ARCADE = "Arcade"
    ANDROID = "Android"
    IOS = "iOS"
    MOBILE = "Mobile"
    OTHER = "Other"


class GameModes(str, enum.Enum):
    SINGLE_PLAYER = "Single Player"
    MULTIPLAYER = "Multiplayer"
    CO_OP = "Co-op"
    ONLINE = "Online"
    OFFLINE = "Offline"
    ALL = "all"


class GameEdition(str, enum.Enum):
    STANDARD = "Standard"
    DELUXE = "Deluxe"
    COLLECTOR = "Collector's Edition"
    ULTIMATE = "Ultimate Edition"
    GAME_OF_THE_YEAR = "Game of the Year"


class GamesESRB(str, enum.Enum):
    Three = "three"
    Seven = "seven"
    Twelve = "twelve"
    Sixteen = "sixteen"
    Eighteen = "eighteen"
    RP = "rp"
    EC = "ec"
    E = "e"
    E10 = "e10"
    T = "t"
    M = "m"
    AO = "ao"
    CERO_A = "cero_a"
    CERO_B = "cero_b"
    CERO_C = "cero_c"
    CERO_D = "cero_d"
    CERO_Z = "cero_z"
    USK_0 = "usk_0"
    USK_6 = "usk_6"
    USK_12 = "usk_12"
    USK_16 = "usk_16"
    USK_18 = "usk_18"
    GRAC_ALL = "grac_all"
    GRAC_TWELVE = "grac_twelve"
    GRAC_FIFTEEN = "grac_fifteen"
    GRAC_EIGHTEEN = "grac_eighteen"
    GRAC_TESTING = "grac_testing"
    CLASS_IND_L = "class_ind_l"
    CLASS_IND_TEN = "class_ind_ten"
    CLASS_IND_TWELVE = "class_ind_twelve"
    CLASS_IND_FOURTEEN = "class_ind_fourteen"
    CLASS_IND_SIXTEEN = "class_ind_sixteen"
    CLASS_IND_EIGHTEEN = "class_ind_eighteen"
    ACB_G = "acb_g"
    ACB_PG = "acb_pg"
    ACB_M = "acb_m"
    ACB_MA15 = "acb_ma15"
    ACB_R18 = "acb_r18"
    ACB_RC = "acb_rc"


IGDB_AGE_RATING_BY_ID = {
    rating_id: rating
    for rating_id, rating in enumerate(GamesESRB, start=1)
}

class SortOrder(str, enum.Enum):
    ASC = "asc"
    DESC = "desc"


class GameSort(str, enum.Enum):
    """Ways to order library games."""

    ADDED = "added"
    TITLE = "title"
    RELEASE_DATE = "release_date"
    USER_RATING = "user_rating"
    CRITIC_RATING = "critic_rating"
    HOURS_PLAYED = "hours_played"


class ReleaseSort(str, enum.Enum):
    """Ways to order IGDB releases."""

    RELEASE_DATE = "release_date"
    TITLE = "title"
    HYPE = "hype"
    USER_RATING = "user_rating"
    CRITIC_RATING = "critic_rating"


class ModelGamesESRB(BaseModel):
    organization: str | int | None = ""
    rating: str | int | None = ""


class ModelGamesGameModes(BaseModel):
    id: int | None = 0
    name: str | None = ""

class GameCreate(BaseModel):
    title: str
    genre: str
    release_year: int
    release_date: str | None = None
    description: str | None = ""
    cover_image_url: str | None = ""
    image_url: str | None = ""
    screenshot_url: str | None = ""
    developer_name: str | None = ""
    publisher_name: str | None = ""
    website_url: str | None = ""
    trailer_url: str | None = ""
    screenshots: list[str] = Field(default_factory=list)
    platforms: list[Gameplatforms] | str | None = Gameplatforms.PC
    gamemodes: list[ModelGamesGameModes] | list[GameModes] | str | None = GameModes.ALL
    editions: list[GameEdition] | str | None = GameEdition.STANDARD
    user_rating: float | int | None = 0
    critic_rating: float | int | None = 0
    wishlisted: bool | None = False
    hoursplayed: float | int | None = 0
    esrb: GamesESRB | None = Field(
        default=None,
        description="ESRB rating of the game",
        json_schema_extra={
            "example": GamesESRB.E.value,
            "oneOf": [{"const": e.value, "title": e.name, "description": e.value} for e in GamesESRB],
        },
    )
    minimum_system_requirements: str | None = None
    recommended_system_requirements: str | None = None

    @field_validator("esrb", mode="before")
    @classmethod
    def parse_esrb_name(cls, value):
        if isinstance(value, str) and value in GamesESRB.__members__:
            return GamesESRB[value]
        if isinstance(value, str) and value.isdigit():
            return IGDB_AGE_RATING_BY_ID.get(int(value), value)
        if isinstance(value, int):
            return IGDB_AGE_RATING_BY_ID.get(value, value)
        return value

    @field_serializer("esrb", when_used="json")
    def serialize_esrb_name(self, value: GamesESRB | None) -> str | None:
        return value.value if value is not None else None


class Game(GameCreate):
    id: int


class GameReleasePage(BaseModel):
    items: list[Game]
    total: int
    page_size: int


class GamePage(BaseModel):
    items: list[Game]
    total: int
    page_size: int


class GameCover(BaseModel):
    id: int
    title: str
    cover_image_url: str | None = ""
    image_url: str | None = ""

class GameCoverInfo(BaseModel): 
    type: str
    alpha_channel: bool
    animated: bool
    checksum: str
    game: int | str
    game_localization: int | str
    height: int
    image_id: str
    image_type: int
    url: str
    width: int

class GamePlatform(BaseModel):
    alternative_name: str
    checksum: str
    created_at: datetime
    generation: int
    name: str
    platform_family: int
    platform_logo: int
    platform_type: int
    slug: str
    summary: str
    updated_at: datetime
    url: str


class GamePlatformVersionsCompany(BaseModel):
    checksum: str | None = None
    comment: str | None = None
    company: int
    developer: bool
    manufacturer: bool


class GamePlatformVersionsLogos(BaseModel):
    alpha_channel: bool
    animated: bool
    checksum: str | None = None
    height: int
    image_id: str
    url: str | None
    width: int

class GamePlatformVersionsRelDates(BaseModel):
    checksum: str | None = None
    created_at: datetime
    date: str | int | datetime
    date_format: int
    human: str
    m: int
    platform_version: int | None = None
    release_region: int
    updated_at: datetime
    y: int

class GamePlatformVersions(BaseModel):
    checksum: str | None = None
    companies: list[GamePlatformVersionsCompany] | None
    connectivity: str
    cpu: str
    graphics: str
    main_manufacturer: int
    media: str
    memory: str
    name: str
    os: str
    output: str
    platform_logo: GamePlatformVersionsLogos | None
    platform_version_release_dates: list[GamePlatformVersionsRelDates] | None
    slug: str
    summary: str
    url: str | None = None
