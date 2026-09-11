# -*- coding: utf-8 -*-
"""
app.py
Servidor Web Flask Principal - Proxy IPTV e Web Player
- Rota / : Página Inicial
- Rota /debug : Painel de Diagnóstico do Pool de Contas
- Rota /watch : Web Player HTML5 (mpegts.js) para Premiere 1 FHD
- Rota /playlist.m3u : Lista M3U gerada dinamicamente
- Rota /live/premiere1.ts : Streaming em tempo real via stream_handler
"""

import os
from flask import Flask, Response, request
from config import PORT
from accounts import gerenciador_contas
from stream_handler import gerar_stream, carregar_canais

app = Flask(__name__)

def adicionar_cors(resposta):
    """Adiciona cabeçalhos CORS para permitir reprodução em qualquer player/navegador."""
    resposta.headers["Access-Control-Allow-Origin"] = "*"
    resposta.headers["Access-Control-Allow-Headers"] = "*"
    resposta.headers["Access-Control-Allow-Methods"] = "GET, OPTIONS, HEAD"
    return resposta

@app.route("/")
def home():
    html_home = """
    <!DOCTYPE html>
    <html lang="pt-BR">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Servidor Proxy IPTV - Premiere 1 FHD</title>
        <style>
            body { font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background-color: #121212; color: #fff; text-align: center; padding: 40px; margin: 0; }
            .card { background-color: #1e1e1e; padding: 30px; border-radius: 12px; display: inline-block; max-width: 650px; box-shadow: 0 4px 15px rgba(0,0,0,0.5); }
            h1 { color: #00e676; font-size: 26px; margin-bottom: 15px; }
            p { color: #ccc; font-size: 15px; line-height: 1.5; }
            .btn { display: inline-block; background-color: #00e676; color: #000; padding: 12px 24px; margin: 10px; border-radius: 6px; font-weight: bold; text-decoration: none; transition: 0.2s; }
            .btn:hover { background-color: #00c853; transform: scale(1.03); }
            .btn-alt { background-color: #29b6f6; }
            .btn-alt:hover { background-color: #0288d1; color: #fff; }
        </style>
    </head>
    <body>
        <div class="card">
            <h1>⚽ Servidor Proxy IPTV - Premiere 1 FHD</h1>
            <p>Servidor ativo com failover automático de contas e proteção anti-Cloudflare.</p>
            <br>
            <a href="/watch" class="btn">📺 Web Player Chrome (/watch)</a>
            <a href="/debug" class="btn btn-alt">📊 Diagnóstico (/debug)</a>
            <a href="/playlist.m3u" class="btn">📋 Baixar Lista M3U (/playlist.m3u)</a>
        </div>
    </body>
    </html>
    """
    return adicionar_cors(Response(html_home, content_type="text/html; charset=utf-8"))

@app.route("/debug")
@app.route("/debug/")
def debug():
    total_contas = gerenciador_contas.total_contas()
    
    html_debug = f"""
    <!DOCTYPE html>
    <html lang="pt-BR">
    <head>
        <meta charset="UTF-8">
        <title>Diagnóstico - Servidor Proxy IPTV</title>
        <style>
            body {{ font-family: Arial, sans-serif; background-color: #121212; color: #fff; padding: 20px; }}
            .container {{ max-width: 800px; margin: 0 auto; background-color: #1e1e1e; padding: 25px; border-radius: 10px; }}
            h2 {{ color: #00e676; border-bottom: 2px solid #00e676; padding-bottom: 10px; }}
            .summary {{ background: #2a2a2a; padding: 15px; border-radius: 6px; margin-bottom: 20px; font-size: 16px; }}
            .btn-voltar {{ display: inline-block; margin-top: 20px; padding: 10px 15px; background-color: #29b6f6; color: #000; font-weight: bold; text-decoration: none; border-radius: 5px; }}
        </style>
    </head>
    <body>
        <div class="container">
            <h2>📊 Painel de Diagnóstico do Pool de Contas</h2>
            <div class="summary">
                <p><b>Total de Contas Carregadas:</b> <span style="color: #00e676;">{total_contas}</span></p>
                <p><b>Canal Ativo no Proxy:</b> Premiere 1 FHD (premiere1.ts)</p>
                <p><b>Status da Sessão:</b> Impersonate Chrome 122 (Anti-Cloudflare Ativo)</p>
            </div>
            <a href="/" class="btn-voltar">← Voltar para o Início</a>
        </div>
    </body>
    </html>
    """
    return adicionar_cors(Response(html_debug, content_type="text/html; charset=utf-8"))

@app.route("/watch")
@app.route("/watch/")
def watch():
    html_watch = """
    <!DOCTYPE html>
    <html lang="pt-BR">
    <head>
        <meta charset="UTF-8">
        <title>Web Player - Premiere 1 FHD</title>
        <script src="https://cdn.jsdelivr.net/npm/mpegts.js@1.7.3/dist/mpegts.min.js"></script>
        <style>
            body { font-family: Arial, sans-serif; background-color: #0a0a0a; color: #fff; text-align: center; margin: 0; padding: 20px; }
            .player-box { max-width: 900px; margin: 20px auto; background-color: #161616; padding: 20px; border-radius: 12px; box-shadow: 0 4px 20px rgba(0,0,0,0.8); }
            h1 { color: #00e676; font-size: 22px; margin-bottom: 10px; }
            video { width: 100%; height: 500px; background-color: #000; border-radius: 8px; }
            .badge { background-color: #ff1744; color: #fff; padding: 4px 10px; border-radius: 4px; font-weight: bold; font-size: 12px; vertical-align: middle; }
        </style>
    </head>
    <body>
        <div class="player-box">
            <h1>⚽ Premiere 1 FHD <span class="badge">AO VIVO</span></h1>
            <p>Reprodutor HTML5 integrado com decodificação MPEG-TS em tempo real</p>
            <video id="videoElement" controls autoplay muted></video>
        </div>
        <script>
            if (mpegts.getFeatureList().isSupported) {
                var videoElement = document.getElementById('videoElement');
                var player = mpegts.createPlayer({
                    type: 'mse',
                    isLive: true,
                    url: '/live/premiere1.ts'
                });
                player.attachMediaElement(videoElement);
                player.load();
                player.play();
            } else {
                alert('Seu navegador não possui suporte para o mpegts.js.');
            }
        </script>
    </body>
    </html>
    """
    return adicionar_cors(Response(html_watch, content_type="text/html; charset=utf-8"))

@app.route("/playlist.m3u")
def playlist():
    host_base = request.host_url.rstrip("/")
    m3u_txt = f"""#EXTM3U
#EXTINF:-1 tvg-id="Premiere1.br" tvg-name="Premiere 1 FHD" tvg-logo="https://i.imgur.com/8Q9Z3v1.png" group-title="ESPORTES",Premiere 1 FHD
{host_base}/live/premiere1.ts
"""
    return adicionar_cors(Response(m3u_txt, content_type="application/x-mpegURL"))

@app.route("/live/premiere1.ts")
@app.route("/live/premiere.m3u8")
def stream_premiere():
    fluxo = gerar_stream("premiere1")
    return adicionar_cors(Response(fluxo, content_type="video/mp2t"))

@app.errorhandler(404)
def erro_404(e):
    msg = """
    <h2>⚠️ Página Não Encontrada (Erro 404)</h2>
    <p>Rota indisponível. Acesse uma das rotas válidas:</p>
    <ul>
        <li><a href="/">Página Inicial (/)</a></li>
        <li><a href="/watch">Web Player (/watch)</a></li>
        <li><a href="/debug">Painel de Diagnóstico (/debug)</a></li>
        <li><a href="/playlist.m3u">Lista M3U (/playlist.m3u)</a></li>
    </ul>
    """
    return adicionar_cors(Response(msg, status=404, content_type="text/html; charset=utf-8"))

if __name__ == "__main__":
    porta = int(os.environ.get("PORT", PORT))
    app.run(host="0.0.0.0", port=porta, debug=False)
