# api/zoho_workdrive.py
# Integração com Zoho WorkDrive (EU).
# Funções:
#   refresh_workdrive_token()   — renova o access_token WorkDrive via refresh_token
#   upload_factura_files(...)   — cria subpasta e faz upload dos 4 ficheiros

import asyncio
import json
import os
import tempfile
from typing import Literal

import httpx

from api.models import ExtractionResponseAI

_WD_BASE   = "https://www.zohoapis.eu/workdrive/api/v1"
_WD_UPLOAD = "https://www.zohoapis.eu/workdrive/api/v1/upload"

_EXCLUDE_FIELDS = {"api_ok", "api_error", "fichero_json"}


async def refresh_workdrive_token() -> str:
    """Renova o ZOHO_WORKDRIVE_ACCESS_TOKEN usando o ZOHO_WORKDRIVE_REFRESH_TOKEN."""
    url = "https://accounts.zoho.eu/oauth/v2/token"
    params = {
        "grant_type":    "refresh_token",
        "client_id":     os.getenv("ZOHO_CLIENT_ID"),
        "client_secret": os.getenv("ZOHO_CLIENT_SECRET"),
        "refresh_token": os.getenv("ZOHO_WORKDRIVE_REFRESH_TOKEN"),
    }
    async with httpx.AsyncClient() as client:
        r = await client.post(url, params=params)
        r.raise_for_status()
        token = r.json()["access_token"]
        os.environ["ZOHO_WORKDRIVE_ACCESS_TOKEN"] = token
        return token


def _is_invalid_token(r: httpx.Response) -> bool:
    """Zoho WorkDrive devolve 500 com código F7003 quando o token é inválido/expirado."""
    if r.status_code != 500:
        return False
    try:
        errors = r.json().get("errors", [])
        return any(e.get("id") == "F7003" for e in errors)
    except Exception:
        return False


async def _create_folder(
    parent_id: str,
    name: str,
    token: str,
    client: httpx.AsyncClient,
) -> str | None | Literal["UNAUTHORIZED"]:
    """Cria subpasta no WorkDrive. Devolve o folder id, 'UNAUTHORIZED' em 401, None noutros erros."""
    headers = {
        "Authorization": f"Zoho-oauthtoken {token}",
        "Content-Type":  "application/json",
    }
    body = {
        "data": {
            "attributes": {"name": name, "parent_id": parent_id},
            "type": "files",
        }
    }
    r = await client.post(f"{_WD_BASE}/files", json=body, headers=headers)
    if r.status_code == 401 or _is_invalid_token(r):
        return "UNAUTHORIZED"
    if r.status_code not in (200, 201):
        print(f"  ⚠️  WorkDrive create_folder HTTP {r.status_code}: {r.text[:200]}")
        return None
    return r.json()["data"]["id"]


async def _upload_file(
    folder_id: str,
    filename: str,
    content: bytes,
    token: str,
    client: httpx.AsyncClient,
) -> bool | Literal["UNAUTHORIZED"]:
    """Faz upload de um ficheiro para uma pasta do WorkDrive (multipart form)."""
    headers = {"Authorization": f"Zoho-oauthtoken {token}"}
    data    = {"filename": filename, "parent_id": folder_id}
    files   = {"content": (filename, content)}
    r = await client.post(_WD_UPLOAD, headers=headers, data=data, files=files)
    if r.status_code == 401 or _is_invalid_token(r):
        return "UNAUTHORIZED"
    if r.status_code not in (200, 201):
        print(f"  ⚠️  WorkDrive upload '{filename}' HTTP {r.status_code}: {r.text[:300]}")
        return False
    return True


def _extract_parser_sync(pdf_path: str) -> dict:
    """Corre o pipeline de parsers (síncrono) e devolve o dict de campos."""
    from extractor import extract_from_pdf
    res = extract_from_pdf(pdf_path)
    return {**res.fields, "api_ok": res.api_ok, "api_error": res.api_error}


async def _run_parser(pdf_bytes: bytes, nomedopdf: str) -> bytes | None:
    """
    Guarda o PDF num ficheiro temporário, corre o parser num thread executor
    (para não bloquear o event loop) e devolve o JSON como bytes.
    Devolve None se o parser falhar.
    """
    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
            tmp.write(pdf_bytes)
            tmp_path = tmp.name

        loop = asyncio.get_event_loop()
        fields = await loop.run_in_executor(None, _extract_parser_sync, tmp_path)
        print(f"  ✅  Parser extracção concluída: {nomedopdf}")
        return json.dumps(fields, ensure_ascii=False, indent=2).encode("utf-8")

    except Exception as exc:
        print(f"  ⚠️  Parser extracção falhou: {exc}")
        return None

    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.unlink(tmp_path)


async def upload_factura_files(
    nomedopdf:       str,
    tarifa_acceso:   str,
    pdf_bytes:       bytes,
    result:          ExtractionResponseAI,
    session_payload: dict,
) -> None:
    """
    Cria subpasta {nomedopdf}_{tarifa_acceso} dentro de ZOHO_WORKDRIVE_FOLDER_ID
    e faz upload dos 4 ficheiros. Nunca lança excepção — erros são apenas logados.
    Se ZOHO_WORKDRIVE_FOLDER_ID não estiver definido, retorna silenciosamente.
    """
    folder_id = os.getenv("ZOHO_WORKDRIVE_FOLDER_ID", "").strip()
    if not folder_id:
        return

    files: list[tuple[str, bytes]] = [
        (
            f"{nomedopdf}.pdf",
            pdf_bytes,
        ),
        (
            f"claude_{nomedopdf}.json",
            json.dumps(
                result.model_dump(exclude=_EXCLUDE_FIELDS),
                ensure_ascii=False, indent=2,
            ).encode("utf-8"),
        ),
        (
            f"{nomedopdf}_processed.json",
            json.dumps(
                session_payload.get("factura", {}),
                ensure_ascii=False, indent=2,
            ).encode("utf-8"),
        ),
        (
            f"remoto_{nomedopdf}.json",
            json.dumps(session_payload, ensure_ascii=False, indent=2).encode("utf-8"),
        ),
    ]

    # Extracção pelo pipeline de parsers (BaseParser/parser específico)
    parser_json = await _run_parser(pdf_bytes, nomedopdf)
    if parser_json is not None:
        files.append((f"parser_{nomedopdf}.json", parser_json))

    token          = os.getenv("ZOHO_WORKDRIVE_ACCESS_TOKEN", "")
    subfolder_name = f"{nomedopdf}_{tarifa_acceso}"

    try:
        async with httpx.AsyncClient(timeout=30) as client:

            # Criar subpasta
            subfolder_id = await _create_folder(folder_id, subfolder_name, token, client)
            if subfolder_id == "UNAUTHORIZED":
                token = await refresh_workdrive_token()
                subfolder_id = await _create_folder(folder_id, subfolder_name, token, client)

            if not subfolder_id:
                print(f"  ⚠️  WorkDrive: não foi possível criar pasta '{subfolder_name}'")
                return

            print(f"  ✅  WorkDrive pasta criada: {subfolder_name} ({subfolder_id})")

            # Upload de cada ficheiro
            ok_count = 0
            for filename, content in files:
                ok = await _upload_file(subfolder_id, filename, content, token, client)
                if ok == "UNAUTHORIZED":
                    token = await refresh_workdrive_token()
                    ok = await _upload_file(subfolder_id, filename, content, token, client)
                if ok is True:
                    print(f"  ✅  WorkDrive subido: {filename}  ({len(content):,} bytes)")
                    ok_count += 1
                else:
                    print(f"  ❌  WorkDrive falhou upload: {filename}")

            print(f"  {'✅' if ok_count == len(files) else '⚠️ '}  WorkDrive concluído: {ok_count}/{len(files)} ficheiros enviados")

    except Exception as exc:
        print(f"  ❌  WorkDrive upload_factura_files erro inesperado: {exc}")
