# -*- coding: utf-8 -*-
"""
===============================================================================
SERVIDOR PROXY IPTV PREMIUM - VERSÃO 27 (Anti-Cloudflare TLS Impersonate & Auto-Descarte)
===============================================================================
Recursos da versão v27:
1. Anti-Cloudflare TLS Impersonation (curl_cffi): Simula o Chrome 124 real nas requisições,
   impedindo que a Cloudflare detecte o fingerprint de script e derrube a conexão a cada 190KB.
2. Leitura Dinâmica do `contasonlinefiltradas.json` com Fallback de Segurança.
3. Descarte Automático e Isolamento de Contas Bloqueadas / Offline.
4. Conexão Contínua e Ininterrupta para VLC, Smart TV, TiviMate e SS IPTV.
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

# Importa curl_cffi para contornar impressão digital TLS da Cloudflare
try:
    from curl_cffi import requests as cffi_requests
    HAS_CURL_CFFI = True
except ImportError:
    import requests as cffi_requests
    HAS_CURL_CFFI = False

# Desativa avisos de SSL
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

app = Flask(__name__)

# =============================================================================
# FALLBACK DE CONTAS (CASO O JSON NÃO SEJA ENCONTRADO)
# =============================================================================
CONTAS_FALLBACK = [
    {
        "id": "meusrv_03",
        "nome": "MeuSrv 567",
        "host": "http://meusrv.top:80",
        "user": "567689135",
        "pass": "965722522"
    },
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
        "id": "meusrv_04",
        "nome": "MeuSrv 361",
        "host": "http://meusrv.top:80",
        "user": "361811331",
        "pass": "252766314"
    }
]

CONTAS_ONLINE_ATIVAS = []
CONTAS_BLOQUEADAS = []

HEADERS_CHROME = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "*/*",
    "Accept-Language": "pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7",
    "Connection": "keep-alive"
}

def requisitar_http(url, stream=True, timeout=4.0):
    """ Realiza requisição usando impersonate Chrome 124 para enganar o WAF da Cloudflare """
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

def carregar_todas_as_contas():
    """ Tenta carregar as contas do arquivo contasonlinefiltradas.json ou usa fallback """
    arquivos_json = ["contasonlinefiltradas.json", "stream_config.json", "canais.json"]
    
    for arq in arquivos_json:
        if os.path.exists(arq):
            try:
                with open(arq, "r", encoding="utf-8") as f:
                    dados = json.load(f)
                    if isinstance(dados, list) and len(dados) > 0:
                        logging.info(f"📂 Contas carregadas com sucesso do arquivo: {arq} ({len(dados)} contas)")
                        return dados
                    elif isinstance(dados, dict) and "contas" in dados:
                        logging.info(f"📂 Contas carregadas com sucesso do arquivo: {arq}")
                        return dados["contas"]
            except Exception as e:
                logging.warning(f"Erro ao ler {arq}: {e}")
                
    logging.info("ℹ️ Usando pool de contas interno (Fallback)")
    return CONTAS_FALLBACK

def validar_se_e_video_mpegts(chunk_bytes):
    """ Valida se o primeiro pacote é MPEG-TS válido (byte 0x47) """
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
    """ Valida individualmente uma conta utilizando simulação de Chrome 124 """
    host = conta_info.get("host", "").rstrip("/")
    user = conta_info.get("user") or conta_info.get("username", "")
    password = conta_info.get("pass") or conta_info.get("password", "")
    
    if not host or not user or not password:
        return False
        
    urls = [
        f"{host}/live/{user}/{password}/premiere1.ts",
        f"{host}/live/{user}/{password}/premiere.m3u8",
        f"{host}/live/{user}/{password}/premiere.ts"
    ]
    
    for url in urls:
        try:
            r = requisitar_http(url, stream=True, timeout=3.5)
            if r.status_code == 200:
                chunk = next(r.iter_content(chunk_size=16384), None)
                if chunk and validar_se_e_video_mpegts(chunk):
                    return True
        except Exception:
            continue
    return False

def atualizar_pool_de_contas():
    """ Diagnostica as contas e separa as ONLINE das BLOQUEADAS """
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
    logging.info(f"📊 Diagnóstico Concluído (curl_cffi Chrome 124): {len(novas_online)} Online | {len(novas_bloqueadas)} Descartadas/Bloqueadas")

def iniciar_verificacao_em_segundo_plano():
    t = Thread(target=atualizar_pool_de_contas)
    t.daemon = True
    t.start()

# Executa primeira checagem no startup
atualizar_pool_de_contas()

def tentar_obter_stream_direto():
    """ Conecta na primeira conta ativa válida enviando TLS Chrome 124 de baixa latência """
    global CONTAS_ONLINE_ATIVAS, CONTAS_BLOQUEADAS
    
    if not CONTAS_ONLINE_ATIVAS:
        atualizar_pool_de_contas()
        
    contas_copia = list(CONTAS_ONLINE_ATIVAS)
    
    for conta in contas_copia:
        host = conta.get("host", "").rstrip("/")
        user = conta.get("user") or conta.get("username", "")
        password = conta.get("pass") or conta.get("password", "")
        
        url_target = f"{host}/live/{user}/{password}/premiere1.ts"
        try:
            r = requisitar_http(url_target, stream=True, timeout=5.0)
            if r.status_code == 200:
                iterador = r.iter_content(chunk_size=32768)
                primeiro_chunk = next(iterador, None)
                if primeiro_chunk and validar_se_e_video_mpegts(primeiro_chunk):
                    def gerador():
                        yield primeiro_chunk
                        for chunk in iterador:
                            if chunk:
                                yield chunk
                    logging.info(f"🟢 Transmissão Iniciada (Chrome 124 TLS) via: {conta.get('nome_formatado')}")
                    return gerador()
        except Exception as err:
            logging.warning(f"⚠️ Conta {conta.get('nome_formatado')} falhou durante reprodução: {err}. Removendo do pool...")
            if conta in CONTAS_ONLINE_ATIVAS:
                CONTAS_ONLINE_ATIVAS.remove(conta)
                CONTAS_BLOQUEADAS.append(conta)
            continue
            
    return None

def adicionar_cors(resposta):
    resposta.headers["Access-Control-Allow-Origin"] = "*"
    resposta.headers["Access-Control-Allow-Headers"] = "*"
    resposta.headers["Access-Control-Allow-Methods"] = "GET, OPTIONS, HEAD"
    resposta.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
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
        <title>Servidor Proxy IPTV - Premiere 1 (v27 Anti-Cloudflare)</title>
        <style>
            body { font-family: Arial, sans-serif; background-color: #121212; color: #fff; text-align: center; padding: 40px; }
            .card { background-color: #1e1e1e; padding: 30px; border-radius: 12px; display: inline-block; max-width: 650px; }
            h1 { color: #00e676; }
            .btn { display: inline-block; background-color: #00e676; color: #000; padding: 12px 24px; margin: 10px; border-radius: 6px; font-weight: bold; text-decoration: none; }
        </style>
    </head>
    <body>
        <div class="card">
            <h1>⚽ Servidor Proxy IPTV Premiere 1 (v27 Anti-Cloudflare)</h1>
            <p>Servidor Ativo com Impersonate Chrome 124 (curl_cffi) & Auto-Descarte!</p>
            <br>
            <a href="/debug" class="btn">📊 Painel de Diagnóstico (/debug)</a>
            <a href="/playlist.m3u" class="btn">📋 Baixar Lista M3U (/playlist.m3u)</a>
        </div>
    </body>
    </html>
    """
    return adicionar_cors(Response(html, content_type="text/html; charset=utf-8"))

@app.route("/debug")
@app.route("/debug/")
def debug():
    iniciar_verificacao_em_segundo_plano()
    
    linhas_online = [f"<li style='color:#00e676;'><b>[ATIVO] {c.get('nome_formatado')}</b>: ONLINE (Sinal Limpo Chrome 124)</li>" for c in CONTAS_ONLINE_ATIVAS]
    linhas_bloqueadas = [f"<li style='color:#ff5252;'><b>[REMOVIDO] {c.get('nome_formatado')}</b>: BLOQUEADO / OFFLINE</li>" for c in CONTAS_BLOQUEADAS]
    
    html = f"""
    <h2>📊 Painel de Diagnóstico v27 (Anti-Cloudflare Chrome 124)</h2>
    <p><b>Contas Ativas no Roteador:</b> {len(CONTAS_ONLINE_ATIVAS)} | <b>Contas Descartadas:</b> {len(CONTAS_BLOQUEADAS)}</p>
    <h3>✅ Contas Online (Servindo Vídeo)</h3>
    <ul>{''.join(linhas_online) if linhas_online else '<li>Nenhuma conta online no momento</li>'}</ul>
    <h3>❌ Contas Descartadas do Pool</h3>
    <ul>{''.join(linhas_bloqueadas) if linhas_bloqueadas else '<li>Nenhuma conta descartada</li>'}</ul>
    """
    return adicionar_cors(Response(html, content_type="text/html; charset=utf-8"))

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
    return adicionar_cors(Response(m3u_txt, content_type="application/x-mpegURL"))

@app.route("/live/premiere1.ts")
@app.route("/live/premiere.m3u8")
@app.route("/live/premiere1")
@app.route("/live/premiere")
def stream_premiere():
    gerador = tentar_obter_stream_direto()
    if gerador:
        return adicionar_cors(Response(gerador, content_type="video/mp2t"))
    return adicionar_cors(Response("Sinal indisponível no momento. Todas as contas falharam.", status=503, content_type="text/plain; charset=utf-8"))

@app.errorhandler(404)
def erro_404(e):
    return playlist()

if __name__ == "__main__":
    porta = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=porta, debug=False)
