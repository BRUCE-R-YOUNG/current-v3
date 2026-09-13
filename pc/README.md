# PC側

担当: 認証付き受信API、ダッシュボード、疑似ラベル生成、追加学習・評価。
Piのカメラ・本番推論・転送プロセスはこの起動コードから実行できません。

## 配布ZIPから起動

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-training.txt
.\.venv\Scripts\python.exe run.py init
.\.venv\Scripts\python.exe run.py dashboard
```

ダッシュボードは `http://127.0.0.1:8001/v3`。設定は `config/server.yaml`、DBとログは `config/runtime/server/` です。既存プロジェクト・モデル・画像・パスワードはZIPに含めません。

受信・画面確認だけなら `requirements.txt` のみで実行できます。学習は `python run.py train`、疑似ラベル生成は `python run.py label`。ソースリポジトリーでは `python pc/run.py ...` を使用します。

## アクセストークン

このシステム専用の共有認証キーです。OpenAIのAPIキーではありません。

- ブラウザー: ダッシュボードの接続欄に入力します。
- Raspberry Pi: `SVL_EDGE_TOKEN` 環境変数に同じ値を設定します。
- PC: 同じ値で送信元を確認します。異なる場合は401エラーです。

環境変数未設定でダッシュボードを起動すると `config/runtime/server/access-token.txt` にランダムなキーを生成します。このファイルの中身が現在のトークンです。

自分でトークンを指定する場合は、起動前に設定します。

```powershell
$env:SVL_EDGE_TOKEN = '自分で生成した長いランダム文字列'
.\.venv\Scripts\python.exe run.py dashboard
```

キーを変える際はPCのサーバーを再起動し、Pi側とブラウザー側の設定も更新してください。キーはGit・配布ZIPには含めません。別ネットワークへの接続方法は `docs/v3-edge-pc.md` を参照してください。
