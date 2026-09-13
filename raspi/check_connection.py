"""Read-only receiver authentication check, including Tailscale Serve URLs."""
import argparse
import json
import os
from pathlib import Path
from urllib import error, request

from app.edge.config import EdgeConfig


class ConnectionCheckError(ValueError):
    """Diagnostic messages that never include credentials or server bodies."""


def check(cfg):
    token = os.environ.get(cfg.token_env, '')
    if not cfg.server_url.strip():
        raise ConnectionCheckError('server_url is empty. Set the PC receiver origin in your YAML config.')
    if not token.strip():
        raise ConnectionCheckError('Token is empty. Export the environment variable named by token_env in this terminal.')
    req = request.Request(cfg.server_url.rstrip('/') + '/v3/status',
                          headers={'Authorization': f'Bearer {token}'})
    with request.urlopen(req, timeout=cfg.timeout_seconds) as response:
        try:
            status = json.loads(response.read(1_000_000))
        except (ValueError, UnicodeError) as exc:
            raise ConnectionCheckError('Receiver returned non-JSON data. Check server_url and the proxy target.') from exc
    if not isinstance(status, dict) or 'counts' not in status:
        raise ConnectionCheckError('Unexpected receiver response. Use the v3 receiver origin without /v3 or /v3/ingest.')
    return status


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path,
                        default=Path(__file__).resolve().parent / 'config/edge.yaml')
    args = parser.parse_args()
    try:
        check(EdgeConfig.load(args.config))
    except error.HTTPError as exc:
        parser.exit(1, f'HTTP {exc.code}: check token, Serve target and receiver.\n')
    except ConnectionCheckError as exc:
        parser.exit(1, f'Connection failed: {exc}\n')
    except (ValueError, OSError) as exc:
        parser.exit(1, f'Connection failed ({type(exc).__name__}); check config, VPN, DNS and receiver.\n')
    print('OK: authenticated receiver reachable. No images uploaded.')


if __name__ == '__main__':
    main()
