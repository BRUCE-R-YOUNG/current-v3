# PC: 受信・ダッシュボード・学習

- [マニュアル全体](docs/README.md)
- [PCセットアップとトークン](docs/01-pc.md)
- [Tailscale VPNで受信](docs/02-tailscale.md)
- [追加学習と評価](docs/04-inference-training.md)

```powershell
.\.venv\Scripts\python.exe run.py dashboard --host 127.0.0.1 --port 8001
```

事前に仮想環境と requirements.txt を準備します。受信だけなら学習用依存パッケージは不要です。

[ローカルダッシュボード](http://127.0.0.1:8001/v3)
