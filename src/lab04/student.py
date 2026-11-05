"""Ваші три функції. Дописуйте тут; решта коду — готова інфраструктура.
Порядок: read_file_batch → request_page → fetch_pages.
Контракти функцій та критерії приймання наведені у завданні й tests/lab04/.
"""
import csv
import hashlib
import io
import json
import logging
import time
import zipfile
from pathlib import Path
from typing import Any, Callable
import requests
from support import CSV_COLUMNS, save_response

LOG = logging.getLogger('lab04')


RETRY_STATUS = {429, 500, 502, 503, 504}
BACKOFF_SECONDS = (1, 2, 4)  # pauses after failed attempts no. 1, 2, 3
MAX_WAIT_SECONDS = 30
MAX_PAGES = 10_000
EVENTS_PATH = '/api/v1/delivery-events'


def read_file_batch(package_path: Path, student_id: str) -> dict[str, list[dict[str, str]]]:
    """Поверніть {'orders': [...], 'order_items': [...]}.
    1. Відкрийте ZIP, прочитайте PACKAGE_INFO.json, перевірте student_id.
    2. Перевірте наявність, size_bytes та sha256 ВСІХ записів manifest.
    3. Прочитайте orders.csv і order_items.csv з заголовками CSV_COLUMNS.
    4. Значення лишаються рядками; структурна помилка → ValueError.
    Не змінюйте ZIP, не пропускайте некоректні рядки мовчки.
    """
    with zipfile.ZipFile(package_path) as archive:  # read-only: the ZIP is never modified
        names = set(archive.namelist())
        if 'PACKAGE_INFO.json' not in names:
            raise ValueError('MISSING_MANIFEST')
        manifest = json.loads(archive.read('PACKAGE_INFO.json').decode('utf-8'))
        # the variant is identified by the manifest, not by the archive name
        if manifest.get('student_id') != student_id:
            raise ValueError('INVALID_STUDENT_ID')
        files = manifest.get('files')
        if not isinstance(files, list) or not files:
            raise ValueError('INVALID_MANIFEST')

        # completeness of the whole package: every listed file exists, has its size and SHA-256
        listed = set()
        for file_info in files:
            path = file_info.get('path') if isinstance(file_info, dict) else None
            if not isinstance(path, str) or path not in names:
                raise ValueError(f'MISSING_FILE:{path}')
            file_bytes = archive.read(path)
            if len(file_bytes) != file_info.get('size_bytes'):
                raise ValueError(f'INVALID_SIZE:{path}')
            if hashlib.sha256(file_bytes).hexdigest() != file_info.get('sha256'):
                raise ValueError(f'INVALID_CHECKSUM:{path}')
            listed.add(path)

        result = {}
        for source, columns in CSV_COLUMNS.items():
            name = f'{source}.csv'
            if name not in listed:
                raise ValueError(f'MISSING_IN_MANIFEST:{name}')
            text = archive.read(name).decode('utf-8-sig')
            reader = csv.reader(io.StringIO(text, newline=''), delimiter=',')
            header = next(reader, None)
            if header != columns:  # exact names and order
                raise ValueError(f'INVALID_HEADER:{name}')
            rows = []
            for row in reader:
                if len(row) != len(columns):  # no silent skipping or padding
                    raise ValueError(f'INVALID_ROW:{name}:line {reader.line_num}')
                rows.append(dict(zip(columns, row)))  # values stay strings, empty stays empty
            result[source] = rows
    LOG.info('file batch: %s', {k: len(v) for k, v in result.items()})
    return result


def _retry_after_seconds(response: requests.Response) -> int | None:
    """Retry-After in whole seconds (the format of this API); anything else -> None."""
    value = response.headers.get('Retry-After', '').strip()
    return int(value) if value.isdigit() else None


def request_page(session: requests.Session, url: str, *, params: dict,
                 headers: dict, timeout: tuple[float, float] = (3, 10),
                 max_attempts: int = 4,
                 sleep: Callable[[float], None] = time.sleep) -> requests.Response:
    """Поверніть Response лише для HTTP 200.
    Повторюйте тільки GET: 429, 500, 502, 503, 504, Timeout, ConnectionError.
    Після невдач №1/2/3: sleep(1/2/4). Для 429 врахуйте Retry-After (секунди).
    400/401/403/404/422 та інші постійні помилки — без повтору.
    Після 4 невдалих спроб киньте виняток. JSON тут не розбираємо.
    Обов’язково передавайте timeout й allow_redirects=False.
    sleep передається параметром, тому тести не чекають реальний час.
    """
    for attempt in range(1, max_attempts + 1):
        retry_after = None
        try:
            response = session.get(url, params=params, headers=headers,
                                   timeout=timeout, allow_redirects=False)
        except requests.exceptions.SSLError:
            # SSLError is a subclass of ConnectionError, so it is caught first and never retried
            LOG.error('attempt %d: TLS error, not retried', attempt)
            raise
        except (requests.Timeout, requests.ConnectionError) as exc:
            problem = type(exc).__name__
        else:
            code = response.status_code
            if code == 200:
                LOG.info('attempt %d: HTTP 200', attempt)
                return response
            if code not in RETRY_STATUS:
                # 4xx, redirects and other codes are permanent: the same request will fail again
                LOG.error('attempt %d: HTTP %d, permanent error, not retried', attempt, code)
                raise requests.HTTPError(f'HTTP_{code}', response=response)
            problem = f'HTTP {code}'
            if code == 429:
                retry_after = _retry_after_seconds(response)
        if attempt == max_attempts:
            LOG.error('attempt %d: %s, no attempts left', attempt, problem)
            raise RuntimeError(f'RETRIES_EXHAUSTED after {attempt} attempts: {problem}')
        delay = BACKOFF_SECONDS[min(attempt, len(BACKOFF_SECONDS)) - 1]
        if retry_after is not None:
            delay = max(delay, retry_after)
        if delay > MAX_WAIT_SECONDS:
            LOG.error('attempt %d: %s, required wait %s s is longer than %s s', attempt, problem, delay, MAX_WAIT_SECONDS)
            raise RuntimeError(f'RETRY_WAIT_TOO_LONG: {delay} s')
        LOG.warning('attempt %d: %s, retry in %s s', attempt, problem, delay)
        sleep(delay)
    raise RuntimeError('RETRIES_EXHAUSTED')  # only reached when max_attempts < 1


def _is_count(value: Any) -> bool:
    return type(value) is int and value >= 0  # bool is not accepted as a number


def fetch_pages(session: requests.Session, base_url: str, api_key: str,
                student_id: str, params: dict, raw_dir: Path,
                request_fn: Callable | None = None) -> dict[str, Any]:
    """Поверніть {'events': [...], 'page_count': int, 'total_count': int}.
    Використайте request_fn (або request_page) для кожної сторінки.
    Збережіть успішну відповідь через save_response ДО розбору JSON.
    next_cursor — непрозоре значення; завершуємо лише на null.
    Перевірте student_id, count, стабільний total_count, повтор курсора,
    структуру data, суму count. На цьому етапі НЕ прибирайте дублікати.
    Усі поля події збережіть. Жодного запису в PostgreSQL у цій функції.
    """
    request_fn = request_fn or request_page
    url = base_url.rstrip('/') + EVENTS_PATH
    headers = {'X-API-Key': api_key}  # the key lives only here, never in params, raw or logs
    query = dict(params)  # the caller's dict is not changed
    query.pop('cursor', None)  # the first request has no cursor
    events: list[dict[str, Any]] = []
    seen_cursors: set[str] = set()
    total_count = None
    page_no = 0

    while True:
        if page_no >= MAX_PAGES:
            raise ValueError(f'INVALID_PAGINATION: more than {MAX_PAGES} pages')
        response = request_fn(session, url, params=dict(query), headers=headers)
        page_no += 1
        save_response(response, raw_dir, page_no, query)  # raw body first, then parsing

        body = json.loads(response.content)
        if not isinstance(body, dict):
            raise ValueError(f'INVALID_ENVELOPE: page {page_no}')
        if body.get('student_id') != student_id:
            raise ValueError(f'INVALID_STUDENT_ID: page {page_no}')
        if body.get('schema_version') not in (1, 2) or type(body.get('schema_version')) is not int:
            raise ValueError(f'INVALID_SCHEMA_VERSION: page {page_no}')
        data = body.get('data')
        if not isinstance(data, list):
            raise ValueError(f'INVALID_DATA: page {page_no}')
        for event in data:
            if not isinstance(event, dict) or not isinstance(event.get('event_id'), str) \
                    or not event['event_id'].strip():
                raise ValueError(f'INVALID_EVENT: page {page_no}')
        if not _is_count(body.get('count')) or body['count'] != len(data):
            raise ValueError(f'INVALID_COUNT: page {page_no}')
        if not _is_count(body.get('total_count')):
            raise ValueError(f'INVALID_TOTAL_COUNT: page {page_no}')
        if total_count is None:
            total_count = body['total_count']
        elif body['total_count'] != total_count:
            raise ValueError(f'INVALID_TOTAL_COUNT: changed on page {page_no}')
        if 'next_cursor' not in body:
            raise ValueError(f'INVALID_CURSOR: page {page_no} has no next_cursor')
        next_cursor = body['next_cursor']
        if next_cursor is not None and (not isinstance(next_cursor, str) or not next_cursor):
            raise ValueError(f'INVALID_CURSOR: page {page_no}')

        events.extend(data)  # all fields, duplicates kept
        LOG.info('page %d: count=%d, total_count=%d, received so far=%d',
                 page_no, body['count'], total_count, len(events))
        if next_cursor is None:  # the end is null, not a short page
            break
        if next_cursor in seen_cursors:
            raise ValueError(f'INVALID_CURSOR: repeated on page {page_no}')
        seen_cursors.add(next_cursor)
        query['cursor'] = next_cursor  # opaque value, passed as is

    if len(events) != total_count:
        raise ValueError(f'INVALID_TOTAL: received {len(events)}, total_count {total_count}')
    return {'events': events, 'page_count': page_no, 'total_count': total_count}
