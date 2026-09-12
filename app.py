# -*- coding: utf-8 -*-
"""
===============================================================================
SERVIDOR PROXY IPTV PREMIUM - VERSÃO 33 (Suporte Nativo HLS .m3u8 & MPEG-TS .ts)
===============================================================================
Novidades da Versão 33:
1. Preservação Estrita de URLs .m3u8 (sem forçar conversão para .ts).
2. Validador de Fluxo HLS/MPEG-TS: Aceita tanto pacotes .ts (0x47) quanto listas HLS (#EXTM3U).
3. Auto-Failover Transparente em Loop Infinito sem tela preta.
4. Suporte aos endpoints /live/premiere1.m3u8 e /live/premiere1.ts.
===============================================================================
"""

import os
import json
import time
import logging
import urllib3
from flask import Flask, Response, request, stream_with_context

try:
    from curl_cffi import requests as cffi_requests
    HAS_CURL_CFFI = True
except ImportError:
    import requests as cffi_requests
    HAS_CURL_CFFI = False

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

app = Flask(__name__)

HEADERS_CHROME = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "*/*",
    "Accept-Language": "pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7",
    "Connection": "keep-alive"
}

def carregar_configuracao():
    arquivos = ["stream_config.json", "contasonlinefiltradas.json", "canais.json"]
    for arq in arquivos:
        if os.path.exists(arq):
            try:
                with open(arq, "r", encoding="utf-8") as f:
                    dados = json.load(f)
                    if isinstance(dados, dict) and "contas" in dados:
                        return dados["contas"]
                    elif isinstance(dados, list) and len(dados) > 0:
                        return dados
            except Exception as e:
                logging.warning(f"Erro ao ler {arq}: {e}")
    return []

def obter_url_canal(conta):
    # Preserva rigorosamente a URL original fornecida (ex: .m3u8)
    if "url_direta" in conta and conta["url_direta"]:
        return conta["url_direta"]
    host = conta.get("host", "").rstrip("/")
    user = conta.get("user") or conta.get("username", "")
    password = conta.get("pass") or conta.get("password", "")
    stream_id = conta.get("stream_id", "premiere1")
    return f"{host}/live/{user}/{password}/{stream_id}.m3u8"

def criar_sessao():
    if HAS_CURL_CFFI:
        return cffi_requests.Session(impersonate="chrome124")
    return cffi_requests.Session()

def validar_chunk(chunk):
    if not chunk or len(chunk) < 10:
        return False
    amostra = chunk[:512].lower()
    # Bloqueia HTML / Cloudflare / Erros de Acesso
    if b"<html" in amostra or b"cloudflare" in amostra or b"access denied" in amostra or b"404 not found" in amostra:
        return False
    # Aceita byte de sincronização MPEG-TS (0x47) OU cabeçalho HLS M3U8 (#EXTM3U / #EXTINF) OU fluxo binário
    if chunk[0] == 0x47 or b"#extm3u" in amostra or b"#extinf" in amostra or len(chunk) >= 188:
        return True
    return False

def gerador_de_stream_continuo():
    contas = carregar_configuracao()
    if not contas:
        logging.error("❌ Nenhuma conta disponível no stream_config.json")
        return

    idx_conta = 0
    tentativas = 0
    max_tentativas = len(contas) * 10

    while tentativas < max_tentativas:
        conta = contas[idx_conta % len(contas)]
        url_target = obter_url_canal(conta)
        nome_conta = conta.get("nome") or conta.get("id") or f"Conta #{idx_conta+1}"

        logging.info(f"📡 Abrindo fluxo .m3u8 via: {nome_conta} -> {url_target}")
        
        session = criar_sessao()
        try:
            r = session.get(url_target, headers=HEADERS_CHROME, stream=True, timeout=6.0, verify=False)
            if r.status_code == 200:
                iterador = r.iter_content(chunk_size=32768)
                primeiro_chunk = next(iterador, None)

                if primeiro_chunk and validar_chunk(primeiro_chunk):
                    logging.info(f"🟢 Transmissão HLS/M3U8 Ativa via: {nome_conta}")
                    yield primeiro_chunk
                    
                    for chunk in iterador:
                        if chunk:
                            yield chunk
                        else:
                            break
                    
                    logging.warning(f"⚠️ Fluxo encerrado na conta {nome_conta}. Efetuando failover transparente...")
            else:
                logging.warning(f"🔴 Erro HTTP {r.status_code} na conta {nome_conta}")
        except Exception as e:
            logging.warning(f"⚠️ Falha no fluxo da conta {nome_conta}: {e}")
        finally:
            try:
                session.close()
            except Exception:
                pass

        idx_conta += 1
        tentativas += 1
        time.sleep(0.1)

def adicionar_cabecalhos_streaming(resposta, content_type="application/x-mpegURL"):
    resposta.headers["Access-Control-Allow-Origin"] = "*"
    resposta.headers["Access-Control-Allow-Headers"] = "*"
    resposta.headers["Access-Control-Allow-Methods"] = "GET, OPTIONS, HEAD"
    resposta.headers["Cache-Control"] = "no-cache, no-store, must-revalidate, private"
    resposta.headers["Pragma"] = "no-cache"
    resposta.headers["Expires"] = "0"
    resposta.headers["X-Accel-Buffering"] = "no"
    resposta.headers["Content-Type"] = content_type
    return resposta

@app.route("/")
def home():
    return adicionar_cabecalhos_streaming(Response("Servidor Proxy IPTV Premiere 1 (v33 M3U8 Native Stream)", content_type="text/plain; charset=utf-8"), "text/plain; charset=utf-8")

@app.route("/debug")
def debug():
    contas = carregar_configuracao()
    return adicionar_cabecalhos_streaming(Response(f"Contas Ativas no Pool: {len(contas)}", content_type="text/plain; charset=utf-8"), "text/plain; charset=utf-8")

@app.route("/playlist.m3u")
@app.route("/playlist.m3u8")
def playlist():
    host_base = request.host_url.rstrip("/")
    m3u = f'#EXTM3U\n#EXTINF:-1 tvg-id="Premiere1.br" tvg-name="Premiere 1 FHD",Premiere 1 FHD\n{host_base}/live/premiere1.m3u8\n'
    return adicionar_cabecalhos_streaming(Response(m3u, content_type="application/x-mpegURL"), "application/x-mpegURL")

@app.route("/live/premiere1.m3u8")
@app.route("/live/premiere.m3u8")
@app.route("/live/premiere1.ts")
@app.route("/live/premiere.ts")
def stream():
    ext = request.path.split(".")[-1]
    ctype = "application/x-mpegURL" if ext == "m3u8" else "video/mp2t"
    return adicionar_cabecalhos_streaming(Response(
        stream_with_context(gerador_de_stream_continuo()),
        content_type=ctype
    ), ctype)

if __name__ == "__main__":
    porta = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=porta, debug=False)
