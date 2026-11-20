import copy
import re
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo

THEME_FIELDS = (
    "kvImageId", "titleImageId", "backgroundId", "coverContainsTitle", "titleIsBanner",
    "coverSource", "backgroundUrls", "backgroundAspectRatio", "musicRole",
    "themeSources", "themeNotes", "audio",
)


def apply_stage_complement(stage_entry, complement, server):
    entry = copy.deepcopy(stage_entry)
    if complement and server in complement.get("servers", [server]):
        entry.update({key: value for key, value in complement.items() if key != "servers"})
    return entry


def resolve_stage_audio(stage_entry, audio_data):
    """Resolve real music IDs or bank names, then apply verified source URLs."""
    if (stage_entry.get("musicRole") in ("none", "opening-story")
            or (stage_entry.get("gameMusicName") or "").startswith("story.")
            or (stage_entry.get("audio", {}).get("name") or "").startswith("story.")):
        return None
    if stage_entry.get("gameMusicId"):
        audio_info = get_audio_table(stage_entry["gameMusicId"], audio_data)
    elif stage_entry.get("audio", {}).get("name"):
        # Explicitly named story-music fallback, not a game music ID/bank.
        audio_info = {}
    elif stage_entry.get("gameMusicName"):
        bank = next((item for item in audio_data["bgmBanks"]
                     if item["name"] == stage_entry["gameMusicName"]), None)
        if bank is None:
            raise ValueError(f"Unknown music bank: {stage_entry['gameMusicName']}")
        audio_info = format_audio_bank(bank)
    else:
        audio_info = {}
    if stage_entry.get("audio"):
        audio_info.update(copy.deepcopy(stage_entry["audio"]))
    if not audio_info:
        return None
    if stage_entry.get("audio") and (not audio_info.get("name") or not audio_info.get("loop")):
        raise ValueError("Complement audio requires a resolved name and loop")
    return audio_info


def copy_theme_fields(result, stage_entry):
    if stage_entry:
        result.update({key: stage_entry[key] for key in THEME_FIELDS if key in stage_entry})
    return result

def simplify_story_review_table(table: dict) -> dict:
    # filter required keys and values
    simplified_table = {
        "id": table["id"],
        "name": table["name"],
        "type": table["actType"],
        "startTime": datetime.fromtimestamp(table["startTime"], tz=ZoneInfo("Asia/Shanghai")).strftime("%Y-%m"),
        "infoUnlockDatas": table["infoUnlockDatas"]
    }
    return simplified_table

def simplify_stage_table(table: dict) -> dict:
    if table["storySetType"] == "MAINLINE":
        id = table["mainlineData"]["zoneId"]
        if id is None: 
            # main story from main_14 as activity
            # for ep 15, relavant id is act2mainss => 15 = 13+ 2, split act and mainss
            relavantId = table["relevantActivityId"]
            id = "main_" + str(13 + int(relavantId.split("act")[-1].split("mainss")[0]))
        # Mixstory backgrounds share the cover's English asset suffix.
        # bg_mainLine_N is a shared UI background ID, not a mixstory filename.
        # Older generators also used the nonexistent storybg_main_N pattern.
        background_key = table.get("backgroundId")
        if (not background_key or re.fullmatch(r"(?:bg_mainLine_|storybg_main_)\d+", background_key)) and table.get("kvImageId"):
            background_key = "storybg_" + table["kvImageId"].removeprefix("kv_")
        backgroundId = f"{background_key}.png" if background_key else None
        desc = None
    elif table["storySetType"] == "SS":
        id = table["relevantActivityId"]
        backgroundId = f"{table['ssData']['backgroundId']}.png" if table['ssData']['backgroundId'] else None
        desc = table['ssData']['desc'] if table['ssData']['desc'] else None
    elif table["storySetType"] == "COLLECT":
        id = table["relevantActivityId"]
        backgroundId = f"{table['collectData']['backgroundId']}.png" if table['collectData']['backgroundId'] else None
        desc = table['collectData']['desc'] if table['collectData']['desc'] else None

    # get kvImageId, titleImageId, gameMusicId
    simplified_table = {
        "id": id,
        "desc": desc,
        "kvImageId": f"{table['kvImageId']}.png" if table['kvImageId'] else None,
        "titleImageId": f"{table['titleImageId']}.png" if table['titleImageId'] else None,
        "gameMusicId": table['gameMusicId'],
        "backgroundId": backgroundId
    }
    return simplified_table

def get_review_info(review_table: dict, stage_table: dict, story_desc_path: str) -> dict:
    infoUnlockDatas = review_table["infoUnlockDatas"]
    info_list = []
    for data in infoUnlockDatas:
        if data['storyInfo'] is not None:
            try:
                storyDesc = (Path(story_desc_path) / f"[uc]{data['storyInfo']}.txt").read_text(encoding="utf-8")
            except FileNotFoundError:
                storyDesc = None
        else:
            storyDesc = None
        info = {
            "storyId": data["storyId"],
            "storyCode": data["storyCode"] if data["storyCode"] != "" else None,
            "storyName": data["storyName"],
            "storyDesc": storyDesc,
            "storyTxt": f"{data['storyTxt']}.txt",
            "avgTag": data["avgTag"]
        }
        info_list.append(info)

    review_info = {
        "id": review_table["id"],
        "name": review_table["name"],
        **{key: stage_table.get(key) for key in ("desc", "gameMusicId", "gameMusicName", "backgroundId")},
        "infoUnlockDatas": info_list,
    }
    return copy_theme_fields(review_info, stage_table)

def get_audio_table(gameMusicId: str, audio_data: dict) -> dict:
    musics_table = audio_data["musics"]
    bankAlias_table = audio_data["bankAlias"]
    bgmBanks_table = audio_data["bgmBanks"]

    music_value = next((item for item in musics_table if item["id"] == gameMusicId), None)
    if music_value is None:
        raise ValueError(f"Unknown music ID: {gameMusicId}")
    bank_alias = music_value["bank"]
    bankName = bankAlias_table.get(str(bank_alias), bank_alias)
    bank = next((item for item in bgmBanks_table if item["name"] == bankName), None)
    if bank is None:
        raise ValueError(f"Unknown music bank: {bankName}")
    return format_audio_bank(bank)


def format_audio_bank(bank):
    bank_info = copy.deepcopy(bank)
    if bank_info["intro"] is not None:
        bank_info["intro"] = bank_info["intro"].lower() + ".mp3"
    if bank_info["loop"] is not None:
        bank_info["loop"] = bank_info["loop"].lower() + ".mp3"
    return bank_info



