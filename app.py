"""
MR Bot Dashboard — Flask BFF (Backend-for-Frontend)
Roda dentro do EKS/VPC, serve o HTML estático e faz proxy
das chamadas pro API Gateway Private (sem CORS, sem DNS problem).

Variáveis de ambiente:
  API_GATEWAY_URL   URL interna do API Gateway (Regional, resolúvel dentro da VPC)
                    ex: https://5su5qmyoqc.execute-api.sa-east-1.amazonaws.com/prod
  PORT              porta do servidor (default: 8080)
  LOG_LEVEL         DEBUG | INFO | WARNING (default: INFO)
"""
import logging
import os

import requests
from flask import Flask, Response, jsonify, request, send_from_directory
from flask_cors import CORS

logging.basicConfig(
    level=getattr(logging, os.environ.get("LOG_LEVEL", "INFO")),
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger("mr-dashboard")

API_GW_URL = os.environ.get(
    "API_GATEWAY_URL",
    "https://5su5qmyoqc.execute-api.sa-east-1.amazonaws.com/prod",
).rstrip("/")

app = Flask(__name__, static_folder="static", static_url_path="")
CORS(app, resources={r"/api/*": {"origins": "*"}})

# ── proxy timeout ──────────────────────────────────────────────────────────
TIMEOUT = int(os.environ.get("PROXY_TIMEOUT", "30"))

# ── proxy headers que NÃO devem ser repassados ─────────────────────────────
HOP_BY_HOP = {
    "connection", "keep-alive", "proxy-authenticate", "proxy-authorization",
    "te", "trailers", "transfer-encoding", "upgrade", "host",
    "content-length",   # requests calcula sozinho
}


def _forward_headers():
    """Repassa headers relevantes do request original."""
    return {
        k: v for k, v in request.headers
        if k.lower() not in HOP_BY_HOP
    }


# ── health ─────────────────────────────────────────────────────────────────
@app.get("/health")
@app.get("/healthz")
def health():
    return jsonify({"status": "ok", "upstream": API_GW_URL})


# ── proxy: GET /api/dashboard ──────────────────────────────────────────────
@app.get("/api/dashboard")
def proxy_dashboard():
    """
    Proxy transparente para GET {API_GW_URL}/mrs
    Aceita ?period=7|30|all e repassa pro upstream.
    Roda dentro da VPC: sem CORS, sem DNS externo, sem problema de Host header.
    """
    params = request.args.to_dict()
    target = f"{API_GW_URL}/mrs"

    logger.info("proxy → %s params=%s", target, params)

    try:
        resp = requests.get(
            target,
            params=params,
            headers=_forward_headers(),
            timeout=TIMEOUT,
            verify=True,    # valida TLS do API Gateway
        )
        logger.info("upstream %s → %d (%d bytes)", target, resp.status_code, len(resp.content))

        # devolve pro browser exatamente o que o API Gateway devolveu
        excluded = {"content-encoding", "transfer-encoding", "connection"}
        headers = {k: v for k, v in resp.headers.items() if k.lower() not in excluded}
        # adiciona CORS pra garantir (o browser bate no Flask, não no API GW)
        headers["Access-Control-Allow-Origin"] = "*"

        return Response(resp.content, status=resp.status_code, headers=headers)

    except requests.exceptions.Timeout:
        logger.error("timeout após %ds → %s", TIMEOUT, target)
        return jsonify({"error": "upstream_timeout", "message": f"API Gateway não respondeu em {TIMEOUT}s"}), 504

    except requests.exceptions.ConnectionError as e:
        logger.error("connection error → %s: %s", target, e)
        return jsonify({"error": "upstream_unreachable", "message": str(e)}), 502

    except Exception as e:
        logger.exception("proxy error")
        return jsonify({"error": "internal_error", "message": str(e)}), 500


# ── SPA fallback: serve index.html pra qualquer rota não-api ───────────────
@app.get("/")
@app.get("/<path:path>")
def spa(path=""):
    if path.startswith("api/"):
        return jsonify({"error": "not_found"}), 404
    return send_from_directory(app.static_folder, "index.html")


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    logger.info("Iniciando em :%d | upstream: %s", port, API_GW_URL)
    app.run(host="0.0.0.0", port=port, debug=False)
