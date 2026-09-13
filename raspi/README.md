# Raspberry Pi: 収集・送信

モデルなしで画像を収集し、別プロセスでPCへ定期送信できます。

- [マニュアル全体](docs/README.md)
- [Tailscale VPNの準備](docs/02-tailscale.md)
- [推論なしキャプチャー・送信・自動起動](docs/03-capture-transfer.md)
- [モデルを使う推論](docs/04-inference-training.md)

```bash
python auto_capture.py --config config/edge.yaml
```

別ターミナルでトークン設定後:

```bash
python check_connection.py --config config/edge.yaml
python periodic_transfer.py --config config/edge.yaml
```

事前に requirements.txt のインストールと設定が必要です。両プロセスに同じ設定ファイルを指定します。Ctrl+Cで停止します。
