"""Capabilities that administrators can grant to individual accounts."""

PERMISSIONS = {
    "games.create": {
        "label": "Create games",
        "description": "Add new games to the collection.",
    },
    "games.edit": {
        "label": "Edit games",
        "description": "Change information for existing games.",
    },
    "games.delete": {
        "label": "Delete games",
        "description": "Delete individual games from the collection.",
    },
    "users.edit_profile": {
        "label": "Edit user information",
        "description": "Change profile information and favorites for any account.",
    },
}

ALL_PERMISSIONS = tuple(PERMISSIONS)
