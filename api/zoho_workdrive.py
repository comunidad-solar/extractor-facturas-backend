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
from api.routes.sesion import actualizar_sesion

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
    result:          ExtractionResponseAI | None,
    session_payload: dict,
    session_id:      str | None = None,
    is_error:        bool = False,
    error_msg:       str | None = None,
    error_traceback: str | None = None,
    partial_data:    dict | None = None,
) -> None:
    """
    Cria subpasta {nomedopdf}_{tarifa_acceso} dentro de ZOHO_WORKDRIVE_FOLDER_ID
    e faz upload dos ficheiros. Nunca lança excepção — erros são apenas logados.
    Se ZOHO_WORKDRIVE_FOLDER_ID não estiver definido, retorna silenciosamente.
    Se is_error=True, usa prefixo ERROR_ e inclui error_report.json em vez dos JSON Claude.
    """
    folder_id = os.getenv("ZOHO_WORKDRIVE_FOLDER_ID", "").strip()
    if not folder_id:
        return

    files: list[tuple[str, bytes]] = [
        (f"{nomedopdf}.pdf", pdf_bytes),
    ]

    if is_error:
        error_doc = {
            "error":        error_msg or "Unknown error",
            "traceback":    error_traceback,
            "filename":     f"{nomedopdf}.pdf",
            "partial_data": partial_data,
        }
        files.append((
            f"{nomedopdf}_ERROR.json",
            json.dumps(error_doc, ensure_ascii=False, indent=2).encode("utf-8"),
        ))

    if result is not None:
        files += [
            (
                f"{nomedopdf}_claudeDatosBrutos.json",
                json.dumps(
                    result.model_dump(exclude=_EXCLUDE_FIELDS),
                    ensure_ascii=False, indent=2,
                ).encode("utf-8"),
            ),
            (
                f"{nomedopdf}_claudeDatosTratados.json",
                json.dumps(
                    session_payload.get("factura", {}),
                    ensure_ascii=False, indent=2,
                ).encode("utf-8"),
            ),
            (
                f"{nomedopdf}_datosEnviadosalCotizador.json",
                json.dumps(session_payload, ensure_ascii=False, indent=2).encode("utf-8"),
            ),
        ]

    # Extracção pelo pipeline de parsers (BaseParser/parser específico)
    parser_json = await _run_parser(pdf_bytes, nomedopdf)
    if parser_json is not None:
        files.append((f"parser_{nomedopdf}.json", parser_json))

    token          = os.getenv("ZOHO_WORKDRIVE_ACCESS_TOKEN", "")
    prefix         = "ERROR" if is_error else "DEV"
    subfolder_name = f"{prefix}_{nomedopdf}_{tarifa_acceso}"

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

            # Injetar workdrive_id na sessão
            if session_id:
                actualizar_sesion(session_id, {**session_payload, "workdrive_id": subfolder_id})
                print(f"  ✅  Sessão {session_id} actualizada com workdrive_id: {subfolder_id}")

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


async def _get_deal_workdrive_folder(
    deal_id: str,
    crm_token: str,
    client: httpx.AsyncClient,
) -> str | None | Literal["UNAUTHORIZED"]:
    """Busca easyworkdriveforcrm__Workdrive_Folder_ID_EXT do deal no CRM."""
    from api.zoho_crm import ZOHO_API_DOMAIN
    url = f"{ZOHO_API_DOMAIN}/crm/v8/Deals/{deal_id}"
    headers = {"Authorization": f"Zoho-oauthtoken {crm_token}"}
    r = await client.get(url, params={"fields": "easyworkdriveforcrm__Workdrive_Folder_ID_EXT"}, headers=headers)
    if r.status_code == 401:
        return "UNAUTHORIZED"
    if r.status_code not in (200, 201):
        print(f"  ⚠️  WorkDrive deal: CRM HTTP {r.status_code} para deal {deal_id}")
        return None
    data = r.json().get("data", [])
    if not data:
        return None
    return data[0].get("easyworkdriveforcrm__Workdrive_Folder_ID_EXT")


async def _list_folder_files(
    folder_id: str,
    token: str,
    client: httpx.AsyncClient,
) -> list[dict] | Literal["UNAUTHORIZED"]:
    """Lista ficheiros numa pasta WorkDrive."""
    headers = {"Authorization": f"Zoho-oauthtoken {token}"}
    r = await client.get(f"{_WD_BASE}/files/{folder_id}/files", headers=headers)
    if r.status_code == 401 or _is_invalid_token(r):
        return "UNAUTHORIZED"
    if r.status_code not in (200, 201):
        return []
    return r.json().get("data", [])


async def _copy_wd_file(
    file_id: str,
    target_folder_id: str,
    token: str,
    client: httpx.AsyncClient,
) -> bool | Literal["UNAUTHORIZED"]:
    """Copia um ficheiro para outra pasta no WorkDrive (server-side, sem download).
    POST /files/{target_folder_id}/copy com resource_id no body (array).
    """
    headers = {
        "Authorization": f"Zoho-oauthtoken {token}",
        "Content-Type":  "application/json",
    }
    body = {
        "data": [
            {
                "attributes": {"resource_id": file_id},
                "type": "files",
            }
        ]
    }
    r = await client.post(f"{_WD_BASE}/files/{target_folder_id}/copy", json=body, headers=headers)
    if r.status_code == 401 or _is_invalid_token(r):
        return "UNAUTHORIZED"
    if r.status_code not in (200, 201):
        print(f"  ⚠️  WorkDrive _copy_wd_file HTTP {r.status_code}: {r.text[:200]}")
        return False
    return True


async def upload_pdf_to_deal_workdrive(deal_id: str, extraction_folder_id: str) -> None:
    """
    Copia o PDF da factura da pasta de extracção para a pasta WorkDrive do deal.
    Obtém o folder_id do deal via CRM (easyworkdriveforcrm__Workdrive_Folder_ID_EXT).
    Nunca lança excepção — erros são apenas logados.
    """
    if not deal_id or not extraction_folder_id:
        return

    try:
        from api.zoho_crm import refresh_access_token

        crm_token = os.getenv("ZOHO_ACCESS_TOKEN", "")
        wd_token  = os.getenv("ZOHO_WORKDRIVE_ACCESS_TOKEN", "")

        async with httpx.AsyncClient(timeout=30) as client:

            # 1. Obter folder_id do deal no CRM
            deal_folder_id = await _get_deal_workdrive_folder(deal_id, crm_token, client)
            if deal_folder_id == "UNAUTHORIZED":
                crm_token = await refresh_access_token()
                deal_folder_id = await _get_deal_workdrive_folder(deal_id, crm_token, client)

            if not deal_folder_id:
                print(f"  ⚠️  WorkDrive deal: sem folder_id para deal {deal_id}")
                return

            print(f"  ✅  WorkDrive deal folder: {deal_folder_id}")

            # 2. Listar ficheiros na pasta de extracção → encontrar o PDF
            files = await _list_folder_files(extraction_folder_id, wd_token, client)
            if files == "UNAUTHORIZED":
                wd_token = await refresh_workdrive_token()
                files = await _list_folder_files(extraction_folder_id, wd_token, client)

            if not files or files == "UNAUTHORIZED":
                print(f"  ⚠️  WorkDrive deal: sem ficheiros em {extraction_folder_id}")
                return

            pdf_entry = next(
                (f for f in files
                 if f.get("attributes", {}).get("name", "").lower().endswith(".pdf")),
                None,
            )
            if not pdf_entry:
                print(f"  ⚠️  WorkDrive deal: PDF não encontrado em {extraction_folder_id}")
                return

            pdf_id        = pdf_entry["id"]
            pdf_attrs     = pdf_entry.get("attributes", {})
            pdf_name      = pdf_attrs.get("name", "factura.pdf")
            pdf_res_id    = pdf_attrs.get("resource_id") or pdf_id
            print(f"  📄  WorkDrive PDF entry — id:{pdf_id} resource_id:{pdf_res_id} name:{pdf_name}")

            # 3. Copiar PDF para pasta do deal (server-side, sem download)
            ok = await _copy_wd_file(pdf_res_id, deal_folder_id, wd_token, client)
            if ok == "UNAUTHORIZED":
                wd_token = await refresh_workdrive_token()
                ok = await _copy_wd_file(pdf_id, deal_folder_id, wd_token, client)

            if ok is True:
                print(f"  ✅  WorkDrive deal: '{pdf_name}' copiado → deal {deal_id} ({deal_folder_id})")
            else:
                print(f"  ❌  WorkDrive deal: falhou cópia para deal {deal_id}")

    except Exception as exc:
        print(f"  ❌  WorkDrive upload_pdf_to_deal_workdrive erro: {exc}")
