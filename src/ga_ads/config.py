from pathlib import Path
import yaml

def load_config(path):
    path = Path(path)
    data = yaml.safe_load(path.read_text())
    data['_base_dir'] = str(path.parent.parent.resolve())
    return data

def resolve(cfg, key):
    base = Path(cfg['_base_dir'])
    cur = cfg
    for part in key.split('.'):
        cur = cur[part]
    p = Path(cur)
    return str(p if p.is_absolute() else base / p)
