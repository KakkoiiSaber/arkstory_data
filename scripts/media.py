"""Resolve catalog media against the CN hot-update list and curated exceptions."""
import hashlib
import io
import json
import re
import subprocess
import sys
import zipfile
from collections import defaultdict
from pathlib import Path
from urllib.parse import urlsplit

import imageio_ffmpeg
import requests
import UnityPy
from PIL import Image
from UnityPy.enums.BundleFile import CompressionFlags
from UnityPy.helpers import CompressionHelper

from catalog import save

sys.path.insert(0, str(Path(".work/kawa/kawapack/_src/lz4ak").resolve()))
from Block import decompress_lz4ak

CompressionHelper.DECOMPRESSION_MAP[CompressionFlags.LZHAM] = decompress_lz4ak
ROOT = Path("data")
FAMILIES = {"kvImageId": "kv", "titleImageId": "title", "backgroundId": "retro_bkg"}
VERSION = "https://ak-conf.hypergryph.com/config/prod/official/Android/version"
CDN = "https://ak.hycdn.cn/assetbundle/official/Android/assets/"
SESSION = requests.Session()
from urllib3.util.retry import Retry
SESSION.mount("https://", requests.adapters.HTTPAdapter(max_retries=Retry(
    total=3, backoff_factor=1, status_forcelist=(429, 500, 502, 503, 504))))


def fetch(url):
    response = SESSION.get(url, timeout=90, headers={"Referer": "https://prts.wiki/"})
    response.raise_for_status()
    return response


def wants():
    images, tracks = {}, {}
    def music(bank):
        if bank:
            for part in ("intro", "loop"):
                if bank.get(part):
                    tracks[bank[part]] = bank.get("loopSongId") if part == "loop" else None
    for path in ROOT.glob("*/index.json"):
        index = json.loads(path.read_bytes())
        music(index["homeMusic"])
        for card in index["stories"]:
            detail = json.loads((path.parent / card["detail"]).read_bytes())
            for field, family in FAMILIES.items():
                values = [detail.get(field)]
                if field == "backgroundId" and detail.get("backgroundUrls"):
                    values = detail["backgroundUrls"]
                images.update({v: family for v in values if v})
            music(detail["audio"])
    return images, tracks


def publish(key, data, origin, state):
    suffix = Path(urlsplit(key).path).suffix.lower()
    if suffix in {".png", ".jpg", ".webp", ".jpeg"}:
        with Image.open(io.BytesIO(data)) as image:
            image.verify()
    else:
        subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(), "-v", "error", "-xerror", "-i",
                        "pipe:0", "-f", "null", "-"], input=data, check=True)
    digest = hashlib.sha256(data).hexdigest()
    path = Path("media") / digest[:2] / (digest + suffix)
    if not path.exists() or hashlib.sha256(path.read_bytes()).hexdigest() != digest:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    state[key] = dict(path=path.as_posix(), sha256=digest, bytes=len(data), source=origin)


def extract(base, row, wanted, state):
    name = row["name"]
    url = base + name[:-3].replace("/", "_").replace("#", "__") + ".dat"
    cache = Path(".work/bundles") / row["md5"]
    cache.parent.mkdir(parents=True, exist_ok=True)
    data = cache.read_bytes() if cache.exists() else fetch(url).content
    if len(data) != row["totalSize"]:
        raise ValueError(f"Bundle integrity check failed: {name}")
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        for member in archive.namelist():
            if not member.endswith(".ab"):
                continue
            payload = archive.read(member)
            if hashlib.md5(payload).hexdigest() != row["md5"]:
                raise ValueError(f"Bundle MD5 mismatch: {name}")
            if not cache.exists():
                cache.write_bytes(data)
            env = UnityPy.load(payload)
            # Prefer the Sprite crop when both the atlas texture and sprite share a name.
            emitted = set()
            for obj in sorted(env.objects, key=lambda o: o.type.name != "Sprite"):
                if obj.type.name not in {"Sprite", "Texture2D", "AudioClip"}:
                    continue
                item = obj.read()
                keys = wanted.get(item.m_Name.lower(), [])
                if not keys or item.m_Name.lower() in emitted:
                    continue
                if obj.type.name == "AudioClip":
                    sample, = item.samples.values()
                    out = subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(), "-v", "error",
                        "-i", "pipe:0", "-f", "mp3", "pipe:1"], input=sample,
                        stdout=subprocess.PIPE, check=True).stdout
                else:
                    buf = io.BytesIO()
                    item.image.save(buf, "PNG")
                    out = buf.getvalue()
                emitted.add(item.m_Name.lower())
                for key in keys:
                    publish(key, out, name, state)


def main():
    manifest = ROOT / "media.json"
    previous = json.loads(manifest.read_bytes()) if manifest.exists() else {}
    version = fetch(VERSION).json()["resVersion"]
    base = CDN + version + "/"
    rows = {r["name"]: r for r in fetch(base + "hot_update_list.json").json()["abInfos"]}
    images, tracks = wants()
    groups = defaultdict(lambda: defaultdict(list))
    external = {}
    for key, family in images.items():
        if key.startswith("https://"):
            external[key] = key
        else:
            for name in rows:
                if name.startswith("spritepack/mixstory_" + family + "_"):
                    groups[name][Path(key).stem.lower()].append(key)
    for key, song_id in tracks.items():
        path = urlsplit(key).path
        if "/music/" in path:
            stem = "audio/sound_beta_2/music/" + path.split("/music/", 1)[1].rsplit(".", 1)[0]
            name = re.sub(r"_(loop|intro)$", "", stem) + ".ab"
            if name in rows:
                groups[name][Path(stem).name].append(key)
                continue
        if song_id:
            external[key] = fetch(f"https://monster-siren.hypergryph.com/api/song/{song_id}").json()["data"]["sourceUrl"]
        elif key.startswith("https://") and "/arkdata/" not in key:
            external[key] = key
        else:
            raise ValueError(f"No official bundle or curated source for {key}")

    wanted = set(images) | set(tracks)
    state = {}
    for key, r in previous.get("resources", {}).items():
        if key in wanted and Path(r["path"]).is_file() and hashlib.sha256(Path(r["path"]).read_bytes()).hexdigest() == r["sha256"]:
            state[key] = r
    extractor = hashlib.sha256(Path(__file__).read_bytes().replace(b"\r\n", b"\n") + Path("requirements.txt").read_bytes().replace(b"\r\n", b"\n")).hexdigest()
    fingerprints = {}
    for name, names in groups.items():
        fingerprint = [rows[name]["md5"], sorted(k for keys in names.values() for k in keys)]
        fingerprints[name] = fingerprint
        prior = previous.get("bundles", {}).get(name)
        missing = any(k not in state for k in fingerprint[1] if previous.get("resources", {}).get(k, {}).get("source") == name)
        if prior != fingerprint or missing or previous.get("extractor") != extractor:
            for key in list(state):
                if state[key]["source"] == name:
                    del state[key]
            print("Extracting", name, flush=True)
            extract(base, rows[name], names, state)
    for key, url in external.items():
        publish(key, fetch(url).content, "external", state)
    if missing := wanted - state.keys():
        raise ValueError(f"Missing media: {sorted(missing)}")
    save(manifest, dict(version=version, extractor=extractor, bundles=fingerprints, resources=dict(sorted(state.items()))))
    print(len(state), "verified media references")


if __name__ == "__main__":
    main()

