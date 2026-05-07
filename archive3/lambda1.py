“””
Lambda: mr-bot-dashboard-api
Rota: GET /dashboard?period=7|30|all
Retorna agregações + lista de MRs do DynamoDB para alimentar o dashboard.

Variáveis de ambiente:
TABLE_NAME      -> nome da tabela DynamoDB
ALLOWED_ORIGIN  -> origin permitida no CORS (ex.: https://meu-bucket.s3-website-us-east-1.amazonaws.com)
use “*” apenas em dev.
“””
import os
import json
import logging
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import boto3
from boto3.dynamodb.conditions import Attr

logger = logging.getLogger()
logger.setLevel(logging.INFO)

TABLE_NAME = os.environ.get(“TABLE_NAME”, “mr-bot-history”)
ALLOWED_ORIGIN = os.environ.get(“ALLOWED_ORIGIN”, “*”)

dynamodb = boto3.resource(“dynamodb”)
table = dynamodb.Table(TABLE_NAME)

CORS_HEADERS = {
“Access-Control-Allow-Origin”: ALLOWED_ORIGIN,
“Access-Control-Allow-Methods”: “GET,OPTIONS”,
“Access-Control-Allow-Headers”: “Content-Type,Authorization,x-api-key”,
“Content-Type”: “application/json”,
}

# –––––––––––––––––––––––––––––––––––––

# Helpers

# –––––––––––––––––––––––––––––––––––––

class DecimalEncoder(json.JSONEncoder):
“”“DynamoDB devolve números como Decimal; precisa serializar.”””
def default(self, o):
if isinstance(o, Decimal):
if o % 1 == 0:
return int(o)
return float(o)
return super().default(o)

def _response(status: int, body) -> dict:
return {
“statusCode”: status,
“headers”: CORS_HEADERS,
“body”: json.dumps(body, cls=DecimalEncoder, ensure_ascii=False),
}

def _parse_period(period: str):
“”“Devolve (since_iso, days_back) ou (None, None) para ‘all’.”””
if period in (None, “”, “all”):
return None, None
try:
days = int(period)
except (TypeError, ValueError):
days = 7
days = max(1, min(days, 365))
since = datetime.now(timezone.utc) - timedelta(days=days)
return since.isoformat(), days

def _normalize_status(raw: str) -> str:
“”“Mapeia o status do bot para os 3 buckets do dashboard.”””
if not raw:
return “pending”
s = str(raw).lower()
if “approv” in s:
return “approved”
if “reject” in s or “denied” in s or “block” in s:
return “rejected”
if “pend” in s or “review” in s or “wait” in s:
return “pending”
return s  # devolve como veio se não bater (ex.: ‘merged’)

def _scan_all(filter_expr=None):
“”“Scan paginado completo (cuidado com tabelas grandes — ver nota no final).”””
items = []
kwargs = {}
if filter_expr is not None:
kwargs[“FilterExpression”] = filter_expr

```
while True:
    resp = table.scan(**kwargs)
    items.extend(resp.get("Items", []))
    lek = resp.get("LastEvaluatedKey")
    if not lek:
        break
    kwargs["ExclusiveStartKey"] = lek
return items
```

# –––––––––––––––––––––––––––––––––––––

# Aggregations

# –––––––––––––––––––––––––––––––––––––

def _build_stats(items):
by_status = Counter()
by_project = Counter()
merged = 0

```
for it in items:
    st = _normalize_status(it.get("status"))
    by_status[st] += 1
    if it.get("merged") in (True, "true", "True"):
        merged += 1
    pname = it.get("project_name") or f"project-{it.get('project_id', '?')}"
    by_project[pname] += 1

return {
    "total": len(items),
    "merged": merged,
    "by_status": {
        "approved": by_status.get("approved", 0),
        "rejected": by_status.get("rejected", 0),
        "pending":  by_status.get("pending", 0),
    },
    "unique_projects": len(by_project),
}
```

def _build_top_projects(items, limit=10):
counter = Counter()
name_for_id = {}
for it in items:
pid = str(it.get(“project_id”, “”))
pname = it.get(“project_name”) or f”project-{pid}”
counter[pid] += 1
name_for_id[pid] = pname

```
top = counter.most_common(limit)
return [
    {"project_id": pid, "project_name": name_for_id[pid], "count": c}
    for pid, c in top
]
```

def _build_timeline(items, days_back):
“””
Retorna uma lista [{date, total, approved, rejected, pending}, …]
para os últimos `days_back` dias (ou todos os dias com dados se days_back=None).
“””
buckets = defaultdict(lambda: {“total”: 0, “approved”: 0, “rejected”: 0, “pending”: 0})

```
for it in items:
    raw_date = it.get("created_at") or it.get("updated_at")
    if not raw_date:
        continue
    try:
        d = datetime.fromisoformat(str(raw_date).replace("Z", "+00:00"))
    except ValueError:
        continue
    key = d.date().isoformat()
    st = _normalize_status(it.get("status"))
    buckets[key]["total"] += 1
    if st in buckets[key]:
        buckets[key][st] += 1

if days_back:
    # garante que todos os dias do range apareçam (mesmo zerados)
    today = datetime.now(timezone.utc).date()
    out = []
    for i in range(days_back - 1, -1, -1):
        day = (today - timedelta(days=i)).isoformat()
        b = buckets.get(day, {"total": 0, "approved": 0, "rejected": 0, "pending": 0})
        out.append({"date": day, **b})
    return out

return [{"date": k, **v} for k, v in sorted(buckets.items())]
```

def _filter_period(items, since_iso):
if not since_iso:
return items
out = []
for it in items:
raw = it.get(“created_at”) or it.get(“updated_at”)
if raw and str(raw) >= since_iso:
out.append(it)
return out

def _slim_item(it):
“”“Remove campos pesados que o front não precisa na lista.”””
return {
“pk”: it.get(“pk”),
“sk”: it.get(“sk”),
“agent_summary”: it.get(“agent_summary”),
“created_at”: it.get(“created_at”),
“updated_at”: it.get(“updated_at”),
“merged”: it.get(“merged”),
“mr_iid”: it.get(“mr_iid”),
“mr_url”: it.get(“mr_url”),
“project_id”: it.get(“project_id”),
“project_name”: it.get(“project_name”),
“status”: it.get(“status”),
}

# –––––––––––––––––––––––––––––––––––––

# Handler

# –––––––––––––––––––––––––––––––––––––

def lambda_handler(event, context):
method = (event.get(“httpMethod”)
or event.get(“requestContext”, {}).get(“http”, {}).get(“method”)
or “GET”).upper()

```
if method == "OPTIONS":
    return _response(200, {"ok": True})

qs = event.get("queryStringParameters") or {}
period = qs.get("period", "7")

try:
    since_iso, days_back = _parse_period(period)

    # Filtro server-side reduz tráfego quando há muito histórico
    filter_expr = None
    if since_iso:
        filter_expr = Attr("created_at").gte(since_iso) | Attr("updated_at").gte(since_iso)

    items = _scan_all(filter_expr)
    # Defesa caso o filtro deixe passar algo (Attr aceita strings)
    items = _filter_period(items, since_iso)

    # Ordena por updated_at desc para a lista
    items_sorted = sorted(
        items,
        key=lambda x: str(x.get("updated_at") or x.get("created_at") or ""),
        reverse=True,
    )

    body = {
        "period": period,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "stats": _build_stats(items),
        "top_projects": _build_top_projects(items, limit=10),
        "timeline": _build_timeline(items, days_back),
        "items": [_slim_item(it) for it in items_sorted[:500]],  # cap de segurança
    }
    return _response(200, body)

except Exception as e:
    logger.exception("dashboard error")
    return _response(500, {"error": "internal_error", "message": str(e)})
