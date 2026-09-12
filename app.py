# -*- coding: utf-8 -*-
"""
===============================================================================
SERVIDOR PROXY IPTV PREMIUM - VERSÃO 30 (Ultra-Rápido com Leitura de stream_config.json)
===============================================================================
Recursos da versão v30:
1. Leitura do `stream_config.json`: Consome diretamente os IDs numéricos reais pré-mapeados
   pelo script local `gerar_config_ids.py`.
2. Latência Zero: Sem perdas de tempo buscando playlists M3U ou testando contas mortas no Render.
3. Anti-Cloudflare TLS (curl_cffi Chrome 124) + Suporte Multi-Rotas (/live/premiere1.ts, etc).
===============================================================================
"""

import os
import time
import json
import logging
import urllib3
from flask import Flask, Response, request
from threading import Thread

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
    "Connection": "keep-alive"
}

CONTAS_ONLINE = []
CONTAS_BLOQUEADAS = []

def requisitar_http(url, stream=True, timeout=5.0):
    if HAS_CURL_CFFI:
        return cffi_requests.get(
            url,
            headers=HEADERS_CHROME,
            stream=stream,
            timeout=timeout,
            verify=False,
            impersonate="chrome124"
        )
    else:
        return cffi_requests.get(
            url,
            headers=HEADERS_CHROME,
            stream=stream,
            timeout=timeout,
            verify=False
        )

def carregar_stream_config():
    global CONTAS_ONLINE
    arquivos = ["stream_config.json", "contasonlinefiltradas.json"]
    for arq in arquivos:
        if os.path.exists(arq):
            try:
                with open(arq, "r", encoding="utf-8") as f:
                    dados = json.load(f)
                    lista = dados.get("contas", dados) if isinstance(dados, dict) else dados
                    if isinstance(lista, list) and len(lista) > 0:
                        logging.info(f"📂 Configuração carregada com sucesso de '{arq}' ({len(lista)} contas)")
                        CONTAS_ONLINE = lista
                        return
            except Exception as e:
                logging.warning(f"Erro ao carregar {arq}: {e}")
    logging.warning("⚠️ Nenhum arquivo de configuração válido encontrado.")

carregar_stream_config()

def validar_mpegts(chunk):
    if not chunk or len(chunk) < 188 or chunk[0] != 0x47:
        return False
    amostra = chunk[:1024].lower()
    return not any(t in amostra for t in [b"<html", b"<!doctype", b"cloudflare", b"access denied"])

def obter_gerador_stream():
    global CONTAS_ONLINE, CONTAS_BLOQUEADAS
    
    if not CONTAS_ONLINE:
        carregar_stream_config()
        
    copia_contas = list(CONTAS_ONLINE)
    
    for conta in copia_contas:
        host = conta.get("host", "").rstrip("/")
        user = conta.get("user") or conta.get("username", "")
        password = conta.get("pass") or conta.get("password", "")
        stream_id = conta.get("stream_id", "premiere1")
        
        url_target = conta.get("url_direta") or f"{host}/live/{user}/{password}/{stream_id}.ts"
        
        try:
            r = requisitar_http(url_target, stream=True, timeout=4.0)
            if r.status_code == 200:
                iterador = r.iter_content(chunk_size=32768)
                primeiro_chunk = next(iterador, None)
                if primeiro_chunk and validar_mpegts(primeiro_chunk):
                    def gerador():
                        yield primeiro_chunk
                        for chunk in iterador:
                            if chunk:
                                yield chunk
                    logging.info(f"🟢 Transmissão Iniciada via: {conta.get('nome', user)}")
                    return gerador()
        except Exception as err:
            logging.warning(f"⚠️ Conta {conta.get('nome', user)} falhou: {err}. Descartando...")
            if conta in CONTAS_ONLINE:
                CONTAS_ONLINE.remove(conta)
                CONTAS_BLOQUEADAS.append(conta)
            continue
            
    return None

def adicionar_cors(resp):
    resp.headers["Access-Control-Allow-Origin"] = "*"
    resp.headers["Access-Control-Allow-Headers"] = "*"
    resp.headers["Access-Control-Allow-Methods"] = "GET, OPTIONS, HEAD"
    resp.headers["X-Accel-Buffering"] = "no"
    return resp

@app.route("/")
def home():
    return adicionar_cors(Response("Servidor Proxy IPTV Premiere 1 (v30) Ativo!", content_type="text/plain; charset=utf-8"))

@app.route("/debug")
def debug():
    carregar_stream_config()
    linhas_online = [f"<li style='color:#00e676;'><b>{c.get('nome', c.get('user'))}</b> (ID: {c.get('stream_id', 'N/A')}): ONLINE</li>" for c in CONTAS_ONLINE]
    linhas_bloq = [f"<li style='color:#ff5252;'><b>{c.get('nome', c.get('user'))}</b>: BLOQUEADO</li>" for c in CONTAS_BLOQUEADAS]
    
    html = f"""
    <h2>📊 Diagnóstico v30 (stream_config.json)</h2>
    <p><b>Contas Carregadas:</b> {len(CONTAS_ONLINE)} | <b>Descartadas:</b> {len(CONTAS_BLOQUEADAS)}</p>
    <h3>✅ Online</h3>
    <ul>{''.join(linhas_online) if linhas_online else '<li>Nenhuma</li>'}</ul>
    <h3>❌ Bloqueadas</h3>
    <ul>{''.join(linhas_bloq) if linhas_bloq else '<li>Nenhuma</li>'}</ul>
    """
    return adicionar_cors(Response(html, content_type="text/html; charset=utf-8"))

@app.route("/playlist.m3u")
@app.route("/playlist.m3u8")
@app.route("/playlist")
@app.route("/get.php")
def playlist():
    host_base = request.host_url.rstrip("/")
    m3u_txt = f"#EXTM3U\n#EXTINF:-1 tvg-id=\"Premiere1.br\" tvg-name=\"Premiere 1 FHD\" group-title=\"ESPORTES\",Premiere 1 FHD\n{host_base}/live/premiere1.ts\n"
    return adicionar_cors(Response(m3u_txt, content_type="application/x-mpegURL"))

@app.route("/live/premiere1.ts")
@app.route("/live/premiere1.m3u8")
@app.route("/live/premiere.m3u8")
@app.route("/live/premiere.ts")
@app.route("/live/premiere1")
@app.route("/live/premiere")
def stream_premiere():
    gerador = obter_gerador_stream()
    if gerador:
        return adicionar_cors(Response(gerador, content_type="video/mp2t"))
    return adicionar_cors(Response("Sinal indisponível.", status=503, content_type="text/plain; charset=utf-8"))

if __name__ == "__main__":
    porta = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=porta, debug=False)
