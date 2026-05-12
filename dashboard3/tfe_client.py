"""
Cliente Terraform Enterprise — busca applies recentes nos projetos/workspaces
com filtro por padrão de nome ("test-*" no exemplo) e cache em memória com TTL.

Estratégia:
  - Thread em background atualiza o cache a cada REFRESH_INTERVAL segundos.
  - Endpoint /api/applies serve do cache (resposta < 100ms).
  - Primeira request espera o cache encher (lazy init).
"""
import logging
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta, timezone
from typing import Any

import requests

logger = logging.getLogger("tfe-client")

# ── CONFIG ─────────────────────────────────────────────────────────────────
TFE_HOSTNAME = os.environ.get("TFE_HOSTNAME", "").rstrip("/")
TFE_TOKEN = os.environ.get("TFE_TOKEN", "")
TFE_ORGANIZATION = os.environ.get("TFE_ORGANIZATION", "main")
TFE_PROJECT_PREFIX = os.environ.get("TFE_PROJECT_PREFIX", "test").upper()
TFE_WS_PREFIX = os.environ.get("TFE_WS_PREFIX", "test-").upper()
TFE_WS_SUFFIXES = tuple(
    s.strip().upper() for s in os.environ.get("TFE_WS_SUFFIXES", "-test,-te,-tt").split(",")
)
LOOKBACK_DAYS = int(os.environ.get("TFE_LOOKBACK_DAYS", "10"))
REFRESH_INTERVAL = int(os.environ.get("TFE_REFRESH_INTERVAL", "300"))  # 5 min
HTTP_TIMEOUT = int(os.environ.get("TFE_HTTP_TIMEOUT", "30"))
PAGE_SIZE = 100


# ── MODELO ─────────────────────────────────────────────────────────────────
@dataclass
class ApplyRecord:
    run_id: str
    workspace_id: str
    workspace_name: str
    project_id: str
    project_name: str
    status: str
    created_at: str       # ISO 8601
    user: str
    source: str           # tfe-api, tfe-ui, tfe-vcs etc
    message: str = ""
    has_changes: bool = False


@dataclass
class CacheState:
    applies: list[dict[str, Any]] = field(default_factory=list)
    last_refresh: str | None = None
    last_error: str | None = None
    refreshing: bool = False
    projects_count: int = 0
    workspaces_count: int = 0


# ── CLIENTE ────────────────────────────────────────────────────────────────
class TFEClient:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"Bearer {TFE_TOKEN}",
            "Content-Type": "application/vnd.api+json",
        })
        self._cache = CacheState()
        self._lock = threading.RLock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    # -- HTTP helpers ------------------------------------------------------
    def _request(self, method: str, path: str) -> dict:
        url = f"{TFE_HOSTNAME}/api/v2/{path}"
        resp = self.session.request(method, url, timeout=HTTP_TIMEOUT)
        resp.raise_for_status()
        return resp.json()

    def _paginate(self, initial_path: str):
        """Iterador que segue links.next paginando os resultados."""
        path = initial_path
        while path:
            resp = self._request("GET", path)
            for item in resp.get("data", []):
                yield item
            next_url = resp.get("links", {}).get("next")
            path = next_url.replace(f"{TFE_HOSTNAME}/api/v2/", "") if next_url else None

    # -- filtros configuráveis ---------------------------------------------
    @staticmethod
    def _project_matches(name: str) -> bool:
        return name.upper().startswith(TFE_PROJECT_PREFIX)

    @staticmethod
    def _workspace_matches(name: str) -> bool:
        n = name.upper()
        return n.startswith(TFE_WS_PREFIX) and n.endswith(TFE_WS_SUFFIXES)

    # -- resolução de usuário ---------------------------------------------
    def _resolve_user(self, run: dict, user_cache: dict[str, str]) -> str:
        """
        Resolve usuário a partir de created-by; fallback pra VCS / system.
        Thread-safe via lock externo (chamado pelo refresh loop).
        """
        attrs = run.get("attributes", {})

        created_by = run.get("relationships", {}).get("created-by", {}).get("data")
        if created_by:
            user_id = created_by["id"]
            cached = user_cache.get(user_id)
            if cached:
                return cached
            try:
                user_resp = self._request("GET", f"users/{user_id}")
                username = user_resp["data"]["attributes"].get("username") or "unknown"
                user_cache[user_id] = username
                return username
            except Exception as e:
                logger.warning("falha ao resolver user %s: %s", user_id, e)
                user_cache[user_id] = "unknown"
                return "unknown"

        # vcs-revision na API do TFE é um STRING (hash), não dict.
        # autor/email vivem em ingress-attributes do configuration-version.
        # pra simplificar, marcamos como vcs e podemos enriquecer depois.
        if attrs.get("vcs-revision"):
            return "vcs"

        if attrs.get("source") == "tfe-api":
            return "system/api"

        return "unknown"

    # -- carregamento principal --------------------------------------------
    def _fetch_all(self) -> tuple[list[ApplyRecord], int, int]:
        if not TFE_TOKEN or not TFE_HOSTNAME:
            raise RuntimeError("TFE_TOKEN ou TFE_HOSTNAME não configurados")

        cutoff = datetime.now(timezone.utc) - timedelta(days=LOOKBACK_DAYS)

        # 1) projetos
        projects = [
            p for p in self._paginate(
                f"organizations/{TFE_ORGANIZATION}/projects?page[size]={PAGE_SIZE}"
            )
            if self._project_matches(p["attributes"]["name"])
        ]
        logger.info("projetos filtrados: %d", len(projects))

        # 2) workspaces (uma vez só, indexa por projeto)
        all_ws = list(self._paginate(
            f"organizations/{TFE_ORGANIZATION}/workspaces?page[size]={PAGE_SIZE}"
        ))
        ws_by_project: dict[str, list[dict]] = {}
        for ws in all_ws:
            proj_rel = ws["relationships"].get("project", {}).get("data")
            if proj_rel:
                ws_by_project.setdefault(proj_rel["id"], []).append(ws)
        logger.info("workspaces totais: %d", len(all_ws))

        # 3) runs por workspace filtrado
        records: list[ApplyRecord] = []
        user_cache: dict[str, str] = {}
        user_resolution_jobs: list[tuple[ApplyRecord, dict]] = []

        for proj in projects:
            proj_id = proj["id"]
            proj_name = proj["attributes"]["name"]

            for ws in ws_by_project.get(proj_id, []):
                ws_name = ws["attributes"]["name"]
                if not self._workspace_matches(ws_name):
                    continue
                ws_id = ws["id"]

                runs_path = f"workspaces/{ws_id}/runs?page[size]=50"
                stop_paging = False
                while runs_path and not stop_paging:
                    resp = self._request("GET", runs_path)

                    for run in resp["data"]:
                        attrs = run["attributes"]
                        if attrs.get("status") != "applied":
                            continue

                        try:
                            created_at = datetime.fromisoformat(
                                attrs["created-at"].replace("Z", "+00:00")
                            )
                        except (KeyError, ValueError):
                            continue

                        # runs vêm ordenados desc por data → para de paginar
                        # quando passa do cutoff
                        if created_at < cutoff:
                            stop_paging = True
                            break

                        record = ApplyRecord(
                            run_id=run["id"],
                            workspace_id=ws_id,
                            workspace_name=ws_name,
                            project_id=proj_id,
                            project_name=proj_name,
                            status=attrs["status"],
                            created_at=created_at.isoformat(),
                            user="...",  # resolvido depois (paralelo)
                            source=attrs.get("source", "unknown"),
                            message=attrs.get("message", "") or "",
                            has_changes=attrs.get("has-changes", False),
                        )
                        records.append(record)
                        user_resolution_jobs.append((record, run))

                    next_url = resp.get("links", {}).get("next")
                    runs_path = (
                        next_url.replace(f"{TFE_HOSTNAME}/api/v2/", "")
                        if next_url and not stop_paging else None
                    )

        # 4) resolve users em paralelo (limita pra não martelar o TFE)
        logger.info("resolvendo %d users em paralelo...", len(user_resolution_jobs))
        with ThreadPoolExecutor(max_workers=8) as pool:
            futures = {
                pool.submit(self._resolve_user, run, user_cache): record
                for record, run in user_resolution_jobs
            }
            for fut, record in futures.items():
                try:
                    record.user = fut.result()
                except Exception as e:
                    logger.warning("user lookup falhou: %s", e)
                    record.user = "unknown"

        # 5) ordena: mais recente primeiro
        records.sort(key=lambda r: r.created_at, reverse=True)
        return records, len(projects), len(all_ws)

    # -- background refresh -------------------------------------------------
    def _refresh_loop(self):
        while not self._stop.is_set():
            try:
                with self._lock:
                    self._cache.refreshing = True

                logger.info("iniciando refresh do TFE...")
                start = time.time()
                records, n_proj, n_ws = self._fetch_all()
                duration = time.time() - start
                logger.info("refresh concluído em %.1fs (%d applies)", duration, len(records))

                with self._lock:
                    self._cache.applies = [asdict(r) for r in records]
                    self._cache.last_refresh = datetime.now(timezone.utc).isoformat()
                    self._cache.last_error = None
                    self._cache.projects_count = n_proj
                    self._cache.workspaces_count = n_ws

            except Exception as e:
                logger.exception("erro no refresh do TFE")
                with self._lock:
                    self._cache.last_error = str(e)

            finally:
                with self._lock:
                    self._cache.refreshing = False

            self._stop.wait(REFRESH_INTERVAL)

    def start(self):
        if self._thread and self._thread.is_alive():
            return
        logger.info("iniciando thread de refresh TFE (intervalo=%ds)", REFRESH_INTERVAL)
        self._thread = threading.Thread(target=self._refresh_loop, daemon=True, name="tfe-refresh")
        self._thread.start()

    def stop(self):
        self._stop.set()

    # -- API pra o Flask ----------------------------------------------------
    def snapshot(self) -> dict:
        with self._lock:
            return {
                "applies": list(self._cache.applies),
                "last_refresh": self._cache.last_refresh,
                "last_error": self._cache.last_error,
                "refreshing": self._cache.refreshing,
                "projects_count": self._cache.projects_count,
                "workspaces_count": self._cache.workspaces_count,
                "config": {
                    "lookback_days": LOOKBACK_DAYS,
                    "refresh_interval_seconds": REFRESH_INTERVAL,
                    "project_prefix": TFE_PROJECT_PREFIX,
                    "ws_prefix": TFE_WS_PREFIX,
                    "ws_suffixes": list(TFE_WS_SUFFIXES),
                },
            }


# instância singleton — importada pelo app.py
client = TFEClient()
