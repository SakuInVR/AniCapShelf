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

字幕ストリームをサンプル調査します。

```powershell
python -m anicapshelf --db .\anicapshelf.db probe-subtitles --limit 40
```

録画1本から字幕の一部を抽出します。

```powershell
python -m anicapshelf --db .\anicapshelf.db extract-subtitles --recording-id 1 --seconds 120 --max-cues 50
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
2. キャプチャファイル名またはファイル更新時刻
3. キャプチャ時刻と録画時間帯の突き合わせ
4. 日本の録画TSに含まれることがある ARIB 字幕
5. 今後追加する OCR、画像特徴量、手動タグ

過去のキャプチャは、残っている証拠から可能な範囲で復元します。新しい
キャプチャについては、将来的に KonomiTV の視聴状態や再生位置を
キャプチャ時点で同時保存する「キャプチャ同時アノテート」を本命にします。

## ロードマップ

段階的な開発計画は [ROADMAP.md](ROADMAP.md) を参照してください。現在の
インデックス用プロトタイプから、キャプチャ同時アノテート、検索可能な
シーンカード、スマホでの共有体験までを順番に進めます。
