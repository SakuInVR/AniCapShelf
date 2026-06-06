# AniCapShelf

AniCapShelf は、アニメのキャプチャ画像と録画アーカイブをつなぐ
ローカルファーストなシーン管理ツールです。キャプチャ画像を単なる
JPEG/PNGとして放置せず、元の録画ファイル、作品、話数、動画内時刻、
字幕、ユーザータグと結びつけて、あとから検索・整理・共有しやすい
「シーンカード」として扱うことを目指しています。

現在は小さな Python プロトタイプから始めています。

- `Z:\TV-Record` のようなフォルダから TS/m2ts 録画をインデックスする
- 日本語の録画ファイル名から録画開始時刻、番組名、話数らしき情報、
  `[字]` などのフラグを取り出す
- 番組名を正規化し、シリーズ名、話数番号、サブタイトルを可能な範囲で分離する
- `Z:\TV-Capture` のようなフォルダからキャプチャ画像をインデックスする
- 画像の撮影時刻と録画時間帯を使って、可能な範囲で元録画に紐づける
- `arib_caption` などの TS 字幕ストリームを検出する
- ffmpeg で録画から字幕テキストの一部を抽出する
- ShareX の履歴DBを取り込む

## クイックスタート

まずローカル設定ファイルを作ります。

```powershell
Copy-Item .\anicapshelf.example.toml .\anicapshelf.toml
```

`anicapshelf.toml` のパスを自分の環境に合わせて編集します。

```toml
[roots]
records = "Z:\\TV-Record"
captures = "Z:\\TV-Capture"

[sharex]
history_db = "Z:\\TV-Capture\\ShareX\\History.db"
```

設定ファイルを使う場合は、ルートパスの指定を省略できます。

```powershell
python -m anicapshelf --db .\anicapshelf.db scan-records
python -m anicapshelf --db .\anicapshelf.db scan-captures
python -m anicapshelf --db .\anicapshelf.db match
python -m anicapshelf --db .\anicapshelf.db report
```

未分類キャプチャを確認します。

```powershell
python -m anicapshelf --db .\anicapshelf.db review-unmatched --limit 50
```

複数の録画候補に当たっている曖昧なキャプチャを確認します。
候補の先頭には `best` または `candidate` が表示されます。確度スコアは、
録画時間内か、番組端に近すぎないか、前後猶予内か、複数候補があるかを使って
計算し、理由も保存します。

```powershell
python -m anicapshelf --db .\anicapshelf.db review-ambiguous --limit 20 --show-candidates
```

デバッグ用にDB内容を JSONL または CSV で出力します。

```powershell
python -m anicapshelf --db .\anicapshelf.db export matches --format jsonl --output .\matches.jsonl
python -m anicapshelf --db .\anicapshelf.db export captures --format csv --output .\captures.csv
python -m anicapshelf --db .\anicapshelf.db export annotations --format jsonl
python -m anicapshelf --db .\anicapshelf.db export ocr --format jsonl
```

キャプチャ1件の詳細を確認します。KonomiTV 連携で保存した元URL、
動画内時刻、録画パス、タグ、紐づいた前後字幕もここで見られます。
`source_jump` には、元URL、動画内秒数、タイムコード、開くときのヒントを
まとめて表示します。

```powershell
python -m anicapshelf --db .\anicapshelf.db show-capture 1
python -m anicapshelf --db .\anicapshelf.db show-capture 1 --format json
```

既存キャプチャに対して、`match` で選ばれた最有力録画候補から後追いの
アノテーションを作ります。古いスクリーンショットも、新しい
キャプチャ同時アノテートと近い形で `show-capture` から確認できます。

```powershell
python -m anicapshelf --db .\anicapshelf.db backfill-annotations --tag 後追い
```

キャプチャ画像の画面内文字をOCRします。現在のOCRエンジンは、PATH上の
`tesseract` コマンドを使います。OCR結果は `capture_ocr_results` に保存し、
TS字幕とは別の情報源として扱います。

```powershell
python -m anicapshelf --db .\anicapshelf.db ocr-captures --only-missing --language jpn+eng --verbose
```

タイトル、字幕、タグ、メモ、OCR結果を横断検索する検索インデックスを作ります。
字幕の `raw_text` はデバッグ用に残し、検索インデックスでは全角英数、
句読点、空白を正規化します。

```powershell
python -m anicapshelf --db .\anicapshelf.db rebuild-search-index
python -m anicapshelf --db .\anicapshelf.db search-text 魔法少女
python -m anicapshelf --db .\anicapshelf.db search-title 魔法少女
python -m anicapshelf --db .\anicapshelf.db near-capture 1
python -m anicapshelf --db .\anicapshelf.db search-text SNS候補 --format json
python -m anicapshelf --db .\anicapshelf.db search-text アイキャッチ
```

KonomiTV などの外部ツールから、画像とメタデータを同時保存するローカルAPIを
起動します。`--capture-output-root` を省略した場合は、設定ファイルの
`roots.captures` を保存先として使います。APIスタックは、依存を増やさない
標準ライブラリの `http.server` ベースです。

```powershell
python -m anicapshelf --db .\anicapshelf.db serve-api --host 127.0.0.1 --port 8765 --allow-origin http://127.0.0.1:7000
```

起動後、ブラウザで `http://127.0.0.1:8765/` を開くと、キャプチャグリッド、
タグ、コレクション、選択したキャプチャの詳細を確認できます。

`--api-token` または `ANICAPSHELF_API_TOKEN` を設定すると、POST API は
`Authorization: Bearer <token>` を要求します。スマホやKonomiTVから使う場合も、
ローカルネットワークへ公開するならトークンを設定してください。

最小APIは `POST /api/captures/annotated` です。`multipart/form-data` で
`image` と `metadata` JSON文字列を送ると、画像を保存し、
`capture_annotations` に録画ID、録画パス、再生位置などを残します。
`tags` または `quick_tags` は JSON配列かカンマ区切り文字列で送れます。
同じ録画パスの字幕がDBにあり、再生位置の前後に字幕が見つかった場合は、
時間窓内の字幕と、最も近い字幕キューの前後文脈を
`capture_subtitle_links` に自動で紐づけます。
KonomiTV 側へ差し込む最小クライアントは
[integrations/konomitv](integrations/konomitv) に置いています。

ブラウザUI向けの読み取りAPIも同じサーバーで提供します。

```text
GET /api/recordings
GET /api/captures
GET /api/captures/{capture_id}
GET /api/captures/{capture_id}/image
GET /api/matches?capture_id=1
GET /api/subtitles?recording_id=1
GET /api/tags
GET /api/collections
```

字幕ストリームをサンプル調査します。

```powershell
python -m anicapshelf --db .\anicapshelf.db probe-subtitles --limit 40
```

録画DBに ARIB 字幕の有無を保存します。

```powershell
python -m anicapshelf --db .\anicapshelf.db probe-recording-captions --only-unknown --limit 100
```

録画DBに ffprobe のストリーム情報を保存します。

```powershell
python -m anicapshelf --db .\anicapshelf.db probe-recording-streams --limit 100
```

録画1本から字幕の一部を抽出します。

```powershell
python -m anicapshelf --db .\anicapshelf.db extract-subtitles --recording-id 1 --seconds 120 --max-cues 50
```

字幕ありとして検出済みで、まだ字幕DBがない録画だけをまとめて処理します。
失敗した録画があっても次の録画へ進みます。

```powershell
python -m anicapshelf --db .\anicapshelf.db extract-subtitles-batch --only-with-arib --only-missing --seconds 1800 --verbose
```

録画ごとの字幕キューを時系列で確認します。`cue_index` は録画内の字幕順序です。

```powershell
python -m anicapshelf --db .\anicapshelf.db list-subtitles --recording-id 1
python -m anicapshelf --db .\anicapshelf.db list-subtitles --recording-id 1 --format json
```

ShareX の履歴を取り込みます。

```powershell
python -m anicapshelf --db .\anicapshelf.db import-sharex
```

コマンドラインから直接ルートを指定することもできます。

```powershell
python -m anicapshelf --db .\anicapshelf.db scan-records --records-root Z:\TV-Record
python -m anicapshelf --db .\anicapshelf.db scan-captures --captures-root Z:\TV-Capture
```

## テスト

```powershell
python -m pip install -e ".[dev]"
python -m pytest
```

## 現在の設計

AniCapShelf は、複数の情報源を「確度つきの証拠」として扱います。

1. 録画ファイル名から取れる録画開始時刻、番組名、話数、フラグ
   - 正規化タイトル、シリーズ名、話数番号、サブタイトルも保存します
2. キャプチャファイル名またはファイル更新時刻
3. キャプチャ時刻と録画時間帯の突き合わせ
4. 日本の録画TSに含まれることがある ARIB 字幕
5. OCR で読んだ画面内文字
6. 今後追加する画像特徴量、手動タグ

過去のキャプチャは、残っている証拠から可能な範囲で復元します。新しい
キャプチャについては、将来的に KonomiTV の視聴状態や再生位置を
キャプチャ時点で同時保存する「キャプチャ同時アノテート」を本命にします。

## ロードマップ

段階的な開発計画は [ROADMAP.md](ROADMAP.md) を参照してください。現在の
インデックス用プロトタイプから、キャプチャ同時アノテート、検索可能な
シーンカード、スマホでの共有体験までを順番に進めます。

KonomiTV と連携してキャプチャ時点の録画ID、録画パス、再生位置を保存する
設計メモは [docs/konomitv-integration.md](docs/konomitv-integration.md) に
まとめています。
