# KonomiTV 連携設計メモ

このメモは、AniCapShelf の「キャプチャ同時アノテート」を KonomiTV と
どうつなぐかを整理したものです。目的は、キャプチャ画像を保存した瞬間に
元の録画、作品、話数、動画内時刻へ戻れるだけのメタデータを同時保存することです。

## 調査対象

- 調査日: 2026-06-06
- 対象: KonomiTV 公開リポジトリ
- 確認リビジョン: `d9fe96a7c074a705b3157968c4a7e637d076bea7`

主に次のファイルを確認しました。

- [`server/app/routers/CapturesRouter.py`](https://github.com/tsukumijima/KonomiTV/blob/d9fe96a7c074a705b3157968c4a7e637d076bea7/server/app/routers/CapturesRouter.py)
- [`client/src/services/Captures.ts`](https://github.com/tsukumijima/KonomiTV/blob/d9fe96a7c074a705b3157968c4a7e637d076bea7/client/src/services/Captures.ts)
- [`client/src/services/player/managers/CaptureManager.ts`](https://github.com/tsukumijima/KonomiTV/blob/d9fe96a7c074a705b3157968c4a7e637d076bea7/client/src/services/player/managers/CaptureManager.ts)
- [`client/src/views/Videos/Watch.vue`](https://github.com/tsukumijima/KonomiTV/blob/d9fe96a7c074a705b3157968c4a7e637d076bea7/client/src/views/Videos/Watch.vue)
- [`client/src/services/Videos.ts`](https://github.com/tsukumijima/KonomiTV/blob/d9fe96a7c074a705b3157968c4a7e637d076bea7/client/src/services/Videos.ts)
- [`client/src/stores/PlayerStore.ts`](https://github.com/tsukumijima/KonomiTV/blob/d9fe96a7c074a705b3157968c4a7e637d076bea7/client/src/stores/PlayerStore.ts)
- [`client/src/services/player/PlayerController.ts`](https://github.com/tsukumijima/KonomiTV/blob/d9fe96a7c074a705b3157968c4a7e637d076bea7/client/src/services/player/PlayerController.ts)

## わかったこと

KonomiTV には、すでにキャプチャ画像をアップロードする API があります。
サーバー側は `/api/captures` の `POST` を持ち、JPEG/PNG の画像ファイルを
受け取って、KonomiTV 側のキャプチャ保存先へ書き込みます。ただし、現状で
送られているのは画像ファイルが中心で、録画ID、録画パス、再生位置のような
AniCapShelf が欲しい情報は一緒に保存されていません。

クライアント側では `Captures.uploadCapture(blob, filename)` が multipart で
画像を送信しています。キャプチャ処理の中心は `CaptureManager` にあり、
ここが AniCapShelf 連携の有力な差し込み点です。

録画視聴画面では `Videos.fetchVideo(video_id)` で録画番組情報を取得し、
`PlayerStore.recorded_program` に保持しています。この情報には KonomiTV 側の
録画番組ID、録画ファイル情報、タイトル、シリーズ名、話数、サブタイトル、
放送開始/終了時刻などが含まれます。

再生位置はプレイヤーの `video.currentTime` から取得できます。KonomiTV 側の
プレイヤー状態にも再生位置変更イベントがあり、録画視聴中の現在位置を
キャプチャ時点のメタデータとして扱える見込みがあります。

## 推奨方針

最初は KonomiTV 本体の保存仕様を大きく変えず、AniCapShelf 側に小さな
ローカルAPIを立てるのが堅いです。

1. KonomiTV の通常キャプチャ保存はそのまま残す。
2. KonomiTV のキャプチャ処理後に、同じ画像とメタデータを AniCapShelf へ送る。
3. AniCapShelf は画像とメタデータを同時に保存し、録画DBの既存情報と照合する。
4. 失敗しても KonomiTV 側の通常キャプチャは壊さない。

この形なら、KonomiTV の本体仕様に強く依存しすぎず、まず自分の録画PC環境で
実験できます。将来的に安定したら、KonomiTV 側へのオプション連携や
プラグイン的な配布を検討します。

## 最小API案

AniCapShelf 側に、まず次の API を追加します。

```http
POST /api/captures/annotated
Content-Type: multipart/form-data
```

multipart のフィールド案です。

| フィールド | 種別 | 必須 | 説明 |
| --- | --- | --- | --- |
| `image` | file | 必須 | JPEG/PNG/WebP のキャプチャ画像 |
| `metadata` | JSON文字列 | 必須 | キャプチャ時点のソース情報 |
| `tags` | JSON文字列 | 任意 | 初期タグ配列 |
| `note` | 文字列 | 任意 | ユーザーメモ |

`metadata` の最小構造です。

```json
{
  "source_app": "KonomiTV",
  "captured_at": "2026-06-06T12:34:56+09:00",
  "recorded_program_id": 123,
  "recorded_video_id": 456,
  "recording_file_path": "/recorded/anime/example.ts",
  "playback_position_seconds": 123.456,
  "title": "作品名",
  "series_title": "作品名",
  "episode_number": 5,
  "subtitle": "サブタイトル",
  "start_time": "2026-06-06T01:00:00+09:00",
  "end_time": "2026-06-06T01:30:00+09:00",
  "konomitv_url": "http://konomitv.example.local/videos/watch/123"
}
```

初期実装では、録画ファイルパスと再生位置が最重要です。KonomiTV 側のIDは
あとから KonomiTV へ戻るための補助情報として保存します。

## AniCapShelf 側の保存案

既存の `captures` と `recordings` は維持し、キャプチャ時点の外部情報は
別テーブルに分けるのが安全です。

```sql
CREATE TABLE capture_annotations (
  id INTEGER PRIMARY KEY,
  capture_id INTEGER NOT NULL,
  source_app TEXT NOT NULL,
  external_program_id TEXT,
  external_video_id TEXT,
  recording_file_path TEXT,
  playback_position_seconds REAL,
  source_url TEXT,
  metadata_json TEXT NOT NULL,
  created_at TEXT NOT NULL,
  FOREIGN KEY (capture_id) REFERENCES captures(id)
);
```

理由は、ShareX や手動インポート、将来の別プレイヤー連携でも同じ
`captures` を使い回せるからです。KonomiTV 固有の情報をカラムに直置きしすぎると、
あとで入力元が増えたときに責務が混ざります。

## 元シーンへ戻る方法

最初の段階では、次の2つを保存します。

- KonomiTV の録画視聴URL
- 動画内時刻秒 `playback_position_seconds`

KonomiTV が URL パラメータで直接シークできるかは、今回の調査だけでは
確定していません。そのため初期実装では「URLを開き、AniCapShelf側で秒数を表示する」
ところから始めます。直接シークURLやブラウザ拡張での自動シークは、動作確認後に
追加するのが安全です。

## 連携方式の比較

| 方式 | 良い点 | 注意点 |
| --- | --- | --- |
| AniCapShelf sidecar API | KonomiTV 本体への影響が小さい。失敗しても既存キャプチャを壊しにくい。 | KonomiTV 側に小さな差し込みコードが必要。CORSや認証を考える必要がある。 |
| KonomiTV の `/api/captures` 拡張 | 保存元が1つにまとまる。 | KonomiTV 本体仕様に踏み込む。上流変更の追従が必要。 |
| 後追い照合のみ | 既存ファイルだけで動く。 | 動画内時刻の精度が低く、夢の「キャプチャと同時に確定」から遠い。 |

現時点のおすすめは sidecar API です。まずは自分の環境で強い体験を作り、
安定してから配布方法を考えます。

## 最初の実験手順

1. AniCapShelf に `POST /api/captures/annotated` を追加する。
2. DBに `capture_annotations` を追加する。
3. KonomiTV の `CaptureManager` 相当の場所で、キャプチャ画像生成後に
   `recorded_program` と `video.currentTime` を読み取る。
4. 既存の KonomiTV キャプチャ保存を維持したまま、AniCapShelf API にも送る。
5. AniCapShelf の詳細表示または CLI で、録画パス、作品、話数、動画内時刻が
   保存されていることを確認する。

## リスク

- KonomiTV の内部APIやクライアント構造は将来変わる可能性があります。
- KonomiTV の認証、CORS、HTTPS設定によっては、ブラウザから AniCapShelf へ
  直接POSTできない場合があります。
- KonomiTV が見ている録画パスと AniCapShelf がインデックスしている録画パスが
  コンテナ内外で違う可能性があります。
- ライブ視聴と録画視聴では、取れるメタデータが変わります。最初は録画視聴を
  対象にするのが堅いです。
- キャプチャ画像そのものを二重保存するか、KonomiTV の保存ファイルを参照するかは
  運用方針で決める必要があります。

## 現在できているもの

次の最小構成は実装済みです。

1. AniCapShelf のローカルAPIサーバーを `serve-api` で起動する。
2. `POST /api/captures/annotated` で画像とJSONメタデータを保存する。
3. KonomiTV 連携用の最小クライアントスクリプトを `integrations/konomitv/` に置く。
4. ブラウザから送れるように、必要な KonomiTV origin だけを `--allow-origin` で
   許可する。
5. `export annotations` で保存したアノテーションをJSON/CSVとして確認する。

次は、キャプチャ詳細を人間が読みやすく確認できる `show-capture` と、
キャプチャ時のクイックタグ指定を追加します。
