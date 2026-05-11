"""
MR Bot Dashboard — Flask BFF
Serve HTML + proxy pra API Gateway + integração com Terraform Enterprise.

Endpoints:
  GET /              → index.html (SPA)
  GET /healthz       → healthcheck
  GET /api/dashboard → proxy pra API Gateway /mrs (merge requests)
  GET /api/applies   → applies do TFE (cache em memória, ver tfe_client.py)
"""
import logging
import os

import requests
from flask import Flask, Response, jsonify, request, send_from_directory
from flask_cors import CORS

from tfe_client import client as tfe_client

logging.basicConfig(
    level=getattr(logging, os.environ.get("LOG_LEVEL", "INFO")),
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger("mr-dashboard")

API_GW_URL = os.environ.get(
    "API_GATEWAY_URL",
    "https://5su5qmyoqc.execute-api.sa-east-1.amazonaws.com/prod",
).rstrip("/")

TIMEOUT = int(os.environ.get("PROXY_TIMEOUT", "30"))

HOP_BY_HOP = {
    "connection", "keep-alive", "proxy-authenticate", "proxy-authorization",
    "te", "trailers", "transfer-encoding", "upgrade", "host", "content-length",
}

app = Flask(__name__, static_folder="static", static_url_path="")
CORS(app, resources={r"/api/*": {"origins": "*"}})


def _forward_headers():
    return {k: v for k, v in request.headers if k.lower() not in HOP_BY_HOP}


# ── health ─────────────────────────────────────────────────────────────────
@app.get("/health")
@app.get("/healthz")
def health():
    return jsonify({"status": "ok", "upstream": API_GW_URL})


# ── proxy: MRs (API Gateway → Lambda → DynamoDB) ──────────────────────────
@app.get("/api/dashboard")
def proxy_dashboard():
    params = request.args.to_dict()
    target = f"{API_GW_URL}/mrs"
    logger.info("proxy → %s params=%s", target, params)
    try:
        resp = requests.get(target, params=params, headers=_forward_headers(),
                            timeout=TIMEOUT, verify=True)
        excluded = {"content-encoding", "transfer-encoding", "connection"}
        headers = {k: v for k, v in resp.headers.items() if k.lower() not in excluded}
        headers["Access-Control-Allow-Origin"] = "*"
        return Response(resp.content, status=resp.status_code, headers=headers)
    except requests.exceptions.Timeout:
        return jsonify({"error": "upstream_timeout"}), 504
    except requests.exceptions.ConnectionError as e:
        return jsonify({"error": "upstream_unreachable", "message": str(e)}), 502
    except Exception as e:
        logger.exception("proxy error")
        return jsonify({"error": "internal_error", "message": str(e)}), 500


# ── applies do Terraform Enterprise (servido do cache) ────────────────────
@app.get("/api/applies")
def applies():
    """
    Retorna applies recentes do TFE.
    Filtros opcionais via query string:
      ?project=<substring>    filtra project_name
      ?user=<substring>       filtra user
      ?workspace=<substring>  filtra workspace_name
      ?limit=<n>              limita a N registros mais recentes
    """
    snap = tfe_client.snapshot()
    applies_list = snap["applies"]

    proj_q = (request.args.get("project") or "").lower()
    user_q = (request.args.get("user") or "").lower()
    ws_q = (request.args.get("workspace") or "").lower()
    limit = request.args.get("limit", type=int)

    if proj_q:
        applies_list = [a for a in applies_list if proj_q in a["project_name"].lower()]
    if user_q:
        applies_list = [a for a in applies_list if user_q in a["user"].lower()]
    if ws_q:
        applies_list = [a for a in applies_list if ws_q in a["workspace_name"].lower()]
    if limit:
        applies_list = applies_list[:limit]

    by_user = {}
    by_project = {}
    by_source = {}
    for a in applies_list:
        by_user[a["user"]] = by_user.get(a["user"], 0) + 1
        by_project[a["project_name"]] = by_project.get(a["project_name"], 0) + 1
        by_source[a["source"]] = by_source.get(a["source"], 0) + 1

    return jsonify({
        "applies": applies_list,
        "stats": {
            "total": len(applies_list),
            "by_user": [{"name": k, "count": v} for k, v in
                        sorted(by_user.items(), key=lambda x: -x[1])],
            "by_project": [{"name": k, "count": v} for k, v in
                           sorted(by_project.items(), key=lambda x: -x[1])],
            "by_source": [{"name": k, "count": v} for k, v in
                          sorted(by_source.items(), key=lambda x: -x[1])],
        },
        "meta": {
            "last_refresh": snap["last_refresh"],
            "last_error": snap["last_error"],
            "refreshing": snap["refreshing"],
            "projects_count": snap["projects_count"],
            "workspaces_count": snap["workspaces_count"],
            "config": snap["config"],
        },
    })


# ── SPA fallback ──────────────────────────────────────────────────────────
@app.get("/")
@app.get("/<path:path>")
def spa(path=""):
    if path.startswith("api/"):
        return jsonify({"error": "not_found"}), 404
    return send_from_directory(app.static_folder, "index.html")


# ── bootstrap ──────────────────────────────────────────────────────────────
# Inicia o refresh em background quando o módulo é carregado.
# Vale tanto pra `flask run` quanto pra gunicorn workers.
tfe_client.start()


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    logger.info("Iniciando em :%d | upstream MRs: %s", port, API_GW_URL)
    app.run(host="0.0.0.0", port=port, debug=False)
