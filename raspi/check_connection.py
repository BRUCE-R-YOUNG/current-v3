"""Read-only receiver authentication check, including Tailscale Serve URLs."""
import argparse
import json
import os
from pathlib import Path
from urllib import error, request

from app.edge.config import EdgeConfig


def check(cfg):
    token = os.environ.get(cfg.token_env, '')
    if not cfg.server_url or not token:
        raise ValueError('Set server_url and the configured token environment variable')
    req = request.Request(cfg.server_url.rstrip('/') + '/v3/status',
                          headers={'Authorization': f'Bearer {token}'})
    with request.urlopen(req, timeout=cfg.timeout_seconds) as response:
        status = json.loads(response.read(1_000_000))
    if not isinstance(status, dict) or 'counts' not in status:
        raise ValueError('Unexpected receiver response')
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
    except (ValueError, OSError) as exc:
        parser.exit(1, f'Connection failed ({type(exc).__name__}); check config, VPN, DNS and receiver.\n')
    print('OK: authenticated receiver reachable. No images uploaded.')


if __name__ == '__main__':
    main()
