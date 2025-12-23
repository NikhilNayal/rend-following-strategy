
import json
import asyncio
import aiofiles
from typing import Dict, Any

class ConfigManager:
    def __init__(self, config_path: str = "config.json"):
        self.config_path = config_path
        self._lock = asyncio.Lock()

    async def get_config(self) -> Dict[str, Any]:
        async with self._lock:
            try:
                async with aiofiles.open(self.config_path, "r") as f:
                    content = await f.read()
                    return json.loads(content)
            except FileNotFoundError:
                return {}
            except Exception as e:
                print(f"Error reading config: {e}")
                return {}

    async def update_config(self, new_config: Dict[str, Any]):
        async with self._lock:
            try:
                async with aiofiles.open(self.config_path, "w") as f:
                    await f.write(json.dumps(new_config, indent=4))
            except Exception as e:
                print(f"Error writing config: {e}")

    async def get_strategy_settings(self):
        config = await self.get_config()
        return config["strategy_settings"]

    async def set_is_running(self, is_running: bool):
        config = await self.get_config()
        config["is_running"] = is_running
        await self.update_config(config)
