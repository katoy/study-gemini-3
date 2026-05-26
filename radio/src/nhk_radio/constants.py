"""Shared constants for the NHK radio downloader."""

NHK_ONDEMAND_URL = "https://www.nhk.or.jp/radio/ondemand/"
NHK_API_NEW_CORNERS = "https://www.nhk.or.jp/radio-api/app/v1/web/ondemand/corners/new_arrivals"
NHK_API_GENRE = "https://www.nhk.or.jp/radio-api/app/v1/web/ondemand/series?genre={genre}"
NHK_DETAIL_TMPL = "https://www.nhk.or.jp/radio/ondemand/detail.html?p={site_id}_{corner_id}"
NHK_EPISODE_TMPL = "https://www.nhk.or.jp/radio/player/ondemand.html?p={site_id}_{corner_id}_{episode_id}"

NHK_GENRES = ["new_series", "news", "sports", "information", "drama", "music", "variety", "documentary", "theater", "hobby", "welfare", "kids", "language", "local"]

# NHK API への同時リクエスト数の上限。過剰な負荷をかけないための制御。
MAX_CONCURRENT_API_REQUESTS = 3

# NHK Radio API へのリクエストに使用する User-Agent。
# ブロックされるようなら Chrome の最新版番号に更新すること (最終確認: 2025-04)。
_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)
_HEADERS = {"User-Agent": _UA, "Accept-Language": "ja,en;q=0.9"}

# HTTP リトライ設定
HTTP_RETRY_COUNT = 3          # 最大試行回数（初回含む）
HTTP_RETRY_BASE_DELAY = 0.5   # バックオフ基準秒数 (0.5s → 1s → 2s)
HTTP_RETRY_MAX_DELAY = 10.0   # バックオフ上限秒数

# yt-dlp ダウンロード設定
YTDLP_CONCURRENT_FRAGMENTS = 4  # HLS フラグメント並列数
YTDLP_SOCKET_TIMEOUT = 30       # ソケットタイムアウト秒数

JP_WEEKDAYS = "月火水木金土日"

GENRE_LABELS = {
    "language": "語学",
    "music": "音楽",
    "news": "ニュース",
    "drama": "ドラマ",
    "sports": "スポーツ",
    "documentary": "ドキュメンタリー",
    "variety": "バラエティ",
    "hobby": "教養・趣味",
    "theater": "演劇",
    "information": "情報/ワイドショー",
    "kids": "キッズ",
    "welfare": "福祉",
    "local": "地域放送局",
    "new_series": "新番組",
}
