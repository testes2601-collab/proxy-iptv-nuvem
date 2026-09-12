# -*- coding: utf-8 -*-
"""
===============================================================================
SERVIDOR PROXY IPTV PREMIUM - VERSÃO 35 (NATIVE HLS .m3u8 SEGMENT STREAMER)
===============================================================================
1. Suporte Nativo a .m3u8: Lê o manifesto .m3u8 da origem, extrai os segmentos .ts
   e faz o download contínuo dos pedaços de vídeo real sem fechar a transmissão.
2. Fallback Inteligente (.m3u8 + .ts): Se a URL em .m3u8 der HTTP 500 (ex: BitUrl),
   tenta automaticamente a versão .ts equivalente.
3. Zero Tela Preta / Loop Infinito: Mantém o player (VLC/Smart TV) sempre conectado.
===============================================================================
"""

import os
import re
import time
import json
import logging
import urllib3
from urllib.parse import urljoin
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

CONTAS_FALLBACK = [
    {
        "id": "play_biturl_36948",
        "nome": "BitUrl - Premiere Opção 1 (ID 36948)",
        "url_direta": "http://play.biturl.vip:80/live/81996133766/hdj2edcoqw/36948.m3u8"
    },
    {
        "id": "play_biturl_40783",
        "nome": "BitUrl - Premiere Opção 2 (ID 40783)",
        "url_direta": "http://play.biturl.vip:80/live/81996133766/hdj2edcoqw/40783.m3u8"
    },
    {
        "id": "49fftq_72265",
        "nome": "49fftq - Premiere 1 (ID 72265)",
        "url_direta": "http://49fftq.live:80/live/QwqUJ8eQ/Vpw3S3/72265.m3u8"
    },
    {
        "id": "49fftq_72262",
        "nome": "49fftq - Premiere 2 (ID 72262)",
        "url_direta": "http://49fftq.live:80/live/QwqUJ8eQ/Vpw3S3/72262.m3u8"
    }
]

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
    return CONTAS_FALLBACK

def criar_sessao():
    if HAS_CURL_CFFI:
        return cffi_requests.Session(impersonate="chrome124")
    return cffi_requests.Session()

def extrair_segmentos_m3u8(conteudo_texto, url_base):
    segmentos = []
    for linha in conteudo_texto.splitlines():
        linha = linha.strip()
        if linha and not linha.startswith("#"):
            url_seg = urljoin(url_base, linha)
            segmentos.append(url_seg)
    return segmentos

def gerador_hls_resiliente():
    contas = carregar_configuracao()
    if not contas:
        return

    idx_conta = 0
    segmentos_vistos = set()

    while True:
        conta = contas[idx_conta % len(contas)]
        nome_conta = conta.get("nome") or conta.get("id") or f"Conta #{idx_conta+1}"
        url_m3u8 = conta.get("url_direta", "")
        
        if not url_m3u8:
            host = conta.get("host", "").rstrip("/")
            user = conta.get("user") or conta.get("username", "")
            password = conta.get("pass") or conta.get("password", "")
            stream_id = conta.get("stream_id", "premiere1")
            url_m3u8 = f"{host}/live/{user}/{password}/{stream_id}.m3u8"

        logging.info(f"📡 Processando manifesto HLS (.m3u8) via: {nome_conta} -> {url_m3u8}")
        
        session = criar_sessao()
        sucesso_conta = False

        try:
            # 1. Tenta buscar o manifesto .m3u8
            r = session.get(url_m3u8, headers=HEADERS_CHROME, timeout=5.0, verify=False)
            
            # Fallback se der 500 ou 404 no .m3u8: tenta o fluxo direto em .ts
            if r.status_code != 200:
                logging.warning(f"🔴 HTTP {r.status_code} no .m3u8 de {nome_conta}. Tentando fallback para .ts...")
                url_ts = url_m3u8.replace(".m3u8", ".ts")
                r_ts = session.get(url_ts, headers=HEADERS_CHROME, stream=True, timeout=6.0, verify=False)
                if r_ts.status_code == 200:
                    for chunk in r_ts.iter_content(chunk_size=32768):
                        if chunk:
                            yield chunk
                            sucesso_conta = True
            else:
                texto_m3u8 = r.text
                # Se for uma playlist master ou de mídia .m3u8 válida
                if "#EXTM3U" in texto_m3u8:
                    segmentos = extrair_segmentos_m3u8(texto_m3u8, url_m3u8)
                    logging.info(f"🟢 {len(segmentos)} segmentos de vídeo localizados em {nome_conta}")
                    
                    for url_seg in segmentos:
                        if url_seg in segmentos_vistos:
                            continue
                        
                        segmentos_vistos.add(url_seg)
                        if len(segmentos_vistos) > 500:
                            segmentos_vistos.clear()

                        r_seg = session.get(url_seg, headers=HEADERS_CHROME, stream=True, timeout=5.0, verify=False)
                        if r_seg.status_code == 200:
                            for chunk in r_seg.iter_content(chunk_size=32768):
                                if chunk:
                                    yield chunk
                                    sucesso_conta = True
                else:
                    # Se não tiver #EXTM3U, pode ser um stream MPEG-TS direto mascarado
                    if len(r.content) > 188 and r.content[0] == 0x47:
                        yield r.content
                        sucesso_conta = True

        except Exception as e:
            logging.warning(f"⚠️ Erro ao processar HLS em {nome_conta}: {e}")
        finally:
            try:
                session.close()
            except Exception:
                pass

        if not sucesso_conta:
            logging.warning(f"⚠️ Falha de transmissão em {nome_conta}. Alternando para próxima conta...")

        idx_conta += 1
        time.sleep(0.2)

def adicionar_cabecalhos_streaming(resposta):
    resposta.headers["Access-Control-Allow-Origin"] = "*"
    resposta.headers["Access-Control-Allow-Headers"] = "*"
    resposta.headers["Access-Control-Allow-Methods"] = "GET, OPTIONS, HEAD"
    resposta.headers["Cache-Control"] = "no-cache, no-store, must-revalidate, private"
    resposta.headers["Pragma"] = "no-cache"
    resposta.headers["Expires"] = "0"
    resposta.headers["X-Accel-Buffering"] = "no"
    return resposta

@app.route("/")
def home():
    return adicionar_cabecalhos_streaming(Response("Servidor Proxy IPTV Premiere 1 (v35 Native HLS m3u8 Streamer)", content_type="text/plain; charset=utf-8"))

@app.route("/debug")
def debug():
    contas = carregar_configuracao()
    return adicionar_cabecalhos_streaming(Response(f"Contas Ativas no Pool: {len(contas)}", content_type="text/plain; charset=utf-8"))

@app.route("/playlist.m3u")
@app.route("/playlist.m3u8")
def playlist():
    host_base = request.host_url.rstrip("/")
    m3u = f'#EXTM3U\n#EXTINF:-1 tvg-id="Premiere1.br" tvg-name="Premiere 1 FHD",Premiere 1 FHD\n{host_base}/live/premiere1.m3u8\n'
    return adicionar_cabecalhos_streaming(Response(m3u, content_type="application/x-mpegURL"))

@app.route("/live/premiere1.m3u8")
@app.route("/live/premiere.m3u8")
@app.route("/live/premiere1.ts")
@app.route("/live/premiere.ts")
def stream():
    return adicionar_cabecalhos_streaming(Response(
        stream_with_context(gerador_hls_resiliente()),
        content_type="video/mp2t"
    ))

if __name__ == "__main__":
    porta = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=porta, debug=False)
