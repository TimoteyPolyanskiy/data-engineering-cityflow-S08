# data/raw — незмінні первинні дані

Каталог заповнюється командою `uv run python scripts/prepare_raw.py <каталог або zip з архівами S08>`
і **не комітиться** (див. `.gitignore`; виняток — цей файл).

```
data/raw/
├── base_v1/              # cityflow_S08_base_v1.zip: customers, merchants, products, orders, PACKAGE_INFO.json, README.txt
└── lab02_relational/     # cityflow_S08_lab02_relational_v1.zip: order_items, payments, refunds, couriers, deliveries, service_zones, ...
```

Назви пакетів, `student_id`, SHA-256 архівів і файлів записуються в `docs/package_checksums.json`.
SHA-256 архіву `base_v1` звіряється з файлом, наданим викладачем; файли звіряються з `PACKAGE_INFO.json`.
Пакети різних SXX не змішуються. Файли вручну не редагуються: усі виправлення робляться кодом над копіями.
Невеликі синтетичні вибірки (до 100 рядків) лежать у `data/sample/`.
