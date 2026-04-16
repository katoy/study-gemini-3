"""Shared constants for the NHK radio downloader."""

NHK_ONDEMAND_URL = "https://www.nhk.or.jp/radio/ondemand/"
NHK_API_NEW_CORNERS = "https://www.nhk.or.jp/radio-api/app/v1/web/ondemand/corners/new_arrivals"
NHK_API_GENRE = "https://www.nhk.or.jp/radio-api/app/v1/web/ondemand/series?genre={genre}"
NHK_DETAIL_TMPL = "https://www.nhk.or.jp/radio/ondemand/detail.html?p={site_id}_{corner_id}"
NHK_EPISODE_TMPL = (
    "https://www.nhk.or.jp/radio/player/ondemand.html"
    "?p={site_id}_{corner_id}_{episode_id}"
)

NHK_GENRES = ["language", "music", "news", "drama", "sports", "documentary", "variety"]

_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)
_HEADERS = {"User-Agent": _UA, "Accept-Language": "ja,en;q=0.9"}

JP_WEEKDAYS = "月火水木金土日"

GENRE_LABELS = {
    "language": "語学",
    "music": "音楽",
    "news": "ニュース",
    "drama": "ドラマ",
    "sports": "スポーツ",
    "documentary": "ドキュメンタリー",
    "variety": "バラエティ",
}
