"""Curses-based browser for NHK radio programs."""

import curses
import time

from .cache import clear_episode_cache, load_episode_cache
from .config import CACHE_TTL_SECONDS
from .core import get_episode_list
from .text import _fit_text, _safe_addnstr


class EpisodeBrowser:
    def __init__(self, stdscr, programs: list[dict]):
        self.stdscr = stdscr
        self.programs = programs
        self.program_index = 0
        self.program_top = 0
        self.focus = "programs"
        self.status = "上下キーで番組を選択、Enter で下段を取得"
        self.episodes_cache: dict[tuple[str, str], tuple[float, list[dict]]] = {}
        self.episode_index: dict[tuple[str, str], int] = {}
        self.episode_top: dict[tuple[str, str], int] = {}
        self.selected_episode_ids: dict[tuple[str, str], set[str]] = {}
        self.active_program_key: tuple[str, str] | None = None

    def run(self) -> tuple[dict, list[dict]] | tuple[None, None]:
        try:
            curses.curs_set(0)
        except curses.error:
            pass
        self.stdscr.keypad(True)
        while True:
            self._draw()
            key = self.stdscr.getch()
            if key in (ord("q"), 27):
                return None, None
            if key == 9:
                if self.focus == "programs":
                    if self.active_program_key is not None:
                        self.focus = "episodes"
                else:
                    self.focus = "programs"
                continue
            if self.focus == "programs":
                self._handle_program_key(key)
            else:
                result = self._handle_episode_key(key)
                if result is not None:
                    return result

    def _handle_program_key(self, key: int) -> None:
        if key in (curses.KEY_UP, ord("k")):
            self._move_program(-1)
        elif key in (curses.KEY_DOWN, ord("j")):
            self._move_program(1)
        elif key == curses.KEY_PPAGE:
            self._move_program(-8)
        elif key == curses.KEY_NPAGE:
            self._move_program(8)
        elif key in (curses.KEY_HOME, ord("g")):
            self.program_index = 0
        elif key in (curses.KEY_END, ord("G")):
            self.program_index = len(self.programs) - 1
        elif key in (curses.KEY_ENTER, 10, 13):
            self._activate_current_program()
        elif key == curses.KEY_RIGHT and self.active_program_key is not None:
            self.focus = "episodes"
        elif key == ord("C"):
            self._clear_cache_and_reload()

    def _handle_episode_key(self, key: int) -> tuple[dict, list[dict]] | None:
        if key in (curses.KEY_LEFT, ord("h")):
            self.focus = "programs"
        elif key in (curses.KEY_UP, ord("k")):
            self._move_episode(-1)
        elif key in (curses.KEY_DOWN, ord("j")):
            self._move_episode(1)
        elif key == curses.KEY_PPAGE:
            self._move_episode(-8)
        elif key == curses.KEY_NPAGE:
            self._move_episode(8)
        elif key == ord("a"):
            self._toggle_all_episodes()
        elif key == ord(" "):
            self._toggle_current_episode()
        elif key in (ord("d"), curses.KEY_ENTER, 10, 13):
            selected = self._selected_episodes()
            if selected:
                return self.active_program, selected
            self.status = "下段でダウンロード対象を選んでください"
        elif key == ord("C"):
            self._clear_cache_and_reload()
        return None

    @property
    def current_program(self) -> dict:
        return self.programs[self.program_index]

    @property
    def current_key(self) -> tuple[str, str]:
        program = self.current_program
        return program["site_id"], program["corner_id"]

    @property
    def preview_program(self) -> dict:
        return self.current_program if self.focus == "programs" else (self.active_program or self.current_program)

    @property
    def preview_key(self) -> tuple[str, str]:
        program = self.preview_program
        return program["site_id"], program["corner_id"]

    @property
    def preview_episodes(self) -> list[dict]:
        key = self.preview_key
        cached = self.episodes_cache.get(key)
        if not cached:
            cached_episodes = load_episode_cache(self.preview_program)
            if cached_episodes is None:
                return []
            self.episodes_cache[key] = (time.time(), cached_episodes)
            return cached_episodes
        cached_at, episodes = cached
        if time.time() - cached_at > CACHE_TTL_SECONDS:
            self.episodes_cache.pop(key, None)
            cached_episodes = load_episode_cache(self.preview_program)
            if cached_episodes is None:
                return []
            self.episodes_cache[key] = (time.time(), cached_episodes)
            return cached_episodes
        return episodes

    @property
    def current_episodes(self) -> list[dict]:
        if self.active_program_key is None:
            return []
        cached = self.episodes_cache.get(self.active_program_key)
        if not cached:
            return []
        cached_at, episodes = cached
        if time.time() - cached_at > CACHE_TTL_SECONDS:
            self.episodes_cache.pop(self.active_program_key, None)
            return []
        return episodes

    @property
    def active_program(self) -> dict | None:
        if self.active_program_key is None:
            return None
        for program in self.programs:
            if (program["site_id"], program["corner_id"]) == self.active_program_key:
                return program
        return None

    def _load_current_program(self):
        key = self.current_key
        if self.active_program_key == key and self.current_episodes:
            return

        title = self.current_program.get("display_title") or self.current_program["title"]
        self.status = f"「{title}」のエピソードを取得中..."
        try:
            curses.curs_set(2)
        except curses.error:
            pass
        self._draw()
        try:
            episodes, source = get_episode_list(self.current_program)
            self.episodes_cache[key] = (time.time(), episodes)
        except Exception as e:
            self.episodes_cache[key] = (time.time(), [])
            self.status = f"取得失敗: {e}"
            source = ""
        finally:
            try:
                curses.curs_set(0)
            except curses.error:
                pass
        self.episode_index.setdefault(key, 0)
        self.episode_top.setdefault(key, 0)
        self.selected_episode_ids.setdefault(key, set())
        self.active_program_key = key

        episodes = self.current_episodes
        if episodes:
            source_label = {
                "cache": "キャッシュ",
                "stale-cache": "期限切れキャッシュ",
            }.get(source, "最新取得")
            self.status = f"{len(episodes)} 件のエピソードを表示中 ({source_label})"
        elif not self.status.startswith("取得失敗:"):
            self.status = "エピソードが見つかりませんでした"

    def _activate_current_program(self):
        self._load_current_program()
        self.focus = "episodes"

    def _move_program(self, delta: int):
        new_index = min(max(self.program_index + delta, 0), len(self.programs) - 1)
        if new_index == self.program_index:
            return
        self.program_index = new_index
        title = self.current_program.get("display_title") or self.current_program["title"]
        if self.preview_episodes:
            self.status = f"「{title}」のキャッシュを表示中。Enter で最新一覧を取得"
        else:
            self.status = f"「{title}」の一覧は未取得です。Enter で下段を取得"

    def _move_episode(self, delta: int):
        episodes = self.current_episodes
        if not episodes:
            return
        key = self.active_program_key
        if key is None:
            return
        current = self.episode_index.get(key, 0)
        self.episode_index[key] = min(max(current + delta, 0), len(episodes) - 1)

    def _toggle_current_episode(self):
        episodes = self.current_episodes
        if not episodes:
            return
        key = self.active_program_key
        if key is None:
            return
        current = episodes[self.episode_index.get(key, 0)]
        selected = self.selected_episode_ids.setdefault(key, set())
        if current["id"] in selected:
            selected.remove(current["id"])
        else:
            selected.add(current["id"])

    def _toggle_all_episodes(self):
        episodes = self.current_episodes
        if not episodes:
            return
        key = self.active_program_key
        if key is None:
            return
        selected = self.selected_episode_ids.setdefault(key, set())
        episode_ids = {ep["id"] for ep in episodes}
        if selected == episode_ids:
            selected.clear()
        else:
            selected.clear()
            selected.update(episode_ids)

    def _selected_episodes(self) -> list[dict]:
        episodes = self.current_episodes
        if not episodes:
            return []

        key = self.active_program_key
        if key is None:
            return []
        selected_ids = self.selected_episode_ids.get(key, set())
        if selected_ids:
            return [ep for ep in episodes if ep["id"] in selected_ids]

        return [episodes[self.episode_index.get(key, 0)]]

    def _clear_cache_and_reload(self):
        removed = clear_episode_cache()
        self.episodes_cache.clear()
        self.episode_index.clear()
        self.episode_top.clear()
        self.selected_episode_ids.clear()
        self.active_program_key = None
        self.status = f"キャッシュをクリアしました ({removed} 件)"
        self._activate_current_program()

    def _draw(self):
        self.stdscr.erase()
        height, width = self.stdscr.getmaxyx()

        if height < 12 or width < 70:
            _safe_addnstr(self.stdscr, 0, 0, "端末サイズが小さすぎます。70x12 以上に広げてください。", width)
            self.stdscr.refresh()
            return

        top_height = max(8, int(height * 0.58))
        bottom_y = top_height + 1
        bottom_height = height - bottom_y - 2
        if bottom_height < 4:
            bottom_height = 4

        self._draw_programs(0, 0, top_height, width)
        self._draw_episodes(bottom_y, 0, bottom_height, width)

        help_text = "q 終了  Enter 下段取得  Tab/←→ 切替  Space 選択  C キャッシュ削除  d/Enter DL"
        _safe_addnstr(self.stdscr, height - 2, 0, _fit_text(help_text, width), width)
        _safe_addnstr(self.stdscr, height - 1, 0, _fit_text(self.status, width), width, curses.A_DIM)
        self.stdscr.refresh()

    def _draw_programs(self, y: int, x: int, height: int, width: int):
        _safe_addnstr(self.stdscr, y, x, _fit_text("▼ 聞き逃しサービス", width), width, curses.A_BOLD)
        header_attr = curses.A_REVERSE if self.focus == "programs" else curses.A_BOLD
        _safe_addnstr(self.stdscr, y + 1, x, _fit_text("No.", 5), 5, header_attr)
        _safe_addnstr(self.stdscr, y + 1, x + 6, _fit_text("放送日", 22), 22, header_attr)
        _safe_addnstr(self.stdscr, y + 1, x + 29, _fit_text("番組", width - 29), width - 29, header_attr)

        visible = max(height - 3, 1)
        self.program_top = min(max(self.program_top, 0), max(len(self.programs) - visible, 0))
        if self.program_index < self.program_top:
            self.program_top = self.program_index
        elif self.program_index >= self.program_top + visible:
            self.program_top = self.program_index - visible + 1

        for row in range(visible):
            idx = self.program_top + row
            screen_y = y + 2 + row
            if idx >= len(self.programs):
                _safe_addnstr(self.stdscr, screen_y, x, " " * width, width)
                continue

            program = self.programs[idx]
            attr = curses.A_REVERSE if idx == self.program_index else curses.A_NORMAL
            number_text = _fit_text(str(idx + 1), 5)
            date_text = _fit_text(program.get("display_date", "----"), 22)
            title_text = _fit_text(program.get("display_title", program["title"]), width - 29)
            _safe_addnstr(self.stdscr, screen_y, x, number_text, 5, attr)
            _safe_addnstr(self.stdscr, screen_y, x + 6, date_text, 22, attr)
            _safe_addnstr(self.stdscr, screen_y, x + 29, title_text, width - 29, attr)

    def _draw_episodes(self, y: int, x: int, height: int, width: int):
        preview_program = self.preview_program
        title = preview_program.get("display_title") or preview_program["title"]
        header = f"▼ エピソード一覧: {title}"
        _safe_addnstr(self.stdscr, y, x, _fit_text(header, width), width, curses.A_BOLD)
        header_attr = curses.A_REVERSE if self.focus == "episodes" else curses.A_BOLD
        _safe_addnstr(self.stdscr, y + 1, x, _fit_text("選択", 6), 6, header_attr)
        _safe_addnstr(self.stdscr, y + 1, x + 7, _fit_text("放送日時", 18), 18, header_attr)
        _safe_addnstr(self.stdscr, y + 1, x + 26, _fit_text("長さ", 9), 9, header_attr)
        _safe_addnstr(self.stdscr, y + 1, x + 36, _fit_text("タイトル", width - 36), width - 36, header_attr)

        episodes = self.preview_episodes
        visible = max(height - 2, 1)
        key = self.preview_key
        if self.focus == "programs" and not episodes:
            _safe_addnstr(self.stdscr, y + 2, x, _fit_text("一覧は未取得です。上段で Enter を押すと取得します。", width), width)
            return
        if self.focus == "episodes" and self.active_program_key is None:
            _safe_addnstr(self.stdscr, y + 2, x, _fit_text("一覧は未取得です。上段で Enter を押すと取得します。", width), width)
            return
        self.episode_top[key] = min(max(self.episode_top.get(key, 0), 0), max(len(episodes) - visible, 0))
        current_idx = self.episode_index.get(key, 0)
        if current_idx < self.episode_top[key]:
            self.episode_top[key] = current_idx
        elif current_idx >= self.episode_top[key] + visible:
            self.episode_top[key] = current_idx - visible + 1

        if not episodes:
            _safe_addnstr(self.stdscr, y + 2, x, _fit_text("利用可能なエピソードがありません。", width), width)
            return

        selected_ids = self.selected_episode_ids.get(key, set())
        for row in range(visible):
            idx = self.episode_top[key] + row
            screen_y = y + 2 + row
            if idx >= len(episodes):
                _safe_addnstr(self.stdscr, screen_y, x, " " * width, width)
                continue

            episode = episodes[idx]
            marker = "[x]" if episode["id"] in selected_ids else "[ ]"
            attr = curses.A_REVERSE if idx == current_idx else curses.A_NORMAL
            date_time = episode.get("display_date", "----")
            btime = episode.get("broadcast_time", "")
            if btime:
                date_time = f"{date_time} {btime}"
            dur = episode.get("duration_str", "")
            dur_text = f"[{dur}]" if dur else "---------"
            _safe_addnstr(self.stdscr, screen_y, x, _fit_text(marker, 6), 6, attr)
            _safe_addnstr(self.stdscr, screen_y, x + 7, _fit_text(date_time, 18), 18, attr)
            _safe_addnstr(self.stdscr, screen_y, x + 26, _fit_text(dur_text, 9), 9, attr)
            _safe_addnstr(self.stdscr, screen_y, x + 36, _fit_text(episode.get("display_title", episode["title"]), width - 36), width - 36, attr)


def browse_programs_tui(programs: list[dict]) -> tuple[dict, list[dict]] | tuple[None, None]:
    try:
        return curses.wrapper(lambda stdscr: EpisodeBrowser(stdscr, programs).run())
    except curses.error as e:
        raise RuntimeError(str(e)) from e
