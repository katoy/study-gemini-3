"""GUI listing — 番組・エピソード一覧の表示と操作。"""

from .episodes import GuiEpisodeMixin
from .operations import GuiOperationsMixin
from .programs import GuiProgramsMixin


class GuiListingMixin(GuiProgramsMixin, GuiEpisodeMixin, GuiOperationsMixin):
    """GuiListingMixin は 3 つの責務 Mixin を統合する。

    - GuiProgramsMixin: 番組ツリー（検索・フィルタ・ソート）
    - GuiEpisodeMixin:  エピソードツリー（表示・ツールチップ）
    - GuiOperationsMixin: ファイル操作・ダウンロード状態
    """


__all__ = ["GuiListingMixin"]
