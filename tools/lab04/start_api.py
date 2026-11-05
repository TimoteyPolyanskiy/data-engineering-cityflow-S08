"""Локальний API з оригінального CityFlow v1.0; дані — лише вашого варіанта."""
import argparse
import os
from pathlib import Path
import uvicorn

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--variant', default='data/lab04_variant')
    parser.add_argument('--port', type=int, default=8000)
    args = parser.parse_args()
    folder = (Path(args.variant) / 'api').resolve()
    if not (folder / 'api_keys.json').is_file():
        parser.error(f'Немає даних API у {folder}; розпакуйте власний варіант.')
    os.environ['CITYFLOW_DATA_DIR'] = str(folder)
    os.environ['CITYFLOW_KEYS_FILE'] = str(folder / 'api_keys.json')
    os.environ['CITYFLOW_FAULTS_FILE'] = str(folder / 'faults.json')
    # Host 127.0.0.1: сервер доступний лише на вашому комп’ютері.
    uvicorn.run('cityflow_api_v1:app', host='127.0.0.1', port=args.port, log_level='warning')
