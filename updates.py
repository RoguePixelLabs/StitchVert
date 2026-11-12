import json
import re
from urllib.request import Request, urlopen

VERSION = "1.0.0"
REPOSITORY = "RoguePixelLabs/StitchVert"
RELEASES_URL = f"https://github.com/{REPOSITORY}/releases"
LATEST_URL = f"https://api.github.com/repos/{REPOSITORY}/releases/latest"


def version_tuple(value):
    if not isinstance(value, str) or not re.fullmatch(r"v?[0-9]+\.[0-9]+\.[0-9]+", value):
        raise ValueError("The release does not have a supported version number.")
    return tuple(map(int, value.removeprefix("v").split(".")))


def latest_update():
    request = Request(LATEST_URL, headers={"Accept": "application/vnd.github+json",
                                            "User-Agent": f"StitchVert/{VERSION}"})
    with urlopen(request, timeout=8) as response:
        release = json.loads(response.read(262144))
    version = release.get("tag_name")
    if version_tuple(version) > version_tuple(VERSION):
        return version.removeprefix("v")
    return None
