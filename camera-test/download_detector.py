"""Download only pinned public weights; never download executable model code."""
import hashlib
import json
from pathlib import Path
import requests

MODEL = 'google/owlv2-base-patch16-ensemble'
REVISION = 'cfd3195ba4ea9592eec887ded089f4c08eff231d'
FILES = ['README.md', 'config.json', 'preprocessor_config.json', 'tokenizer_config.json',
         'special_tokens_map.json', 'added_tokens.json', 'merges.txt', 'vocab.json', 'model.safetensors']
DESTINATION = Path(__file__).resolve().parents[1] / 'models/owlv2'


def main():
    DESTINATION.mkdir(parents=True, exist_ok=True)
    records = {}
    for name in FILES:
        target = DESTINATION / name
        if not target.exists():
            partial = target.with_suffix(target.suffix+'.part')
            with requests.get(f'https://huggingface.co/{MODEL}/resolve/{REVISION}/{name}', stream=True, timeout=(20,120)) as response:
                response.raise_for_status()
                with partial.open('wb') as output:
                    for chunk in response.iter_content(1024*1024):
                        output.write(chunk)
            partial.replace(target)
        with target.open('rb') as source:
            digest=hashlib.file_digest(source,'sha256').hexdigest()
        records[name] = {'bytes':target.stat().st_size,'sha256':digest}
        print(f'{name}: {target.stat().st_size} bytes',flush=True)
    (DESTINATION/'download-manifest.json').write_text(json.dumps({'model':MODEL,'revision':REVISION,
        'license':'Apache-2.0 as declared in official model card','files':records},indent=2),encoding='utf-8')


if __name__=='__main__':
    main()
