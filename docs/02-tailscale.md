# 2. 別ネットワーク間のTailscale VPN転送

## 構成
```text
Raspi: capture -> SQLite queue -> HTTP uploader
                           |
                  Tailscale / HTTPS
                           |
PC: Tailscale Serve -> 127.0.0.1:8001 -> receiver -> review / training
```

両機器がインターネットへ接続できることが前提です。PCとPiを同じtailnetに参加させます。ルーターでアプリ用ポートを一般公開する構成にはしません。

## 手順
1. [公式インストール手順](https://tailscale.com/docs/install) に従い、Windows PCとRaspberry PiへTailscaleをインストールします。PiはOSに対応したLinuxパッケージを使用します。
2. PCでサインインし、Piで sudo tailscale up を実行して端末認証します。管理者の承認が必要な場合は承認後に進みます。
3. 両方で tailscale status を確認します。Piで tailscale ping PCの端末名 を実行し、接続を確認します。
4. PC受信サーバーを127.0.0.1:8001で起動します。
5. PCのターミナルで以下を実行します。

```powershell
tailscale serve --bg 8001
tailscale serve status
```

初回にHTTPS有効化の案内が出たら、表示される公式リンクに従って設定します。既存Serve設定があるPCでは、先に status で確認し、他のサービスの経路を上書きしないでください。

6. 表示された実際のHTTPS URLをPiの server_url に設定します。例のホスト名をそのまま使わないでください。

```yaml
server_url: 'https://PC-NAME.TAILNET-NAME.ts.net'
token_env: SVL_EDGE_TOKEN
```

末尾に /v3 や /v3/ingest は付けません。送信プログラムがAPIパスを付加します。

7. Piにアプリのトークンを設定し、接続確認します。

```bash
read -rsp 'PC access token: ' SVL_EDGE_TOKEN; echo
export SVL_EDGE_TOKEN
python check_connection.py --config config/edge.yaml
```

OK表示は認証付きstatus APIに到達したことを意味します。画像の受信成功までは保証しません。次の収集・送信手順で画像を1件以上送って確認してください。

## セキュリティと運用
Serveはtailnet内への公開です。インターネット一般公開になるFunnelは使用しません。Tailscaleのアクセス制御でPiからPCのHTTPSポート443と、必要な管理端末だけを許可してください。VPN経由でもアプリのトークンは省略しません。

Serveのバックグラウンド設定だけではPython受信サーバーは起動しません。PCのスリープ、再起動、VPN切断、認証期限切れも監視してください。不要になったServeは tailscale serve off で停止します。他サービスと共有するPCでは管理者と停止範囲を確認してください。

Tailscaleを通しても通信量は消費します。アプリの通信量予算はJSONと概算ヘッダー分で、VPN暗号化や中継の通信量を厳密に測定するものではありません。携帯回線の上限には余裕を取ってください。

## 代替: Tailscale IPへ直接HTTP
Serveが利用できない場合だけ、PCのTailscale IPを指定して起動します。

```powershell
.\.venv\Scripts\python.exe run.py dashboard --host 100.x.y.z --port 8001
```

Piの server_url は http://100.x.y.z:8001 です。実際のPCのTailscale IPへ置換します。HTTPでも機器間はVPN内で暗号化されますが、HTTPS Serveを優先します。WindowsファイアウォールはPiのTailscale IPからTCP8001だけを許可し、無効化しないでください。127.0.0.1へのバインドのままでは、この直接接続はできません。

## 公式情報
- [Tailscaleインストール](https://tailscale.com/docs/install)
- [Serveのポート転送とバックグラウンド動作](https://tailscale.com/docs/reference/examples/serve)
- [DNSとMagicDNS](https://tailscale.com/docs/reference/dns-in-tailscale)

確認日: 2026-09-13。この配布にはTailscale本体は含めません。実機のtailnet参加とVPN疎通は利用者環境で実施してください。
