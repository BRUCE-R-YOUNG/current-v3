# Raspberry Pi側

担当: カメラ、本番推論、NumPy集計、画像蓄積、PCへのHTTP転送。
PC側の受信サーバー・学習は起動できません。

## 配布ZIPから起動

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-inference.txt
.venv/bin/python run.py init
```

生成される `config/edge.yaml` にカメラ、人物モデル、階数モデル、PCのHTTPS URLを設定します。`role: edge` を使用します。モデルファイルはZIPに含まれません。

```bash
export SVL_EDGE_TOKEN='PCと同じ共有トークン'
.venv/bin/python run.py production
```

別ターミナルで転送を起動します。

```bash
export SVL_EDGE_TOKEN='PCと同じ共有トークン'
.venv/bin/python run.py transfer
```

推論なしの撮影は `python run.py capture`。本番推論と同時には起動しません。収集・転送だけなら `requirements.txt` の依存関係だけで利用できます。

ソースリポジトリーから実行する場合は `python raspi/run.py ...` を使用します。配布ZIPには必要な `app/edge` 共通コードを同梱するため、PCフォルダーや元のリポジトリーは不要です。

キュー・ログは `config/runtime/edge/` に保存します。3秒5フレームの目標値、通信予算、ETAの仮定は同梱の `docs/v3-edge-pc.md` を参照してください。
