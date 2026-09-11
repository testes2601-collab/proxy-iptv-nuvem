# accounts.py
"""
Gerenciador Circular de Contas (Round-Robin com Failover)
"""

import json
import os
import threading

ARQUIVO_CONTAS = "contasonlinefiltradas.json"

class GerenciadorContas:
    def __init__(self, caminho_json=ARQUIVO_CONTAS):
        self.caminho_json = caminho_json
        self.contas = []
        self.index_atual = 0
        self.lock = threading.Lock()
        self.carregar_contas()

    def carregar_contas(self):
        """Carrega as contas ativas do arquivo JSON de forma segura."""
        if not os.path.exists(self.caminho_json):
            self.contas = []
            return

        try:
            with open(self.caminho_json, "r", encoding="utf-8") as f:
                dados = json.load(f)
                self.contas = [c for c in dados if c.get("status", True)]
        except Exception:
            self.contas = []

    def obter_proxima_conta(self):
        """Retorna a próxima conta da fila circular de forma thread-safe."""
        with self.lock:
            if not self.contas:
                self.carregar_contas()
                if not self.contas:
                    return None

            conta = self.contas[self.index_atual]
            self.index_atual = (self.index_atual + 1) % len(self.contas)
            return conta

    def total_contas(self):
        return len(self.contas)

# Instância global reutilizável
gerenciador_contas = GerenciadorContas()
