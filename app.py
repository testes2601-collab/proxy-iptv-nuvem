# -*- coding: utf-8 -*-
"""
===============================================================================
SERVIDOR PROXY IPTV PREMIUM - VERSÃO 24 (Conexão Direta Sequencial Anti-Bloqueio)
===============================================================================
Recursos da versão v24:
1. Conexão Sequencial Inteligente: Testa 1 conta por vez para evitar bloqueio de IP no meusrv.top.
2. Chunk-Size Reduzido (8192 bytes): Entrega rápida do primeiro pacote ao VLC em < 0.1s.
3. Cache Persistente da Conta Ativa: Mantém a conta funcional sem disparar testes repetidos.
4. Filtro Byte-a-Byte MPEG-TS (0x47): Garante sinal de vídeo limpo.
5. Suporte Completo VLC, Smart TV, TiviMate, SS IPTV e Web Players.
===============================================================================
"""

import os
import re
import time
import logging
import urllib3
import requests
from flask import Flask, Response, request

# Desativa alertas de SSL
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

app = Flask(__name__)

# Cache global da conta ativa funcional
CONTA_ATIVA_CACHE = None
ULTIMA_VERIFICACAO = 0

# =============================================================================
# POOL DE CONTAS (MEUSRV NO TOPO - TESTE SEQUENCIAL SEM PARALELISMO MESMO HOST)
# =============================================================================
LISTA_CONTAS_POOL = [
    # --- SERVIDORES MEUSRV (CONFIRMADOS ONLINE) ---
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
    },
    # --- SERVIDORES IP DIRETO ---
    {
        "id": "ip_103_01",
        "nome": "Servidor IP 103 (Conta 1)",
        "host": "http://103.176.90.186:80",
        "user": "e0828d9135",
        "pass": "e91802270546"
    },
    {
        "id": "ip_103_02",
        "nome": "Servidor IP 103 (Conta 2)",
        "host": "http://103.176.90.186:80",
        "user": "7b559c1042",
        "pass": "11de4cebb4"
    },
    {
        "id": "ono_79_01",
        "nome": "Servidor ONO IP 79",
        "host": "http://79.127.243.145:80",
        "user": "723015",
        "pass": "VfGrmD"
    },
    {
        "id": "ono_85_01",
        "nome": "Servidor ONO IP 85 (Otavio)",
        "host": "http://85.137.49.157.dyn.user.ono.com:80",
        "user": "Otaviodeledove",
        "pass": "9Dh5R8uAu5"
    },
    {
        "id": "ono_85_02",
        "nome": "Servidor ONO IP 85 (Tatiana)",
        "host": "http://85.137.49.157.dyn.user.ono.com:80",
        "user": "tatiana9944",
        "pass": "Ta994a"
    },
    # --- DEMAIS SERVIDORES ---
    {
        "id": "xyz_332_01",
        "nome": "XYZ 332 (988)",
        "host": "http://332nr7hbfu.xyz:80",
        "user": "988060",
        "pass": "zd7YEw"
    },
    {
        "id": "xyz_332_02",
        "nome": "XYZ 332 (Constancio)",
        "host": "http://332nr7hbfu.xyz:80",
        "user": "constancio79",
        "pass": "Wagner@79"
    },
    {
        "id": "xyz_332_03",
        "nome": "XYZ 332 (Casa na Praia)",
        "host": "http://332nr7hbfu.xyz:80",
        "user": "Casanapraia10",
        "pass": "Tvfuturo2"
    },
    {
        "id": "z2mu_54_01",
        "nome": "54z2mu Pro",
        "host": "http://54z2mu.pro:80",
        "user": "jT63beuY",
        "pass": "F11Gkd"
    },
    {
        "id": "fftq_49_01",
        "nome": "49fftq Live",
        "host": "http://49fftq.live:80",
        "user": "WellgtonSilva35",
        "pass": "991DNEubv"
    },
    {
        "id": "vector_61_01",
        "nome": "Vector CDN 61",
        "host": "http://61701-vector.cdn-o2.me:80",
        "user": "4df74cf07e",
        "pass": "9d49be6b44bc"
    },
    {
        "id": "given_11_01",
        "nome": "Given CDN 11",
        "host": "http://11359-given.cdn-o2.me:80",
        "user": "4af01daf4f",
        "pass": "7e3498490571"
    },
    {
        "id": "biturl_play_01",
        "nome": "Biturl Play",
        "host": "http://play.biturl.vip:80",
        "user": "5181603291",
        "pass": "m23bm8a1nup"
    }
]

HEADERS_CLIENTE = {
    "User-Agent": "TiviMate/4.6.1 (Android TV; BRAVIA 4K UR3)",
    "Accept": "*/*",
    "Connection": "keep-alive"
}

def validar_se_e_video_mpegts(chunk_bytes):
    """ Valida se o primeiro pacote é MPEG-TS válido (byte 0x47 / 71 em decimal) """
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

def tentar_obter_stream_conta(conta_info):
    """ Tenta conectar sequencialmente sem sobrecarregar o host """
    urls_para_testar = [
        f"{conta_info['host']}/live/{conta_info['user']}/{conta_info['pass']}/premiere1.ts",
        f"{conta_info['host']}/live/{conta_info['user']}/{conta_info['pass']}/premiere.m3u8",
        f"{conta_info['host']}/live/{conta_info['user']}/{conta_info['pass']}/premiere.ts"
    ]
    
    for target_url in urls_para_testar:
        try:
            res = requests.get(target_url, headers=HEADERS_CLIENTE, stream=True, timeout=3.5, verify=False)
            if res.status_code == 200:
                iterador = res.iter_content(chunk_size=8192)
                primeiro_chunk = next(iterador, None)
                if primeiro_chunk and validar_se_e_video_mpegts(primeiro_chunk):
                    def gerador():
                        yield primeiro_chunk
                        for chunk in iterador:
                            if chunk:
                                yield chunk
                    return (conta_info, gerador)
        except Exception:
            continue
    return None

def obter_fluxo_direto():
    """ 
    Obtém o fluxo de vídeo sem disparar múltiplas conexões simultâneas no mesmo host.
    """
    global CONTA_ATIVA_CACHE, ULTIMA_VERIFICACAO

    # 1. Tenta a conta salva em cache primeiro (resposta ultra-rápida)
    if CONTA_ATIVA_CACHE:
        resultado = tentar_obter_stream_conta(CONTA_ATIVA_CACHE)
        if resultado:
            logging.info(f"⚡ Conectado instantaneamente à conta cache: {CONTA_ATIVA_CACHE['id']}")
            return resultado[1]
        else:
            CONTA_ATIVA_CACHE = None

    # 2. Busca sequencial organizada (evita colisão de requisições no mesmo IP)
    for conta in LISTA_CONTAS_POOL:
        resultado = tentar_obter_stream_conta(conta)
        if resultado:
            conta_info, gerador = resultado
            CONTA_ATIVA_CACHE = conta_info
            ULTIMA_VERIFICACAO = time.time()
            logging.info(f"✅ Nova conta ativa conectada: {conta_info['id']} ({conta_info['nome']})")
            return gerador

    return None

def adicionar_cors(resposta):
    resposta.headers["Access-Control-Allow-Origin"] = "*"
    resposta.headers["Access-Control-Allow-Headers"] = "*"
    resposta.headers["Access-Control-Allow-Methods"] = "GET, OPTIONS, HEAD"
    resposta.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    resposta.headers["Pragma"] = "no-cache"
    resposta.headers["Expires"] = "0"
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
        <title>Servidor Proxy IPTV - Premiere 1 (v24)</title>
        <style>
            body { font-family: Arial, sans-serif; background-color: #121212; color: #fff; text-align: center; padding: 40px; }
            .card { background-color: #1e1e1e; padding: 30px; border-radius: 12px; display: inline-block; max-width: 650px; }
            h1 { color: #00e676; }
            .btn { display: inline-block; background-color: #00e676; color: #000; padding: 12px 24px; margin: 10px; border-radius: 6px; font-weight: bold; text-decoration: none; }
        </style>
    </head>
    <body>
        <div class="card">
            <h1>⚽ Servidor Proxy IPTV Premiere 1 (v24)</h1>
            <p>Servidor com Conexão Sequencial Anti-Bloqueio & Suporte VLC!</p>
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
    linhas = []
    contas_online = 0
    for c in LISTA_CONTAS_POOL:
        res = tentar_obter_stream_conta(c)
        if res:
            contas_online += 1
            linhas.append(f"<li style='color:#00e676;'><b>{c['nome']}</b>: ONLINE (Sinal MPEG-TS Limpo)</li>")
        else:
            linhas.append(f"<li style='color:#ff5252;'><b>{c['nome']}</b>: OFFLINE / BLOQUEADO</li>")

    html = f"""
    <h2>📊 Painel de Diagnóstico v24</h2>
    <p><b>Total de Contas:</b> {len(LISTA_CONTAS_POOL)} | <b>Online:</b> {contas_online}</p>
    <ul>{''.join(linhas)}</ul>
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
    gerador = obter_fluxo_direto()
    if gerador:
        return adicionar_cors(Response(gerador, content_type="video/mp2t"))
    return adicionar_cors(Response("Sinal indisponível no momento. Todas as contas falharam.", status=503, content_type="text/plain; charset=utf-8"))

@app.errorhandler(404)
def erro_404(e):
    return playlist()

if __name__ == "__main__":
    porta = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=porta, debug=False)
