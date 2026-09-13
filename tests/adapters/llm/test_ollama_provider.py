"""Testes do `OllamaProvedorLLM` — com rede de verdade, sem mock.

Aqui a regra de `tests/core/` se inverte: o objetivo e justamente provar que
o adapter conversa com o Ollama real. Por isso duas coisas:

1. os testes que precisam do Ollama sao pulados (nao falham) quando ele nao
   esta rodando — a suite continua util numa maquina sem Ollama;
2. as asserts falam da *forma* da resposta (e uma RespostaLLM, o texto nao
   e vazio, deve_escalar e booleano), nunca do conteudo: do outro lado ha um
   modelo de linguagem, e a saida varia a cada chamada.

O caminho de falha (Ollama fora do ar) e o unico deterministico, e nao
precisa de Ollama nenhum pra rodar: basta apontar pra uma porta fechada.
"""

import os
from datetime import datetime

import pytest
import requests

from adapters.llm.ollama_provider import OllamaProvedorLLM
from core.conversa import Autor, Mensagem
from core.ports import RespostaLLM

BASE_URL_PADRAO = "http://localhost:11434"
BASE_URL_INALCANCAVEL = "http://localhost:1"

TRECHOS = [
    "O horario de atendimento da loja e de segunda a sexta, das 9h as 18h.",
    "Aos sabados a loja abre das 9h as 13h. Domingo nao abre.",
]


@pytest.fixture(scope="session")
def base_url() -> str:
    return os.environ.get("OLLAMA_BASE_URL", BASE_URL_PADRAO)


@pytest.fixture(scope="session")
def modelo(base_url: str) -> str:
    """Um modelo que existe neste Ollama, ou pula o teste explicando o motivo.

    Prefere o `OLLAMA_MODEL` do ambiente; se nao houver, usa o primeiro
    modelo que o Ollama listar. Assim o teste roda em qualquer maquina com
    Ollama, sem exigir que todo mundo tenha baixado o mesmo modelo.
    """
    try:
        resposta = requests.get(f"{base_url}/api/tags", timeout=5)
        resposta.raise_for_status()
        disponiveis = [m["name"] for m in resposta.json().get("models", [])]
    except requests.RequestException as erro:
        pytest.skip(
            f"Ollama nao respondeu em {base_url} ({erro.__class__.__name__}). "
            "Suba com `ollama serve` pra rodar este teste."
        )

    if not disponiveis:
        pytest.skip(
            f"o Ollama em {base_url} nao tem nenhum modelo baixado. "
            "Rode `ollama pull llama3.2:3b` (ou outro) pra rodar este teste."
        )

    escolhido = os.environ.get("OLLAMA_MODEL")
    if escolhido and escolhido not in disponiveis:
        pytest.skip(
            f"OLLAMA_MODEL={escolhido} nao esta baixado neste Ollama. "
            f"Disponiveis: {', '.join(disponiveis)}."
        )
    return escolhido or disponiveis[0]


def _pergunta(texto: str) -> list[Mensagem]:
    return [Mensagem(Autor.CLIENTE, texto, datetime(2026, 9, 13, 15, 0))]


class TestContraOllamaReal:
    def test_devolve_uma_RespostaLLM_bem_formada(self, base_url, modelo):
        provedor = OllamaProvedorLLM(base_url=base_url, model=modelo, timeout_segundos=120.0)

        resposta = provedor.gerar_resposta(
            _pergunta("a loja abre no domingo?"), trechos_contexto=TRECHOS
        )

        assert isinstance(resposta, RespostaLLM)
        assert isinstance(resposta.texto, str)
        assert resposta.texto.strip() != ""
        assert isinstance(resposta.deve_escalar, bool)

    def test_leva_o_historico_da_conversa_e_nao_so_a_ultima_mensagem(self, base_url, modelo):
        """Uma conversa com varios turnos precisa ser aceita pela API de chat.

        Nao da pra afirmar que o modelo *usou* o historico — mas da pra
        afirmar que o adapter montou um payload que o Ollama aceitou.
        """
        historico = [
            Mensagem(Autor.CLIENTE, "qual o horario de segunda?", datetime(2026, 9, 13, 15, 0)),
            Mensagem(Autor.IA, "Das 9h as 18h.", datetime(2026, 9, 13, 15, 1)),
            Mensagem(Autor.CLIENTE, "e no sabado?", datetime(2026, 9, 13, 15, 2)),
        ]
        provedor = OllamaProvedorLLM(base_url=base_url, model=modelo, timeout_segundos=120.0)

        resposta = provedor.gerar_resposta(historico, trechos_contexto=TRECHOS)

        assert isinstance(resposta, RespostaLLM)
        assert resposta.texto.strip() != ""

    def test_sem_trechos_de_contexto_ainda_devolve_uma_RespostaLLM(self, base_url, modelo):
        provedor = OllamaProvedorLLM(base_url=base_url, model=modelo, timeout_segundos=120.0)

        resposta = provedor.gerar_resposta(_pergunta("qual o horario?"), trechos_contexto=[])

        assert isinstance(resposta, RespostaLLM)
        assert isinstance(resposta.deve_escalar, bool)


class TestQuandoOOllamaEstaForaDoAr:
    """O caminho de falha, deterministico e sem depender de Ollama nenhum."""

    def _provedor_inalcancavel(self) -> OllamaProvedorLLM:
        return OllamaProvedorLLM(
            base_url=BASE_URL_INALCANCAVEL, model="qualquer", timeout_segundos=2.0
        )

    def test_nao_levanta_excecao(self):
        self._provedor_inalcancavel().gerar_resposta(
            _pergunta("a loja abre no domingo?"), trechos_contexto=TRECHOS
        )

    def test_pede_escalonamento_pelo_campo(self):
        resposta = self._provedor_inalcancavel().gerar_resposta(
            _pergunta("a loja abre no domingo?"), trechos_contexto=TRECHOS
        )

        assert resposta.deve_escalar is True

    def test_o_texto_explica_o_motivo_tecnico(self):
        resposta = self._provedor_inalcancavel().gerar_resposta(
            _pergunta("a loja abre no domingo?"), trechos_contexto=TRECHOS
        )

        assert resposta.texto.strip() != ""

    def test_a_triagem_de_fato_escala_com_essa_resposta(self):
        """O que importa de verdade: a falha vira handoff, nao um erro."""
        from core.conversa import Conversa
        from core.triagem import Decisao, TriagemService

        resposta = self._provedor_inalcancavel().gerar_resposta(
            _pergunta("a loja abre?"), trechos_contexto=[]
        )

        resultado = TriagemService().decidir(Conversa(conversa_id="c1"), resposta)

        assert resultado.decisao is Decisao.ESCALAR
