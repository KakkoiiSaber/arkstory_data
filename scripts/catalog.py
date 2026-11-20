"""Build the catalog from a sparse checkout of Kengxxiao's game tables."""
import argparse
import json
from pathlib import Path

from review import (apply_stage_complement, get_audio_table, get_review_info,
                    resolve_stage_audio, simplify_stage_table, simplify_story_review_table)


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def generate(source, locale, output):
    root = source / locale / "gamedata"
    def table(name):
        return json.loads((root / "excel" / (name + ".json")).read_bytes())

    overrides = json.loads(Path("config/themes.json").read_bytes())
    stages = {}
    for raw in table("stage_table")["storylineStorySets"].values():
        if raw["storySetType"] in {"SS", "MAINLINE", "COLLECT"}:
            stage = simplify_stage_table(raw)
            stages[stage["id"]] = stage
    audio = table("audio_data")
    home = get_audio_table("music_bg_default", audio)
    index = []
    for raw in table("story_review_table").values():
        if raw["actType"] not in {"ACTIVITY_STORY", "MAIN_STORY", "MINI_STORY"}:
            continue
        review = simplify_story_review_table(raw)
        key = review["id"]
        stage = apply_stage_complement(stages.get(key, {}), overrides.get(key), locale)
        detail = get_review_info(review, stage, str(root / "story"))
        detail["audio"] = resolve_stage_audio(stage, audio)
        detail["kvImageId"] = stage.get("kvImageId")
        detail["titleImageId"] = stage.get("titleImageId")
        detail.pop("themeSources", None)
        detail.pop("themeNotes", None)
        path = f"stories/{key}.json"
        save(output / locale / path, detail)
        index.append({**{k: review[k] for k in ("id", "name", "type", "startTime")},
                      "kvImageId": detail["kvImageId"], "detail": path})
    save(output / locale / "index.json", {"version": 1, "homeMusic": home, "stories": index})
    return index


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("--locale", default="zh_CN")
    parser.add_argument("--output", type=Path, default=Path("data"))
    args = parser.parse_args()
    print(len(generate(args.source, args.locale, args.output)), "stories")
