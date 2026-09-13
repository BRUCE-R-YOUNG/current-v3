import argparse
import os
from pathlib import Path

from .config import EdgeConfig


def main(argv=None, expected_role=None):
    parser = argparse.ArgumentParser(description='Sustainable Vision Learning v3')
    commands = {'edge':['init','production','capture','transfer'], 'server':['init','dashboard','train','label']}
    parser.add_argument('command',choices=commands.get(expected_role,['init','dashboard','production','capture','transfer','train','label']))
    parser.add_argument('--config',type=Path,default=Path('config/server.yaml' if expected_role == 'server' else 'config/edge.yaml'))
    parser.add_argument('--role',choices=[expected_role] if expected_role else ['edge','server'],default=expected_role or 'edge')
    parser.add_argument('--host',default='127.0.0.1')
    parser.add_argument('--port',type=int,default=8001)
    parser.add_argument('--once',action='store_true')
    parser.add_argument('--windows',type=int)
    args = parser.parse_args(argv)
    if args.command == 'init':
        if args.config.exists():
            parser.error('Configuration already exists; it will not be overwritten')
        EdgeConfig(role=args.role).save(args.config)
        print(args.config.resolve())
        return
    cfg = EdgeConfig.load(args.config)
    if expected_role and cfg.role != expected_role:
        parser.error(f'This entry point requires role={expected_role}')
    if args.command == 'dashboard':
        import secrets
        import uvicorn
        from .api import create_app
        from .runtime import service_root
        if not os.environ.get(cfg.token_env):
            token_file = service_root(args.config)/'access-token.txt'
            if not token_file.exists():
                token_file.write_text(secrets.token_urlsafe(32),encoding='utf-8')
                token_file.chmod(0o600)
            os.environ[cfg.token_env] = token_file.read_text(encoding='utf-8').strip()
            print(f'Local access token file: {token_file}')
        uvicorn.run(create_app(args.config),host=args.host,port=args.port)
        return
    from .runtime import service_root, service_lock
    from .store import Store
    root = service_root(args.config)
    store = Store(root/'events.sqlite3')
    (root/f'{args.command}.stop').unlink(missing_ok=True)
    store.state(args.command,dict(status='starting',pid=os.getpid()))
    try:
        if args.command in ('production','capture'):
            if cfg.role != 'edge':
                raise ValueError('Camera and inference run on Raspberry Pi: set role=edge')
            from .runtime import camera_service
            camera_service(cfg,root,store,args.command,args.windows)
        elif args.command == 'transfer':
            if cfg.role != 'edge':
                raise ValueError('Transfer runs on Raspberry Pi')
            from .runtime import transfer_service
            transfer_service(cfg,root,store,args.once)
        elif args.command == 'train':
            from .training import train
            with service_lock(root,'train'):
                train(cfg,root,store)
        elif args.command == 'label':
            from .training import label_received
            label_received(cfg,root,store)
        if args.command not in ('train','label'):
            store.state(args.command,dict(status='stopped'))
    except BaseException as exc:
        store.state(args.command,dict(status='failed',error=f'{type(exc).__name__}: {exc}'))
        raise


if __name__ == '__main__':
    main()
