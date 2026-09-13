import hashlib
import json
import math
import time
import uuid
from pathlib import Path

import yaml

from .runtime import service_lock


def dataset_fingerprint(path):
    from app.dataset import IMAGE_EXTS, resolve_dataset_root
    raw = yaml.safe_load(path.read_text(encoding='utf-8'))
    root = resolve_dataset_root(path,raw)
    splits = {}
    fingerprints = {}
    for split in ('train','val'):
        entries = raw.get(split)
        if not entries:
            raise ValueError('A separate train and val split is required')
        images = []
        for entry in entries if isinstance(entries,list) else [entries]:
            target = Path(entry)
            target = target if target.is_absolute() else root/target
            if target.is_dir():
                images.extend(p.resolve() for p in target.rglob('*') if p.suffix.lower() in IMAGE_EXTS)
            elif target.suffix == '.txt':
                for line in target.read_text(encoding='utf-8').splitlines():
                    if line.strip():
                        item = Path(line.strip())
                        images.append((item if item.is_absolute() else target.parent/item).resolve())
            else:
                images.append(target.resolve())
        if not images:
            raise ValueError(f'{split} images are empty')
        splits[split] = set()
        for image in images:
            label = Path(*('labels' if part == 'images' else part for part in image.parts)).with_suffix('.txt')
            if not label.is_file():
                raise ValueError(f'Label file required (empty is allowed for negatives): {label}')
            digest = hashlib.sha256(image.read_bytes()).hexdigest()
            splits[split].add(digest)
            fingerprints[str(image)] = [digest, hashlib.sha256(label.read_bytes()).hexdigest()]
    if splits['train'] & splits['val']:
        raise ValueError('train/val contain identical images; freeze a separate validation set')
    return hashlib.sha256(json.dumps([raw,fingerprints],sort_keys=True).encode()).hexdigest()


def train(cfg,root,store):
    from app.config import load_config
    from app.platform import ProjectManager
    from app.policy import decide_promotion
    if cfg.role != 'server':
        raise ValueError('Training runs on the PC: set role=server')
    ctx = ProjectManager(load_config()).context(cfg.project_id)
    if not cfg.dataset_yaml:
        raise ValueError('Select an annotated dataset.yaml with frozen train/val splits')
    dataset = Path(cfg.dataset_yaml).resolve()
    fingerprint = dataset_fingerprint(dataset)
    stop = root/'train.stop'
    job = uuid.uuid4().hex
    with service_lock(ctx.paths.runs,'v3-train'):
        stop.unlink(missing_ok=True)
        initial_version = ctx.registry.current()['version']
        ctx.cfg.training.dataset_yaml = dataset
        ctx.cfg.training.epochs = cfg.epochs
        ctx.cfg.training.image_size = cfg.imgsz
        ctx.cfg.training.batch = cfg.batch
        ctx.cfg.training.workers = cfg.workers
        ctx.cfg.training.device = cfg.device
        ctx.paths.runs = ctx.paths.runs/'v3'/job
        def progress(percent,message):
            if stop.exists():
                raise RuntimeError('Training cancelled')
            store.state('train',dict(status='running',progress=percent,message=message,job_id=job))
        progress(0,'Evaluating the current model on frozen validation data')
        baseline = ctx.trainer.evaluate(initial_version)
        if baseline.get('map50') is None or not math.isfinite(baseline['map50']):
            raise ValueError('A finite baseline metric is required')
        result = ctx.trainer.train_candidate(progress)
        progress(98,'Comparing candidate against baseline')
        candidate = ctx.trainer.evaluate(result['candidate_version'])
        if dataset_fingerprint(dataset) != fingerprint:
            raise ValueError('Dataset changed during training; promotion blocked')
        if ctx.registry.current()['version'] != initial_version:
            raise ValueError('Current model changed during training; promotion blocked')
        score = candidate.get('map50')
        if score is None or not math.isfinite(score):
            raise ValueError('Candidate metric missing or non-finite')
        policy = ctx.cfg.promotion
        decision = decide_promotion(score,baseline['map50'],policy.min_map50,policy.max_map50_drop,policy.require_candidate_better_or_equal)
        report = dict(result,baseline=baseline,candidate=candidate,passed=decision.promote,reason=decision.reason,
                      dataset_fingerprint=fingerprint,parent_version=initial_version,promoted=False,job_id=job)
        if cfg.export_onnx and decision.promote:
            from ultralytics import YOLO
            report['onnx'] = str(YOLO(result['best_model']).export(format='onnx',imgsz=cfg.imgsz))
        if cfg.promote_if_passed and decision.promote:
            if stop.exists():
                raise RuntimeError('Training cancelled before promotion')
            ctx.registry.promote(result['candidate_version'])
            report['promoted'] = True
        ctx.paths.runs.mkdir(parents=True,exist_ok=True)
        (ctx.paths.runs/'report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
        store.state('train',dict(status='completed',progress=100,**report))


def label_received(cfg,root,store):
    from app.config import load_config
    from app.platform import ProjectManager
    from app.pipeline import infer_and_store_sample
    if cfg.role != 'server':
        raise ValueError('Labelling runs on the PC')
    with service_lock(root,'label'):
        with store.connect() as db:
            rows = [dict(r) for r in db.execute("SELECT * FROM events WHERE kind='image' AND imported=0 LIMIT 100")]
        for row in rows:
            if (root/'label.stop').exists():
                break
            meta = json.loads(row['payload'])
            ctx = ProjectManager(load_config()).context(meta['project_id'])
            source = 'edge:'+row['id']
            prior = ctx.db.one('SELECT id FROM samples WHERE source=?',(source,))
            if not prior:
                target = ctx.paths.incoming/f"edge-{row['id']}.jpg"
                target.write_bytes(row['image'])
                ctx.cfg.review.require_human_review = True
                infer_and_store_sample(ctx,target,source)
            with store.connect() as db:
                db.execute('UPDATE events SET imported=1 WHERE id=?',(row['id'],))
        store.state('label',dict(status='completed',processed=len(rows)))
