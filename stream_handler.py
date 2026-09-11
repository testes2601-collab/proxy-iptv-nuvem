# stream_handler.py
"""
Motor de Transmissão de Vídeo em Fluxo Contínuo (Apenas Premiere 1 FHD)
- Revezamento automático de contas via accounts.py
- Conexão simulada Chrome via browser_session.py
- Filtro de validação anti-Cloudflare / anti-HTML
"""

import json
import os
import time
from accounts import gerenciador_contas
from browser_session import criar_sessao_chrome
from config import CHUNK_SIZE

ARQUIVO_CANAIS = "canais.json"

def carregar_canais():
    if os.path.exists(ARQUIVO_CANAIS):
        try:
            with open(ARQUIVO_CANAIS, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {
        "premiere1": {"nome": "Premiere 1 FHD", "id_stream": "premiere1"}
    }

def fazer_requisicao_stream(url):
    session = criar_sessao_chrome()
    try:
        resp = session.get(url, stream=True, timeout=5, verify=False)
        return resp
    except Exception:
        return None

def gerar_stream(canal_slug="premiere1"):
    canais = carregar_canais()
    info_canal = canais.get(canal_slug, {"id_stream": canal_slug, "nome": canal_slug})
    id_stream = info_canal.get("id_stream", canal_slug)

    tentativas_totais = 0
    max_tentativas = max(10, gerenciador_contas.total_contas() * 2)

    while tentativas_totais < max_tentativas:
        conta = gerenciador_contas.obter_proxima_conta()
        if not conta:
            time.sleep(1)
            tentativas_totais += 1
            continue

        host = conta.get("host", "").rstrip("/")
        user = conta.get("user", "")
        password = conta.get("pass", "")

        url_stream = f"{host}/live/{user}/{password}/{id_stream}.ts"
        resp = fazer_requisicao_stream(url_stream)

        if not resp or resp.status_code != 200:
            tentativas_totais += 1
            continue

        try:
            iterator = resp.iter_content(chunk_size=CHUNK_SIZE)
            primeiro_chunk = next(iterator, None)

            if not primeiro_chunk:
                resp.close()
                tentativas_totais += 1
                continue

            primeiros_bytes = primeiro_chunk[:1024].lower()
            if b"<html" in primeiros_bytes or b"doctype" in primeiros_bytes or b"cloudflare" in primeiros_bytes:
                resp.close()
                tentativas_totais += 1
                continue

            yield primeiro_chunk

            for chunk in iterator:
                if chunk:
                    yield chunk

            resp.close()

        except Exception:
            if "resp" in locals() and resp:
                try:
                    resp.close()
                except Exception:
                    pass

        tentativas_totais += 1

    time.sleep(1)
