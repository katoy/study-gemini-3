# NHK Radio Program API

このドキュメントは、`nhk_radio_dl.py` が利用している **番組一覧 API** を実装ベースで整理したものです。  
正式な公開仕様ではなく、**2026-04 時点の観測結果 + 現在のコード実装** に基づきます。  
あわせて、公開ポータル `https://api-portal.nhk.or.jp/service-guide` の記載内容との差分も参考情報として併記します。

## OpenAPI-like summary

```yaml
openapi: 3.1.0
info:
  title: NHK Radio Ondemand Program API
  version: "observed-2026-04"
  description: >
    NHK ラジオ聞き逃し番組一覧を取得するために本リポジトリが利用している API。
    正式仕様ではなく、実装で使っている範囲だけを記述する。
servers:
  - url: https://www.nhk.or.jp/radio-api
paths:
  /app/v1/web/ondemand/corners/new_arrivals:
    get:
      summary: 新着寄りの番組・コーナー一覧を返す
      responses:
        "200":
          description: OK
          content:
            application/json:
              schema:
                type: object
                properties:
                  corners:
                    type: array
                    items:
                      $ref: "#/components/schemas/ProgramSourceItem"
  /app/v1/web/ondemand/series:
    get:
      summary: ジャンル別または全体のシリーズ一覧を返す
      parameters:
        - in: query
          name: genre
          required: false
          schema:
            type: string
            enum:
              - language
              - music
              - news
              - drama
              - sports
              - documentary
              - variety
      responses:
        "200":
          description: OK
          content:
            application/json:
              schema:
                type: object
                properties:
                  series:
                    type: array
                    items:
                      $ref: "#/components/schemas/ProgramSourceItem"
components:
  schemas:
    ProgramSourceItem:
      type: object
      properties:
        series_site_id:
          type: string
        site_id:
          type: string
        corner_site_id:
          type: string
        corner_id:
          type: string
        title:
          type: string
        corner_name:
          type: string
        onair_date:
          type: string
        started_at:
          type: string
          format: date-time
    NormalizedProgram:
      type: object
      required:
        - title
        - genre_label
        - site_id
        - corner_id
        - display_date
        - display_title
        - url
      properties:
        title:
          type: string
        corner_name:
          type: string
        genre:
          type:
            - string
            - "null"
        genre_label:
          type: string
        site_id:
          type: string
        corner_id:
          type: string
        onair_date:
          type: string
        display_date:
          type: string
          description: YYYY-MM-DD(曜) 形式に整形した表示用日付
        display_title:
          type: string
          description: corner_name が title と異なる場合は "[title] corner_name"
        started_at:
          type: string
        url:
          type: string
          format: uri
```

## Endpoints

### 1. `GET /app/v1/web/ondemand/corners/new_arrivals`

- 実URL: `https://www.nhk.or.jp/radio-api/app/v1/web/ondemand/corners/new_arrivals`
- 用途: 新着寄りの番組・コーナー一覧取得
- コード上の扱い: **全番組取得の起点**
- 主配列: `corners`

#### 観測できた主なフィールド

| Field | Type | Note |
|---|---|---|
| `series_site_id` | string | 番組 ID |
| `corner_site_id` | string | コーナー ID |
| `title` | string | 番組名 |
| `corner_name` | string | コーナー名。空文字あり |
| `onair_date` | string | 例: `2026年4月15日(水)放送` |
| `started_at` | string | ISO 8601 形式の開始日時 |

#### 備考

- `genre` はこのレスポンスだけでは欠けることがあるため、後段のジャンル API で補完する前提です。
- 同じ `series_site_id` でも `corner_site_id` が異なる複数行が返ることがあります。

---

### 2. `GET /app/v1/web/ondemand/series?genre={genre}`

- 実URL例: `https://www.nhk.or.jp/radio-api/app/v1/web/ondemand/series?genre=language`
- 用途: ジャンル別の番組一覧取得
- コード上の扱い:
  - `genre` 指定時の番組一覧取得
  - 全番組取得時の **新着 API にない番組の補完**
  - `genre_label` 付与
- 主配列: `series`

#### `genre` に使っている値

- `language`
- `music`
- `news`
- `drama`
- `sports`
- `documentary`
- `variety`

#### 観測できた主なフィールド

| Field | Type | Note |
|---|---|---|
| `series_site_id` | string | 番組 ID |
| `corner_site_id` | string | コーナー ID |
| `title` | string | 番組名 |
| `corner_name` | string | コーナー名 |
| `onair_date` | string | 放送日文字列 |
| `started_at` | string | 開始日時 |


## Normalization rules

レスポンスはそのまま使わず、以下のルールで正規化しています。

### ID

```text
site_id   = series_site_id ?? site_id
corner_id = corner_site_id ?? corner_id ?? "01"
```

### タイトル

```text
title = title ?? corner_name ?? "{site_id}_{corner_id}"
```

### 表示用タイトル

- `corner_name` が空でない
- かつ `corner_name != title`

のとき:

```text
display_title = "[{title}] {corner_name}"
```

それ以外は `title` をそのまま使用します。

### 日付

`onair_date` は表示用に `display_date` へ変換します。

- 入力例: `2026年4月15日(水)放送`
- 出力例: `2026-04-15(水)`

受け入れている形式は実装上以下です。

- `YYYY年MM月DD日`
- `YYYY-MM-DD`
- `YYYY/MM/DD`
- `YYYYMMDD`

### URL

詳細 URL は固定テンプレートで構築します。

```text
https://www.nhk.or.jp/radio/ondemand/detail.html?p={site_id}_{corner_id}
```

## Aggregation behavior

`fetch_program_list(None)` で全番組を取るときの実装は次の通りです。

1. `corners/new_arrivals` を取得
2. `corners` を `(series_site_id, corner_site_id)` で重複排除しつつ採用
3. 各 `genre` の `series?genre=...` を順に取得
4. `new_arrivals` に無い `(series_site_id, corner_site_id)` を追加
5. 既出番組で `genre` が空のものは、ジャンル API の値で補完

## Cache format

番組一覧は `.cache/programs/{genre or all}.json` に保存します。

```json
{
  "fetched_at": 1776250239.2524061,
  "genre": null,
  "programs": [
    {
      "title": "ラジオ英会話",
      "corner_name": "",
      "genre": "language",
      "genre_label": "語学",
      "site_id": "PMMJ59J6N2",
      "corner_id": "01",
      "onair_date": "2026年4月15日(水)放送",
      "display_date": "2026-04-15(水)",
      "display_title": "ラジオ英会話",
      "started_at": "2026-04-15T06:45:00+09:00",
      "url": "https://www.nhk.or.jp/radio/ondemand/detail.html?p=PMMJ59J6N2_01"
    }
  ]
}
```

## Request headers

実装では以下のヘッダーを付けています。

```http
User-Agent: Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36
Accept-Language: ja,en;q=0.9
```

## Reference: public API portal (`api-portal.nhk.or.jp`)

公開ポータルのサービス案内ページ:

- `https://api-portal.nhk.or.jp/service-guide`

このページでは、公開中 API として次が案内されています。

- `PgDateTvAPI`
- `PgGenreTvAPI`
- `PgNowTvAPI`
- `BroadcastEventTvAPI`
- `PgDateRadioAPI`
- `PgGenreRadioAPI`
- `PgNowRadioAPI`
- `BroadcastEventRadioAPI`

ラジオ向け公開 API の Resource URL は、少なくとも以下が確認できます。

| API | Resource URL |
|---|---|
| `PgNowRadioAPI` | `https://program-api.nhk.jp/v3/papiPgNowRadio?service={service_radio}&area={area}&key={apikey}` |
| `PgDateRadioAPI` | `https://program-api.nhk.jp/v3/papiPgDateRadio?service={service_radio}&area={area}&date={date}&key={apikey}` |
| `PgGenreRadioAPI` | `https://program-api.nhk.jp/v3/papiPgGenreRadio?service={service_radio}&area={area}&genre={genre}&date={date}&key={apikey}` |
| `BroadcastEventRadioAPI` | `https://program-api.nhk.jp/v3/papiBroadcastEventRadio?broadcastEventId={broadcastEventId}&key={apikey}` |

### このドキュメントとの関係

- `api-portal.nhk.or.jp` が公開しているのは **番組表 API** です。
- 本アプリが利用しているのは `https://www.nhk.or.jp/radio-api/app/v1/web/ondemand/...` 系の **聞き逃し番組一覧 API** です。
- 2026-04 時点で確認した範囲では、公開ポータル上に `ondemand` / `聞き逃し` API の説明ページは見当たりません。
- そのため、**公開ポータルの API と、本アプリが使っている聞き逃し系 API は別系統であり、後者は非掲載 API と見るのが自然** です。

## Limitations

- 公式の公開 API ドキュメントではありません。
- `api-portal.nhk.or.jp/service-guide` に載っている公開 API は番組表 API であり、本ドキュメントの `ondemand` 系 API はその掲載対象外です。
- フィールド追加・削除・意味変更の可能性があります。
- `genre` は `new_arrivals` 単体では安定しない前提で扱っています。
