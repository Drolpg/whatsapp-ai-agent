"""Testes do `TriagemService` — a decisao entre resolver e escalar.

Objetos Python puros: nenhuma chamada de rede, nenhum arquivo, nenhum mock.
A "resposta candidata da IA" e so uma string; quem a produziu (Ollama,
Anthropic, ou este teste) nao faz diferenca pra decisao.
"""

from datetime import datetime

import pytest

from core.conversa import Autor, Conversa, Mensagem
from core.triagem import MARCADOR_ESCALAR, Decisao, TriagemService


def _conversa_com(tentativas_da_ia: int = 0) -> Conversa:
    """Uma conversa onde a IA ja respondeu `tentativas_da_ia` vezes sem resolver."""
    conversa = Conversa(conversa_id="c1")
    for i in range(tentativas_da_ia):
        conversa.registrar_mensagem(
            Mensagem(Autor.CLIENTE, f"pergunta {i}", datetime(2026, 9, 12, 10, i * 2))
        )
        conversa.registrar_mensagem(
            Mensagem(Autor.IA, f"resposta {i}", datetime(2026, 9, 12, 10, i * 2 + 1))
        )
    return conversa


class TestResolvidoSemEscalar:
    def test_resposta_normal_em_conversa_nova_resolve(self):
        resultado = TriagemService().decidir(_conversa_com(), "O horario e das 9h as 18h.")

        assert resultado.decisao is Decisao.RESOLVER

    def test_a_resposta_da_ia_e_preservada_intacta(self):
        resultado = TriagemService().decidir(_conversa_com(), "O horario e das 9h as 18h.")

        assert resultado.resposta == "O horario e das 9h as 18h."

    def test_resolve_enquanto_estiver_dentro_do_limite_de_tentativas(self):
        servico = TriagemService(limite_tentativas=3)

        resultado = servico.decidir(_conversa_com(tentativas_da_ia=2), "Tente reiniciar o app.")

        assert resultado.decisao is Decisao.RESOLVER


class TestEscaladoPorPedidoExplicitoDaIA:
    def test_marcador_na_resposta_escala(self):
        resultado = TriagemService().decidir(
            _conversa_com(), f"{MARCADOR_ESCALAR} nao tenho essa informacao"
        )

        assert resultado.decisao is Decisao.ESCALAR

    def test_escala_mesmo_na_primeira_mensagem_da_conversa(self):
        conversa = _conversa_com(tentativas_da_ia=0)

        resultado = TriagemService(limite_tentativas=3).decidir(conversa, MARCADOR_ESCALAR)

        assert resultado.decisao is Decisao.ESCALAR

    def test_o_marcador_e_reconhecido_sem_diferenciar_maiusculas(self):
        resultado = TriagemService().decidir(_conversa_com(), MARCADOR_ESCALAR.lower())

        assert resultado.decisao is Decisao.ESCALAR

    def test_o_motivo_explica_que_partiu_da_ia(self):
        resultado = TriagemService().decidir(_conversa_com(), MARCADOR_ESCALAR)

        assert "IA" in resultado.motivo

    def test_nao_sobra_resposta_para_enviar_ao_cliente(self):
        resultado = TriagemService().decidir(_conversa_com(), MARCADOR_ESCALAR)

        assert resultado.resposta is None


class TestEscaladoPorNumeroDeTentativas:
    def test_escala_quando_a_ia_ja_tentou_o_limite_de_vezes(self):
        servico = TriagemService(limite_tentativas=3)

        resultado = servico.decidir(_conversa_com(tentativas_da_ia=3), "Tente de novo mais tarde.")

        assert resultado.decisao is Decisao.ESCALAR

    def test_o_motivo_cita_o_numero_de_tentativas(self):
        servico = TriagemService(limite_tentativas=3)

        resultado = servico.decidir(_conversa_com(tentativas_da_ia=3), "Tente de novo.")

        assert "3" in resultado.motivo

    def test_o_limite_e_configuravel(self):
        servico = TriagemService(limite_tentativas=1)

        resultado = servico.decidir(_conversa_com(tentativas_da_ia=1), "Tente de novo.")

        assert resultado.decisao is Decisao.ESCALAR

    def test_mensagens_do_cliente_nao_contam_como_tentativa_da_ia(self):
        conversa = Conversa(conversa_id="c1")
        for i in range(5):
            conversa.registrar_mensagem(
                Mensagem(Autor.CLIENTE, f"pergunta {i}", datetime(2026, 9, 12, 10, i))
            )

        resultado = TriagemService(limite_tentativas=3).decidir(conversa, "Claro, posso ajudar.")

        assert resultado.decisao is Decisao.RESOLVER


class TestLimiteInvalido:
    def test_limite_menor_que_um_e_recusado_na_construcao(self):
        with pytest.raises(ValueError):
            TriagemService(limite_tentativas=0)
