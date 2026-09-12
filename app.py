# -*- coding: utf-8 -*-
"""
===============================================================================
SERVIDOR PROXY IPTV PREMIUM - VERSÃO 36 (Rotação Preventiva 60s & Processador HLS)
===============================================================================
Recursos da versão v36:
1. Rotação Preventiva de 60s: Alterna proativamente de canal a cada 60 segundos
   para evitar o encerramento do token pelo painel de origem e impedir tela preta.
2. Extrator HLS Nativo (.m3u8 -> .ts): Baixa o manifesto .m3u8, extrai os links dos
   segmentos de vídeo (.ts) com seus tokens dinâmicos e repassa em tempo real.
3. Resiliência Total: Troca transparente entre BitUrl e 49fftq sem derrubar a TV/VLC.
4. Desativação Completa de Buffering (X-Accel-Buffering: no).
===============================================================================
"""

import os
import json
import time
import logging
import urllib.parse
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

CONTAS_FALLBACK = [
    {
        "id": "play_biturl_36948",
        "nome": "BitUrl - Premiere 1 (ID 36948)",
        "url_direta": "http://play.biturl.vip:80/live/81996133766/hdj2edcoqw/36948.m3u8"
    },
    {
        "id": "play_biturl_40783",
        "nome": "BitUrl - Premiere 2 (ID 40783)",
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

def obter_sessao():
    if HAS_CURL_CFFI:
        return cffi_requests.Session(impersonate="chrome124")
    return cffi_requests.Session()

def extrair_segmentos_m3u8(session, url_m3u8):
    """
    Baixa o manifesto .m3u8 e extrai as URLs completas dos segmentos .ts
    """
    try:
        res = session.get(url_m3u8, headers=HEADERS_CHROME, timeout=5.0, verify=False)
        if res.status_code == 200 and "#EXTM3U" in res.text:
            linhas = res.text.splitlines()
            segmentos = []
            for linha in linhas:
                linha = linha.strip()
                if linha and not linha.startswith("#"):
                    url_completa = urllib.parse.urljoin(url_m3u8, linha)
                    segmentos.append(url_completa)
            return segmentos
    except Exception as e:
        logging.warning(f"Erro ao extrair manifesto m3u8 de {url_m3u8}: {e}")
    return []

def gerador_stream_v36():
    """
    Gerador Resiliente v36:
    - Roda em loop infinito.
    - Troca de fonte proativamente a cada 60s ou imediatamente em caso de erro.
    - Suporta extração HLS (.m3u8) e fluxo direto (.ts).
    """
    contas = carregar_configuracao()
    if not contas:
        logging.error("❌ Nenhuma conta disponível no pool.")
        return

    idx_conta = 0
    segmentos_vistos = set()

    while True:
        conta = contas[idx_conta % len(contas)]
        nome_conta = conta.get("nome") or conta.get("id") or f"Conta #{idx_conta+1}"
        url_base = conta.get("url_direta") or ""

        if not url_base:
            host = conta.get("host", "").rstrip("/")
            user = conta.get("user") or conta.get("username", "")
            password = conta.get("pass") or conta.get("password", "")
            stream_id = conta.get("stream_id", "72265")
            url_base = f"{host}/live/{user}/{password}/{stream_id}.m3u8"

        logging.info(f"📡 [v36] Iniciando captura via: {nome_conta} -> {url_base}")
        session = obter_sessao()
        tempo_inicio_fonte = time.time()
        sucesso_fonte = False

        try:
            # Se for link .m3u8, processa como lista de segmentos
            if ".m3u8" in url_base.lower():
                while time.time() - tempo_inicio_fonte < 60: # Troca preventiva a cada 60s
                    segmentos = extrair_segmentos_m3u8(session, url_base)
                    
                    # Se falhar o m3u8 (ex: erro 500), tenta fallback para .ts direto
                    if not segmentos:
                        url_ts_fallback = url_base.replace(".m3u8", ".ts")
                        logging.info(f"🔄 Tentando fallback .ts direto para {nome_conta} -> {url_ts_fallback}")
                        try:
                            r_ts = session.get(url_ts_fallback, headers=HEADERS_CHROME, stream=True, timeout=5.0, verify=False)
                            if r_ts.status_code == 200:
                                iterador = r_ts.iter_content(chunk_size=32768)
                                p_chunk = next(iterador, None)
                                if p_chunk and len(p_chunk) >= 188 and p_chunk[0] == 0x47:
                                    logging.info(f"🟢 Fluxo .ts direto ativo via {nome_conta}")
                                    yield p_chunk
                                    for chunk in iterador:
                                        yield chunk
                                        if time.time() - tempo_inicio_fonte >= 60:
                                            logging.info(f"⏱️ Tempo limite de 60s atingido para {nome_conta}. Efetuando rotação preventiva...")
                                            break
                                    break
                        except Exception as e_ts:
                            logging.warning(f"⚠️ Fallback .ts falhou para {nome_conta}: {e_ts}")
                        break # Se não conseguiu segmentos nem .ts, pula para a próxima conta

                    # Baixa os novos segmentos .ts extraídos do manifesto
                    novos_segmentos = [seg for seg in segmentos if seg not in segmentos_vistos]
                    if novos_segmentos:
                        sucesso_fonte = True
                        for seg_url in novos_segmentos:
                            segmentos_vistos.add(seg_url)
                            if len(segmentos_vistos) > 500:
                                segmentos_vistos.clear()

                            try:
                                r_seg = session.get(seg_url, headers=HEADERS_CHROME, timeout=5.0, verify=False)
                                if r_seg.status_code == 200 and len(r_seg.content) > 0:
                                    yield r_seg.content
                            except Exception as e_seg:
                                logging.warning(f"⚠️ Erro ao baixar segmento {seg_url}: {e_seg}")

                    time.sleep(2.0)

            # Se for link .ts direto
            else:
                r = session.get(url_base, headers=HEADERS_CHROME, stream=True, timeout=6.0, verify=False)
                if r.status_code == 200:
                    iterador = r.iter_content(chunk_size=32768)
                    p_chunk = next(iterador, None)
                    if p_chunk and len(p_chunk) >= 188 and p_chunk[0] == 0x47:
                        logging.info(f"🟢 Transmissão .ts ativa via {nome_conta}")
                        yield p_chunk
                        for chunk in iterador:
                            yield chunk
                            if time.time() - tempo_inicio_fonte >= 60:
                                logging.info(f"⏱️ 60s atingidos para {nome_conta}. Rotacionando...")
                                break

        except Exception as e:
            logging.warning(f"⚠️ Falha na fonte {nome_conta}: {e}")
        finally:
            try:
                session.close()
            except Exception:
                pass

        idx_conta += 1
        time.sleep(0.1)

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
    return adicionar_cabecalhos_streaming(Response("Servidor Proxy IPTV Premiere 1 (v36 Active)", content_type="text/plain; charset=utf-8"))

@app.route("/debug")
def debug():
    contas = carregar_configuracao()
    return adicionar_cabecalhos_streaming(Response(f"Contas no Pool: {len(contas)}", content_type="text/plain; charset=utf-8"))

@app.route("/playlist.m3u")
@app.route("/playlist.m3u8")
def playlist():
    host_base = request.host_url.rstrip("/")
    m3u = f"#EXTM3U\n#EXTINF:-1 tvg-id=\"Premiere1.br\" tvg-name=\"Premiere 1 FHD\",Premiere 1 FHD\n{host_base}/live/premiere1.m3u8\n"
    return adicionar_cabecalhos_streaming(Response(m3u, content_type="application/x-mpegURL"))

@app.route("/live/premiere1.m3u8")
@app.route("/live/premiere.m3u8")
@app.route("/live/premiere1.ts")
@app.route("/live/premiere.ts")
def stream():
    return adicionar_cabecalhos_streaming(Response(
        stream_with_context(gerador_stream_v36()),
        content_type="application/x-mpegURL"
    ))

if __name__ == "__main__":
    porta = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=porta, debug=False)
