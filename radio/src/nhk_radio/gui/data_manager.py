"""Data management logic (fetching and caching) decoupled from UI."""

import threading
import time
from collections import OrderedDict
from collections.abc import Callable

from ..core import fetch_program_list, refresh_episode_list
from ..types import Episode, Program


class DataManager:
    """Manages program lists, episode caches, and their background fetching."""

    def __init__(
        self,
        on_program_result: Callable[[list[Program], str | None], None],
        on_episode_result: Callable[[Program, list[Episode], str, str | None], None],
    ):
        self.on_program_result = on_program_result
        self.on_episode_result = on_episode_result

        self.programs: list[Program] = []
        self.filtered_programs: list[Program] = []
        self.episodes_cache: OrderedDict[tuple[str, str], tuple[float, list[Episode]]] = OrderedDict()

        self._fetching_programs = False
        self._fetching_episodes: set[tuple[str, str]] = set()

    def start_fetch_programs(self, genre: str | None = None):
        """Fetches the full program list in the background."""
        if self._fetching_programs:
            return

        self._fetching_programs = True

        def _worker():
            try:
                progs = fetch_program_list(genre)
                self.on_program_result(progs, None)
            except Exception as e:
                self.on_program_result([], str(e))
            finally:
                self._fetching_programs = False

        threading.Thread(target=_worker, daemon=True).start()

    def start_fetch_episodes(self, program: Program):
        """Fetches episodes for a specific program in the background."""
        key = (program.site_id, program.corner_id)
        if key in self._fetching_episodes:
            return

        self._fetching_episodes.add(key)

        def _worker():
            try:
                episodes, source = refresh_episode_list(program)
                self._update_episode_cache(program, episodes)
                self.on_episode_result(program, episodes, source, None)
            except Exception as e:
                self.on_episode_result(program, [], "", str(e))
            finally:
                self._fetching_episodes.discard(key)

        threading.Thread(target=_worker, daemon=True).start()

    def get_cached_episodes(self, program: Program, ttl_seconds: int) -> list[Episode] | None:
        """Returns cached episodes if available and not expired."""
        key = (program.site_id, program.corner_id)
        cached = self.episodes_cache.get(key)
        if cached is not None:
            cached_at, episodes = cached
            if time.time() - cached_at <= ttl_seconds:
                self.episodes_cache.move_to_end(key)
                return episodes
        return None

    def clear_all_data(self):
        """Clears all in-memory data and caches."""
        self.programs.clear()
        self.filtered_programs.clear()
        self.episodes_cache.clear()

    def update_programs(self, programs: list[Program]):
        """Sets the master program list."""
        self.programs = list(programs)

    def _update_episode_cache(self, program: Program, episodes: list[Episode]):
        """Updates the internal episode cache with size limit."""
        key = (program.site_id, program.corner_id)
        self.episodes_cache[key] = (time.time(), episodes)
        self.episodes_cache.move_to_end(key)

        # Capacity limit (100 programs)
        if len(self.episodes_cache) > 100:
            self.episodes_cache.popitem(last=False)
