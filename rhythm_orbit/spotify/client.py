"""Metadata only. Never sends Spotify audio to the analysis pipeline."""
from __future__ import annotations
import os
import re
from urllib.request import urlopen
from urllib.parse import urlparse


def track_id(value: str) -> str | None:
    value = value.strip()
    if value.startswith("spotify:track:"):
        candidate = value.split(":")[-1]
    else:
        parsed = urlparse(value)
        if parsed.hostname != "open.spotify.com":
            return None
        parts = parsed.path.rstrip("/").split("/")
        candidate = parts[-1] if len(parts) >= 3 and parts[-2] == "track" else ""
    return candidate if re.fullmatch(r"[A-Za-z0-9]{22}", candidate) else None


def search(query: str) -> list[dict]:
    import spotipy
    from spotipy.oauth2 import SpotifyClientCredentials
    if not os.environ.get("SPOTIPY_CLIENT_ID") or not os.environ.get("SPOTIPY_CLIENT_SECRET"):
        raise ValueError("Set SPOTIPY_CLIENT_ID and SPOTIPY_CLIENT_SECRET to your own Spotify developer credentials, then restart. See README → Spotify.")
    client = spotipy.Spotify(auth_manager=SpotifyClientCredentials(), requests_timeout=15, retries=1)
    identifier = track_id(query)
    tracks = [client.track(identifier)] if identifier else client.search(q=query, type="track", limit=10)["tracks"]["items"]
    results = []
    for track in tracks:
        if not track:
            continue
        images = track.get("album", {}).get("images", [])
        results.append({"title": track["name"], "artist": ", ".join(a["name"] for a in track["artists"]),
                        "album": track.get("album", {}).get("name", ""), "duration": track["duration_ms"] / 1000,
                        "url": track["external_urls"]["spotify"], "artwork": images[-1]["url"] if images else None})
    return results


def artwork(url: str) -> bytes:
    if urlparse(url).scheme != "https":
        raise ValueError("Artwork URL must use HTTPS")
    with urlopen(url, timeout=15) as response:
        return response.read(4 * 1024 * 1024)
