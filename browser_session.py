from config import CHROME_HEADERS

try:
    from curl_cffi import requests
    HAS_CURL_CFFI = True
except ImportError:
    import requests
    HAS_CURL_CFFI = False

def criar_sessao_chrome():
    """
    Cria uma sessão HTTP que simula o Google Chrome 122 real
    para evitar bloqueios da Cloudflare na nuvem.
    """
    if HAS_CURL_CFFI:
        session = requests.Session(impersonate="chrome122")
    else:
        session = requests.Session()
    
    session.headers.update(CHROME_HEADERS)
    return session
