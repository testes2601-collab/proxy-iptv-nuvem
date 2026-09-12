# -*- coding: utf-8 -*-
"""
===============================================================================
SERVIDOR PROXY IPTV PREMIUM - VERSÃO 32 (Loop Infinito & Auto-Recuperação Anti-Tela Preta)
===============================================================================
Recursos da versão v32:
1. Loop Infinito Permanente (`while True`): Nunca encerra a busca por sinal.
2. Permanência em URL Estável: Enquanto a URL atual enviar vídeo válido (0x47),
   o proxy PERMANECE NELA indefinidamente.
3. Rotação Automática ao Detectar Travamento: Se o sinal ameaçar cair/travar/dar tela preta,
   o proxy pula IMEDIATAMENTE para a próxima URL do pool.
4. Ciclo Contínuo Completo: Quando percorre todas as URLs, volta automaticamente
   para a primeira URL do topo e reinicia a busca sem fechar a conexão no VLC / TV.
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

CONTAS_FALLBACK = [
    {
        "id": "play_biturl_36948",
        "nome": "BitUrl - Premiere Opção 1",
        "host": "http://play.biturl.vip:80",
        "user": "81996133766",
        "pass": "hdj2edcoqw",
        "stream_id": "36948",
        "url_direta": "http://play.biturl.vip:80/live/81996133766/hdj2edcoqw/36948.ts"
    },
    {
        "id": "play_biturl_40783",
        "nome": "BitUrl - Premiere Opção 2",
        "host": "http://play.biturl.vip:80",
        "user": "81996133766",
        "pass": "hdj2edcoqw",
        "stream_id": "40783",
        "url_direta": "http://play.biturl.vip:80/live/81996133766/hdj2edcoqw/40783.ts"
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
                    if isinstance(dados, dict) and "contas" in dados and len(dados["contas"]) > 0:
                        return dados["contas"]
                    elif isinstance(dados, list) and len(dados) > 0:
                        return dados
            except Exception as e:
                logging.warning(f"Erro ao ler {arq}: {e}")
    return CONTAS_FALLBACK

def obter_url_canal(conta):
    if "url_direta" in conta and conta["url_direta"]:
        return conta["url_direta"].replace(".m3u8", ".ts")
    host = conta.get("host", "").rstrip("/")
    user = conta.get("user") or conta.get("username", "")
    password = conta.get("pass") or conta.get("password", "")
    stream_id = conta.get("stream_id", "premiere1")
    return f"{host}/live/{user}/{password}/{stream_id}.ts"

def criar_sessao():
    if HAS_CURL_CFFI:
        return cffi_requests.Session(impersonate="chrome124")
    return cffi_requests.Session()

def validar_chunk_mpegts(chunk):
    """ Valida se o pacote recebido é MPEG-TS válido (0x47) e não HTML/Erro """
    if not chunk or len(chunk) < 188:
        return False
    if chunk[0] != 0x47:
        return False
    amostra = chunk[:1024].lower()
    termos_invalidos = [b"<html", b"<!doctype", b"cloudflare", b"restricted", b"access denied", b"error 1020"]
    for termo in termos_invalidos:
        if termo in amostra:
            return False
    return True

def gerador_loop_infinito_anti_tela_preta():
    """
    GERADOR EM LOOP INFINITO:
    1. Permanece na mesma URL ENQUANTO o sinal estiver estável e enviando chunks de vídeo.
    2. Se a URL ameaçar travar / dar tela preta (falha de rede, timeout, drop da Cloudflare),
       avança imediatamente para a próxima URL.
    3. Percorre todas as URLs do pool e, ao chegar no fim, VOLTA PARA A PRIMEIRA (ciclo contínuo).
    """
    idx_conta = 0

    while True:
        contas = carregar_configuracao()
        if not contas:
            time.sleep(1)
            continue

        # Garante índice dentro do limite da lista atualizada
        idx_conta = idx_conta % len(contas)
        conta = contas[idx_conta]
        url_target = obter_url_canal(conta)
        nome_conta = conta.get("nome") or conta.get("id") or f"Opção #{idx_conta+1}"

        logging.info(f"📡 Conectando ao sinal -> [{idx_conta+1}/{len(contas)}] {nome_conta}")

        session = criar_sessao()

        try:
            r = session.get(url_target, headers=HEADERS_CHROME, stream=True, timeout=6.0, verify=False)
            if r.status_code == 200:
                iterador = r.iter_content(chunk_size=32768)
                primeiro_chunk = next(iterador, None)

                if primeiro_chunk and validar_chunk_mpegts(primeiro_chunk):
                    logging.info(f"🟢 Transmissão ESTÁVEL iniciada via: {nome_conta}")
                    yield primeiro_chunk

                    # PERMANECE NESTA URL ENQUANTO ESTIVER ENVIANDO CHUNKS VÁLIDOS
                    for chunk in iterador:
                        if chunk:
                            yield chunk
                        else:
                            logging.warning(f"⚠️ Fluxo de vídeo interrompido em {nome_conta}. Ameaçando tela preta!")
                            break
                else:
                    logging.warning(f"⚠️ {nome_conta} retornou dados inválidos/erro (não é MPEG-TS 0x47).")
            else:
                logging.warning(f"🔴 Resposta HTTP {r.status_code} recebida de {nome_conta}.")
        except Exception as err:
            logging.warning(f"⚠️ Falha de leitura/conexão em {nome_conta}: {err}")
        finally:
            try:
                session.close()
            except Exception:
                pass

        # Se o sinal caiu ou ameaçou travar, avança para a próxima URL no loop infinito
        idx_conta = (idx_conta + 1) % len(contas)
        logging.info(f"🔄 Alternando para a próxima URL no loop -> Índice [{idx_conta+1}/{len(contas)}]")
        time.sleep(0.05)

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
    return adicionar_cabecalhos_streaming(Response("Servidor Proxy IPTV Premiere 1 (v32 Infinite Anti-Freeze Loop)", content_type="text/plain; charset=utf-8"))

@app.route("/debug")
def debug():
    contas = carregar_configuracao()
    return adicionar_cabecalhos_streaming(Response(f"Contas Ativas no Pool: {len(contas)}", content_type="text/plain; charset=utf-8"))

@app.route("/playlist.m3u")
@app.route("/playlist.m3u8")
def playlist():
    host_base = request.host_url.rstrip("/")
    m3u = f"#EXTM3U\n#EXTINF:-1 tvg-id=\"Premiere1.br\" tvg-name=\"Premiere 1 FHD\",Premiere 1 FHD\n{host_base}/live/premiere1.ts\n"
    return adicionar_cabecalhos_streaming(Response(m3u, content_type="application/x-mpegURL"))

@app.route("/live/premiere1.ts")
@app.route("/live/premiere.m3u8")
@app.route("/live/premiere1.m3u8")
@app.route("/live/premiere.ts")
def stream():
    return adicionar_cabecalhos_streaming(Response(
        stream_with_context(gerador_loop_infinito_anti_tela_preta()),
        content_type="video/mp2t"
    ))

if __name__ == "__main__":
    porta = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=porta, debug=False)
