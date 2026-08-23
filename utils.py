from typing import Any
import json
from pathlib import Path

def find_values_by_key(object, key):
    """Recursively find all values of a given key in a nested JSON object."""
    results = []
    if isinstance(object, dict):
        for k, v in object.items():
            if k.lower() == key.lower():
                results.append(v)
            
            results.extend(find_values_by_key(v, key))
    elif isinstance(object, list):
        for item in object:
            results.extend(find_values_by_key(item, key))
    return results

def save_json(
        data: dict[str, Any],
        path: Path 
):
    """
    Saves a dictionary as a JSON file.

    Args:
        data (dict): The data to save.
        path (Path): The path where the JSON file will be saved.
    """
    path.parent.mkdir(parents=True, exist_ok=True)  # Ensure the directory exists
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)  # Save the data as a JSON file with pretty formatting

def find_game_ids(schedule):
    game_ids = []

    if isinstance(schedule, dict):
        for key, value in schedule.items():
            # Match keys like game1, game2, game3, etc.
            if key.startswith("game") and key[4:].isdigit():
                game_ids.append(value)

            game_ids.extend(find_game_ids(value))

    elif isinstance(schedule, list):
        for item in schedule:
            game_ids.extend(find_game_ids(item))

    return game_ids