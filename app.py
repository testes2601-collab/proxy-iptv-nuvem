# -*- coding: utf-8 -*-
"""
===============================================================================
SERVIDOR PROXY IPTV PREMIUM - VERSÃO 29 (Resolução Automática de ID Numérico Xtream)
===============================================================================
Recursos da versão v29:
1. Resolução Automática do Stream ID: Busca o ID numérico real do canal Premiere 1
   no painel Xtream Codes (ex: /live/user/pass/58392.ts em vez de premiere1.ts).
   -> Resolve a causa raiz da travamento nos 191.572 bytes (vídeo de erro de canal do Xtream).
2. Cache de Stream ID por Conta: Faz a busca M3U uma única vez e reutiliza o ID numérico.
3. Sessão Contínua Anti-Cloudflare (curl_cffi Chrome 124 + X-Accel-Buffering: no).
4. Auto-Descarte & Suporte Dinâmico a contasonlinefiltradas.json.
===============================================================================
"""

import os
import re
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

# Fallback de contas se contasonlinefiltradas.json não existir
CONTAS_FALLBACK = [
    {
        "id": "meusrv_01",
        "nome": "MeuSrv 955",
        "host": "http://meusrv.top:80",
        "user": "955823677",
        "pass": "798597634"
    },
    {
        "id": "meusrv_02",
        "nome": "MeuSrv 744",
        "host": "http://meusrv.top:80",
        "user": "74468590",
        "pass": "448420959"
    },
    {
        "id": "meusrv_03",
        "nome": "MeuSrv 567",
        "host": "http://meusrv.top:80",
        "user": "567689135",
        "pass": "965722522"
    },
    {
        "id": "meusrv_04",
        "nome": "MeuSrv 361",
        "host": "http://meusrv.top:80",
        "user": "361811331",
        "pass": "252766314"
    }
]

CONTAS_ONLINE_ATIVAS = []
CONTAS_BLOQUEADAS = []

# Cache de ID Numérico do Premiere por Conta: {(host, user): "stream_id_numerico"}
CACHE_STREAM_IDS = {}

HEADERS_CHROME = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "*/*",
    "Accept-Language": "pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7",
    "Connection": "keep-alive"
}

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

def obter_stream_id_real(host, user, password):
    """
    Consulta a API Xtream (/get.php) para obter o ID numérico real do canal Premiere 1.
    Exemplo: retorna '58392' em vez da palavra genérica 'premiere1'.
    """
    chave_cache = (host, user)
    if chave_cache in CACHE_STREAM_IDS:
        return CACHE_STREAM_IDS[chave_cache]

    url_m3u = f"{host}/get.php?username={user}&password={password}&type=m3u_plus"
    try:
        r = requisitar_http(url_m3u, stream=False, timeout=6.0)
        if r.status_code == 200 and "#EXTM3U" in r.text:
            linhas = r.text.splitlines()
            for idx, linha in enumerate(linhas):
                l_up = linha.upper()
                if any(termo in l_up for termo in ["PREMIERE 1", "PREMIERE FC 1", "PFC 1", "PREMIERE HD", "PREMIERE FIRO"]):
                    if idx + 1 < len(linhas):
                        prox = linhas[idx + 1].strip()
                        if prox and not prox.startswith("#"):
                            m = re.search(r'/(\d+)\.(ts|m3u8)', prox)
                            if m:
                                stream_id = m.group(1)
                                CACHE_STREAM_IDS[chave_cache] = stream_id
                                logging.info(f"🎯 ID Numérico capturado com sucesso para {user}: {stream_id}")
                                return stream_id
    except Exception as e:
        logging.warning(f"⚠️ Não foi possível obter ID numérico M3U de {user}: {e}")

    # Fallback caso não encontre no M3U
    return "premiere1"

def carregar_todas_as_contas():
    arquivos_json = ["contasonlinefiltradas.json", "stream_config.json", "canais.json"]
    for arq in arquivos_json:
        if os.path.exists(arq):
            try:
                with open(arq, "r", encoding="utf-8") as f:
                    dados = json.load(f)
                    if isinstance(dados, list) and len(dados) > 0:
                        logging.info(f"📂 Contas carregadas do arquivo: {arq} ({len(dados)} contas)")
                        return dados
                    elif isinstance(dados, dict) and "contas" in dados:
                        logging.info(f"📂 Contas carregadas do arquivo: {arq}")
                        return dados["contas"]
            except Exception as e:
                logging.warning(f"Erro ao ler {arq}: {e}")
    logging.info("ℹ️ Usando pool de contas interno (Fallback)")
    return CONTAS_FALLBACK

def validar_se_e_video_mpegts(chunk_bytes):
    if not chunk_bytes or len(chunk_bytes) < 188:
        return False
    if chunk_bytes[0] != 0x47:
        return False
    amostra = chunk_bytes[:1024].lower()
    termos_invalidos = [b"<html", b"<!doctype", b"cloudflare", b"restricted", b"access denied", b"error 1020"]
    for termo in termos_invalidos:
        if termo in amostra:
            return False
    return True

def testar_conta(conta_info):
    host = conta_info.get("host", "").rstrip("/")
    user = conta_info.get("user") or conta_info.get("username", "")
    password = conta_info.get("pass") or conta_info.get("password", "")
    
    if not host or not user or not password:
        return False
        
    stream_id = obter_stream_id_real(host, user, password)
    urls = [
        f"{host}/live/{user}/{password}/{stream_id}.ts",
        f"{host}/live/{user}/{password}/{stream_id}.m3u8"
    ]
    
    for url in urls:
        try:
            r = requisitar_http(url, stream=True, timeout=4.0)
            if r.status_code == 200:
                chunk = next(r.iter_content(chunk_size=16384), None)
                if chunk and validar_se_e_video_mpegts(chunk):
                    return True
        except Exception:
            continue
    return False

def atualizar_pool_de_contas():
    global CONTAS_ONLINE_ATIVAS, CONTAS_BLOQUEADAS
    todas = carregar_todas_as_contas()
    novas_online = []
    novas_bloqueadas = []
    
    for idx, c in enumerate(todas):
        nome = c.get("nome") or c.get("id") or f"Conta #{idx+1}"
        c["nome_formatado"] = nome
        if testar_conta(c):
            novas_online.append(c)
        else:
            novas_bloqueadas.append(c)
            
    CONTAS_ONLINE_ATIVAS = novas_online
    CONTAS_BLOQUEADAS = novas_bloqueadas
    logging.info(f"📊 Diagnóstico Concluído (v29 - Resolvido ID Numérico): {len(novas_online)} Online | {len(novas_bloqueadas)} Descartadas")

def iniciar_verificacao_em_segundo_plano():
    t = Thread(target=atualizar_pool_de_contas)
    t.daemon = True
    t.start()

# Executa primeira checagem no arranque
atualizar_pool_de_contas()

def tentar_obter_stream_direto():
    global CONTAS_ONLINE_ATIVAS, CONTAS_BLOQUEADAS
    
    if not CONTAS_ONLINE_ATIVAS:
        atualizar_pool_de_contas()
        
    contas_copia = list(CONTAS_ONLINE_ATIVAS)
    
    for conta in contas_copia:
        host = conta.get("host", "").rstrip("/")
        user = conta.get("user") or conta.get("username", "")
        password = conta.get("pass") or conta.get("password", "")
        
        stream_id = obter_stream_id_real(host, user, password)
        url_target = f"{host}/live/{user}/{password}/{stream_id}.ts"
        
        try:
            r = requisitar_http(url_target, stream=True, timeout=6.0)
            if r.status_code == 200:
                iterador = r.iter_content(chunk_size=32768)
                primeiro_chunk = next(iterador, None)
                if primeiro_chunk and validar_se_e_video_mpegts(primeiro_chunk):
                    def gerador():
                        yield primeiro_chunk
                        for chunk in iterador:
                            if chunk:
                                yield chunk
                    logging.info(f"🟢 Transmissão Iniciada (ID {stream_id}) via: {conta.get('nome_formatado')}")
                    return gerador()
        except Exception as err:
            logging.warning(f"⚠️ Conta {conta.get('nome_formatado')} falhou na transmissão: {err}. Removendo do pool...")
            if conta in CONTAS_ONLINE_ATIVAS:
                CONTAS_ONLINE_ATIVAS.remove(conta)
                CONTAS_BLOQUEADAS.append(conta)
            continue
            
    return None

def adicionar_cabecalhos_streaming(resposta):
    resposta.headers["Access-Control-Allow-Origin"] = "*"
    resposta.headers["Access-Control-Allow-Headers"] = "*"
    resposta.headers["Access-Control-Allow-Methods"] = "GET, OPTIONS, HEAD"
    resposta.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    resposta.headers["X-Accel-Buffering"] = "no"
    return resposta

# =============================================================================
# ROTAS FLASK
# =============================================================================

@app.route("/")
def home():
    html = """
    <!DOCTYPE html>
    <html lang="pt-BR">
    <head>
        <meta charset="UTF-8">
        <title>Servidor Proxy IPTV - Premiere 1 (v29)</title>
        <style>
            body { font-family: Arial, sans-serif; background-color: #121212; color: #fff; text-align: center; padding: 40px; }
            .card { background-color: #1e1e1e; padding: 30px; border-radius: 12px; display: inline-block; max-width: 650px; }
            h1 { color: #00e676; }
            .btn { display: inline-block; background-color: #00e676; color: #000; padding: 12px 24px; margin: 10px; border-radius: 6px; font-weight: bold; text-decoration: none; }
        </style>
    </head>
    <body>
        <div class="card">
            <h1>⚽ Servidor Proxy IPTV Premiere 1 (v29)</h1>
            <p>Servidor Ativo com Resolução Automática de ID Numérico Xtream!</p>
            <br>
            <a href="/debug" class="btn">📊 Painel de Diagnóstico (/debug)</a>
            <a href="/playlist.m3u" class="btn">📋 Baixar Lista M3U (/playlist.m3u)</a>
        </div>
    </body>
    </html>
    """
    return adicionar_cabecalhos_streaming(Response(html, content_type="text/html; charset=utf-8"))

@app.route("/debug")
@app.route("/debug/")
def debug():
    iniciar_verificacao_em_segundo_plano()
    linhas_online = [f"<li style='color:#00e676;'><b>[ATIVO] {c.get('nome_formatado')}</b> (Stream ID: {CACHE_STREAM_IDS.get((c.get('host','').rstrip('/'), c.get('user','')), 'buscando...')})</li>" for c in CONTAS_ONLINE_ATIVAS]
    linhas_bloqueadas = [f"<li style='color:#ff5252;'><b>[REMOVIDO] {c.get('nome_formatado')}</b>: BLOQUEADO / OFFLINE</li>" for c in CONTAS_BLOQUEADAS]
    
    html = f"""
    <h2>📊 Painel de Diagnóstico v29 (IDs Numéricos Xtream)</h2>
    <p><b>Contas Ativas no Roteador:</b> {len(CONTAS_ONLINE_ATIVAS)} | <b>Contas Descartadas:</b> {len(CONTAS_BLOQUEADAS)}</p>
    <h3>✅ Contas Online (Stream ID Capturado)</h3>
    <ul>{''.join(linhas_online) if linhas_online else '<li>Nenhuma conta online no momento</li>'}</ul>
    <h3>❌ Contas Descartadas do Pool</h3>
    <ul>{''.join(linhas_bloqueadas) if linhas_bloqueadas else '<li>Nenhuma conta descartada</li>'}</ul>
    """
    return adicionar_cabecalhos_streaming(Response(html, content_type="text/html; charset=utf-8"))

@app.route("/playlist.m3u")
@app.route("/playlist.m3u8")
@app.route("/playlist")
@app.route("/get.php")
def playlist():
    host_base = request.host_url.rstrip("/")
    m3u_txt = f"""#EXTM3U
#EXTINF:-1 tvg-id="Premiere1.br" tvg-name="Premiere 1 FHD" tvg-logo="https://i.imgur.com/8Q9Z3v1.png" group-title="ESPORTES",Premiere 1 FHD
{host_base}/live/premiere1.ts
"""
    return adicionar_cabecalhos_streaming(Response(m3u_txt, content_type="application/x-mpegURL"))

@app.route("/live/premiere1.ts")
@app.route("/live/premiere.m3u8")
@app.route("/live/premiere1.m3u8")
@app.route("/live/premiere1")
@app.route("/live/premiere")
def stream_premiere():
    gerador = tentar_obter_stream_direto()
    if gerador:
        return adicionar_cabecalhos_streaming(Response(gerador, content_type="video/mp2t"))
    return adicionar_cabecalhos_streaming(Response("Sinal indisponível no momento. Todas as contas falharam.", status=503, content_type="text/plain; charset=utf-8"))

@app.errorhandler(404)
def erro_404(e):
    return playlist()

if __name__ == "__main__":
    porta = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=porta, debug=False)
