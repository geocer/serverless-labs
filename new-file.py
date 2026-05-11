import requests
from datetime import datetime, timedelta, timezone

# --- Config ---
TFE_HOSTNAME = "https://tfe"
TFE_TOKEN = "123"
ORGANIZATION_NAME = "main"


def make_tfe_request(method, path, data=None):
    headers = {
        "Authorization": f"Bearer {TFE_TOKEN}",
        "Content-Type": "application/vnd.api+json",
    }

    url = f"{TFE_HOSTNAME}/api/v2/{path}"
    response = requests.request(method, url, headers=headers, json=data)
    response.raise_for_status()
    return response.json()


def project_matches(name):
    return name.upper().startswith("test")


def workspace_matches(name):
    name = name.upper()
    valid_suffixes = ("-test", "-te", "-tt")
    return name.startswith("test-") and name.endswith(valid_suffixes)


def resolve_user(run, user_cache):
    """
    Resolve usuário corretamente sem usar message
    """
    attrs = run["attributes"]

    # --- 1. created-by ---
    created_by = run["relationships"].get("created-by", {}).get("data")
    if created_by:
        user_id = created_by["id"]

        if user_id in user_cache:
            return user_cache[user_id]

        try:
            user_resp = make_tfe_request("GET", f"users/{user_id}")
            username = user_resp["data"]["attributes"].get("username", "unknown")
            user_cache[user_id] = username
            return username
        except:
            user_cache[user_id] = "unknown"
            return "unknown"

    # --- 2. VCS (Git) ---
    if attrs.get("vcs-revision"):
        vcs = attrs["vcs-revision"]
        return (
            vcs.get("commit-author")
            or vcs.get("commit-username")
            or vcs.get("commit-email")
            or "vcs-user"
        )

    # --- 3. fallback ---
    return "system/api"


def main():
    if not TFE_TOKEN:
        print("Erro: TFE_TOKEN não definido")
        return

    try:
        cutoff_date = datetime.now(timezone.utc) - timedelta(days=10)

        print("🔎 Buscando projetos...")
        projects = []
        path = f"organizations/{ORGANIZATION_NAME}/projects?page[size]=100"

        # --- PROJETOS ---
        while path:
            resp = make_tfe_request("GET", path)

            for proj in resp["data"]:
                if project_matches(proj["attributes"]["name"]):
                    projects.append(proj)

            path = resp.get("links", {}).get("next")
            if path:
                path = path.replace(f"{TFE_HOSTNAME}/api/v2/", "")

        print(f"✅ {len(projects)} projetos encontrados")

        print("\n🔎 Buscando todos os workspaces...")
        all_workspaces = []
        path = f"organizations/{ORGANIZATION_NAME}/workspaces?page[size]=100"

        # --- WORKSPACES (uma vez) ---
        while path:
            resp = make_tfe_request("GET", path)
            all_workspaces.extend(resp["data"])

            path = resp.get("links", {}).get("next")
            if path:
                path = path.replace(f"{TFE_HOSTNAME}/api/v2/", "")

        print(f"✅ {len(all_workspaces)} workspaces carregados")

        # --- INDEXAR WORKSPACES POR PROJETO ---
        ws_by_project = {}
        for ws in all_workspaces:
            proj_rel = ws["relationships"].get("project", {}).get("data")
            if not proj_rel:
                continue

            proj_id = proj_rel["id"]
            ws_by_project.setdefault(proj_id, []).append(ws)

        user_cache = {}

        # --- PROCESSAMENTO ---
        for proj in projects:
            proj_id = proj["id"]
            proj_name = proj["attributes"]["name"]

            print(f"\n📁 Projeto: {proj_name}")

            workspaces = ws_by_project.get(proj_id, [])

            for ws in workspaces:
                ws_name = ws["attributes"]["name"]

                if not workspace_matches(ws_name):
                    continue

                ws_id = ws["id"]
                print(f"\n  ✅ Workspace: {ws_name}")

                runs_path = f"workspaces/{ws_id}/runs?page[size]=50"

                while runs_path:
                    runs_resp = make_tfe_request("GET", runs_path)

                    for run in runs_resp["data"]:
                        attrs = run["attributes"]

                        # Apenas applies
                        if attrs["status"] != "applied":
                            continue

                        created_at = datetime.fromisoformat(
                            attrs["created-at"].replace("Z", "+00:00")
                        )

                        if created_at < cutoff_date:
                            continue

                        run_id = run["id"]

                        # --- USER ---
                        user = resolve_user(run, user_cache)

                        # --- OUTROS CAMPOS ---
                        source = attrs.get("source", "unknown")
                        message = attrs.get("message", "")

                        print(f"    - Run: {run_id}")
                        print(f"      Data: {created_at}")
                        print(f"      Usuário: {user}")
                        print(f"      Origem: {source}")

                        if message:
                            print(f"      Mensagem: {message}")

                    runs_path = runs_resp.get("links", {}).get("next")
                    if runs_path:
                        runs_path = runs_path.replace(
                            f"{TFE_HOSTNAME}/api/v2/", ""
                        )

    except Exception as e:
        print(f"Erro: {e}")


if __name__ == "__main__":
    main()
