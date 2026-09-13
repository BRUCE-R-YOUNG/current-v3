# Sustainable Vision Learning v3

[運用マニュアルの入口](docs/README.md)

1. [PC受信サーバー](docs/01-pc.md) を準備してプロジェクトを作成。
2. [Tailscale VPN](docs/02-tailscale.md) で別ネットワークを接続。
3. [Raspiの推論なしキャプチャーと定期送信](docs/03-capture-transfer.md) を開始。
4. 必要に応じて [推論と追加学習](docs/04-inference-training.md) を有効化。

配布は [Raspi用ZIP](svl-raspi.zip) と [PC用ZIP](svl-pc.zip) に分かれています。既存設定・モデル・保存データはZIPに含みません。

旧版は隣の previous-versions に保管しています。現行コードは raspi / pc です。仮想環境は機器間やフォルダ間で使い回さず、各環境で作成してください。
