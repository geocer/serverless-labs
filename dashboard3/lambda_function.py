"""
Lambda: mr-bot-dashboard-api
Rota: GET /mrs?period=7|30  (default 7)
Retorna agregações + lista de MRs do DynamoDB.

Schema DynamoDB:
  pk, sk, agent_summary, created_at, merged, mr_iid, mr_url,
  project_id, project_name, source_branch, status, target_branch, updated_at

Variáveis de ambiente:
  TABLE_NAME      -> nome da tabela DynamoDB
  ALLOWED_ORIGIN  -> origin permitida no CORS
  MAX_PERIOD_DAYS -> teto de dias aceito (default 90, evita scans gigantes)
"""
import os
import json
import logging
import re
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import boto3
from boto3.dynamodb.conditions import Attr

logger = logging.getLogger()
logger.setLevel(logging.INFO)

TABLE_NAME = os.environ.get("TABLE_NAME", "MergeRequestReviews")
ALLOWED_ORIGIN = os.environ.get("ALLOWED_ORIGIN", "*")
MAX_PERIOD_DAYS = int(os.environ.get("MAX_PERIOD_DAYS", "90"))

dynamodb = boto3.resource("dynamodb")
table = dynamodb.Table(TABLE_NAME)

CORS_HEADERS = {
    "Access-Control-Allow-Origin": ALLOWED_ORIGIN,
    "Access-Control-Allow-Methods": "GET,OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type,Authorization,x-api-key",
    "Content-Type": "application/json",
}


# ══════════════════════════════════════════════════════════════════════════
# Helpers
# ══════════════════════════════════════════════════════════════════════════
class DecimalEncoder(json.JSONEncoder):
    def default(self, o):
        if isinstance(o, Decimal):
            return int(o) if o % 1 == 0 else float(o)
        return super().default(o)


def _response(status: int, body) -> dict:
    return {
        "statusCode": status,
        "headers": CORS_HEADERS,
        "body": json.dumps(body, cls=DecimalEncoder, ensure_ascii=False),
    }


def _parse_period(period: str) -> tuple[str, int]:
    """
    Devolve (since_iso, days_back).
    A opção 'all' foi removida — só aceita inteiros até MAX_PERIOD_DAYS.
    """
    try:
        days = int(period)
    except (TypeError, ValueError):
        days = 7
    days = max(1, min(days, MAX_PERIOD_DAYS))
    since = datetime.now(timezone.utc) - timedelta(days=days)
    return since.isoformat(), days


def _normalize_status(raw: str) -> str:
    if not raw:
        return "pending"
    s = str(raw).lower()
    if "approv" in s:
        return "approved"
    if "reject" in s or "denied" in s or "block" in s:
        return "rejected"
    if "pend" in s or "review" in s or "wait" in s:
        return "pending"
    return s


# ══════════════════════════════════════════════════════════════════════════
# Gitflow classification
# ══════════════════════════════════════════════════════════════════════════
# Branches protegidas no gitflow tradicional
PROTECTED = ("master", "main", "release", "develop")

# Hierarquia de ambientes (índice menor = mais "baixo")
ENV_LEVEL = {
    "develop": 1,
    "release": 2,
    "master": 3,
    "main": 3,           # tratamos master e main como produção
}


def _branch_kind(name: str) -> str:
    """
    Classifica uma branch pelo padrão de nomenclatura gitflow.
    Retorna: feature | hotfix | bugfix | release | develop | master | other
    """
    if not name:
        return "other"
    n = name.strip().lower()
    # match em prefixos gitflow
    if n in ("master", "main"):
        return "master"
    if n == "develop":
        return "develop"
    if n == "release" or n.startswith("release/") or re.match(r"^release[-/].+", n):
        return "release"
    if n.startswith("feature/") or re.match(r"^feat(ure)?[-/].+", n):
        return "feature"
    if n.startswith("hotfix/") or re.match(r"^hotfix[-/].+", n):
        return "hotfix"
    if n.startswith("bugfix/") or re.match(r"^bugfix[-/].+", n):
        return "bugfix"
    return "other"


def _target_env(target: str) -> str | None:
    """
    Mapeia a target_branch pro ambiente correspondente.
    develop -> dev | release/* -> certification | master/main -> production
    """
    kind = _branch_kind(target)
    if kind == "develop":
        return "develop"
    if kind == "release":
        return "release"
    if kind == "master":
        return "master"
    return None


def _classify_flow(source: str, target: str) -> str:
    """
    Classifica a transição source→target em uma das categorias:
      - expected  : segue o fluxo gitflow esperado
      - hotfix    : hotfix/bugfix indo pra release/master (aceito)
      - skip-env  : pula um ambiente (ex: develop → master direto)
      - reverse   : target "mais baixo" que source (sincronização reversa)
      - unknown   : padrão fora do gitflow

    Regras consideradas "expected":
      feature/* → develop
      bugfix/*  → develop
      develop   → release
      release/* → master
      release/* → develop   (back-merge após release, normal no gitflow)
      master    → develop   (sincronia pós-release/hotfix)
    """
    src_kind = _branch_kind(source)
    tgt_kind = _branch_kind(target)

    # transições gitflow padrão
    expected_pairs = {
        ("feature", "develop"),
        ("bugfix", "develop"),
        ("develop", "release"),
        ("release", "master"),
        ("release", "develop"),
        ("master", "develop"),
    }
    if (src_kind, tgt_kind) in expected_pairs:
        return "expected"

    # hotfixes podem ir direto pra master ou release
    if src_kind in ("hotfix", "bugfix") and tgt_kind in ("master", "release"):
        return "hotfix"

    # pulos de ambiente: feature/develop indo direto pra master
    if src_kind in ("feature", "develop") and tgt_kind == "master":
        return "skip-env"
    if src_kind == "feature" and tgt_kind == "release":
        return "skip-env"

    # reverse: produção indo pra release (raro, mas pode ocorrer)
    src_lvl = ENV_LEVEL.get(src_kind)
    tgt_lvl = ENV_LEVEL.get(tgt_kind)
    if src_lvl and tgt_lvl and tgt_lvl < src_lvl and (src_kind, tgt_kind) not in expected_pairs:
        return "reverse"

    return "unknown"


# ══════════════════════════════════════════════════════════════════════════
# DynamoDB
# ══════════════════════════════════════════════════════════════════════════
def _scan_all(filter_expr=None):
    items = []
    kwargs = {}
    if filter_expr is not None:
        kwargs["FilterExpression"] = filter_expr
    while True:
        resp = table.scan(**kwargs)
        items.extend(resp.get("Items", []))
        lek = resp.get("LastEvaluatedKey")
        if not lek:
            break
        kwargs["ExclusiveStartKey"] = lek
    return items


# ══════════════════════════════════════════════════════════════════════════
# Aggregations
# ══════════════════════════════════════════════════════════════════════════
def _build_stats(items):
    by_status = Counter()
    by_project = Counter()
    merged = 0
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


def _build_branch_analysis(items):
    """
    Análise de gitflow: quantifica por ambiente alvo e por categoria
    de transição. Lista MRs problemáticos pra inspeção no dashboard.
    """
    by_target_env = Counter()           # develop / release / master / other
    by_flow_category = Counter()        # expected / hotfix / skip-env / reverse / unknown
    by_transition = Counter()           # ('feature','develop') -> N (top 10)

    inconsistencies = []                # MRs com skip-env/reverse/unknown

    for it in items:
        source = (it.get("source_branch") or "").strip()
        target = (it.get("target_branch") or "").strip()

        # ambiente alvo
        env = _target_env(target)
        by_target_env[env or "other"] += 1

        # categoria de fluxo (só faz sentido se tiver as duas branches)
        if source and target:
            cat = _classify_flow(source, target)
            by_flow_category[cat] += 1

            # transição genérica (feature → develop, etc) — sem nome de feature
            src_kind = _branch_kind(source)
            tgt_kind = _branch_kind(target)
            by_transition[f"{src_kind} → {tgt_kind}"] += 1

            # marca como inconsistência se NÃO for expected/hotfix
            if cat in ("skip-env", "reverse", "unknown"):
                inconsistencies.append({
                    "sk": it.get("sk"),
                    "mr_iid": it.get("mr_iid"),
                    "mr_url": it.get("mr_url"),
                    "project_name": it.get("project_name"),
                    "source_branch": source,
                    "target_branch": target,
                    "category": cat,
                    "created_at": it.get("created_at"),
                })

    # ordena top transições
    top_transitions = [
        {"transition": k, "count": v}
        for k, v in by_transition.most_common(10)
    ]

    return {
        "by_target_env": {
            "develop":  by_target_env.get("develop", 0),
            "release":  by_target_env.get("release", 0),
            "master":   by_target_env.get("master", 0),
            "other":    by_target_env.get("other", 0),
        },
        "by_flow_category": {
            "expected": by_flow_category.get("expected", 0),
            "hotfix":   by_flow_category.get("hotfix", 0),
            "skip-env": by_flow_category.get("skip-env", 0),
            "reverse":  by_flow_category.get("reverse", 0),
            "unknown":  by_flow_category.get("unknown", 0),
        },
        "top_transitions": top_transitions,
        "inconsistencies": inconsistencies[:50],   # cap pra não inflar payload
        "inconsistencies_total": len(inconsistencies),
    }


def _build_top_projects(items, limit=10):
    counter = Counter()
    name_for_id = {}
    for it in items:
        pid = str(it.get("project_id", ""))
        pname = it.get("project_name") or f"project-{pid}"
        counter[pid] += 1
        name_for_id[pid] = pname
    return [
        {"project_id": pid, "project_name": name_for_id[pid], "count": c}
        for pid, c in counter.most_common(limit)
    ]


def _build_timeline(items, days_back):
    buckets = defaultdict(lambda: {"total": 0, "approved": 0, "rejected": 0, "pending": 0})
    for it in items:
        raw = it.get("created_at") or it.get("updated_at")
        if not raw:
            continue
        try:
            d = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
        except ValueError:
            continue
        key = d.date().isoformat()
        st = _normalize_status(it.get("status"))
        buckets[key]["total"] += 1
        if st in buckets[key]:
            buckets[key][st] += 1

    today = datetime.now(timezone.utc).date()
    out = []
    for i in range(days_back - 1, -1, -1):
        day = (today - timedelta(days=i)).isoformat()
        b = buckets.get(day, {"total": 0, "approved": 0, "rejected": 0, "pending": 0})
        out.append({"date": day, **b})
    return out


def _filter_period(items, since_iso):
    out = []
    for it in items:
        raw = it.get("created_at") or it.get("updated_at")
        if raw and str(raw) >= since_iso:
            out.append(it)
    return out


def _slim_item(it):
    """Inclui source_branch e target_branch no payload da lista."""
    return {
        "pk": it.get("pk"),
        "sk": it.get("sk"),
        "agent_summary": it.get("agent_summary"),
        "created_at": it.get("created_at"),
        "updated_at": it.get("updated_at"),
        "merged": it.get("merged"),
        "mr_iid": it.get("mr_iid"),
        "mr_url": it.get("mr_url"),
        "project_id": it.get("project_id"),
        "project_name": it.get("project_name"),
        "source_branch": it.get("source_branch"),
        "target_branch": it.get("target_branch"),
        "status": it.get("status"),
    }


# ══════════════════════════════════════════════════════════════════════════
# Handler
# ══════════════════════════════════════════════════════════════════════════
def lambda_handler(event, context):
    method = (event.get("httpMethod")
              or event.get("requestContext", {}).get("http", {}).get("method")
              or "GET").upper()

    if method == "OPTIONS":
        return _response(200, {"ok": True})

    qs = event.get("queryStringParameters") or {}
    period = qs.get("period", "7")

    try:
        since_iso, days_back = _parse_period(period)

        # filtro server-side reduz tráfego (não 100% confiável pra todos os tipos,
        # então re-filtramos client-side abaixo)
        filter_expr = Attr("created_at").gte(since_iso) | Attr("updated_at").gte(since_iso)
        items = _scan_all(filter_expr)
        items = _filter_period(items, since_iso)

        items_sorted = sorted(
            items,
            key=lambda x: str(x.get("updated_at") or x.get("created_at") or ""),
            reverse=True,
        )

        body = {
            "period": period,
            "days_back": days_back,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "stats": _build_stats(items),
            "branch_analysis": _build_branch_analysis(items),
            "top_projects": _build_top_projects(items, limit=10),
            "timeline": _build_timeline(items, days_back),
            "items": [_slim_item(it) for it in items_sorted[:500]],
        }
        return _response(200, body)

    except Exception as e:
        logger.exception("dashboard error")
        return _response(500, {"error": "internal_error", "message": str(e)})
