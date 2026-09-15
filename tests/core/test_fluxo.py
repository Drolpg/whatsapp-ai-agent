"""Testes de `processar_mensagem_recebida` — o fluxo inteiro, ponta a ponta.

As quatro portas sao satisfeitas por classes falsas definidas aqui mesmo.
Repare que nenhuma delas herda de `core.ports`: sao aceitas porque tem os
metodos certos, e e exatamente isso que `Protocol` promete. Nenhum framework
de mock, nenhuma rede, nenhum arquivo.
"""

from datetime import datetime

from core.conversa import Autor, Conversa, Mensagem, StatusConversa
from core.ports import RespostaLLM
from core.triagem import (
    MENSAGEM_DE_ESCALONAMENTO,
    MENSAGEM_FORA_DO_DOMINIO,
    Decisao,
    TriagemService,
    processar_mensagem_recebida,
)

AGORA = datetime(2026, 9, 13, 14, 30)


class FakeBaseConhecimento:
    """Devolve sempre os mesmos trechos, e anota o que lhe perguntaram."""

    def __init__(self, trechos: list[str] | None = None) -> None:
        self.trechos = trechos if trechos is not None else ["trecho A", "trecho B"]
        self.perguntas_recebidas: list[str] = []

    def buscar_trechos_relevantes(self, pergunta: str) -> list[str]:
        self.perguntas_recebidas.append(pergunta)
        return list(self.trechos)


class FakeProvedorLLM:
    """Devolve a resposta combinada no construtor, e guarda o que recebeu."""

    def __init__(self, texto: str, deve_escalar: bool = False) -> None:
        self.resposta = RespostaLLM(texto=texto, deve_escalar=deve_escalar)
        self.mensagens_recebidas: list[tuple[Mensagem, ...]] = []
        self.trechos_recebidos: list[list[str]] = []

    def gerar_resposta(self, mensagens, trechos_contexto: list[str]) -> RespostaLLM:
        self.mensagens_recebidas.append(tuple(mensagens))
        self.trechos_recebidos.append(list(trechos_contexto))
        return self.resposta


class FakeCanal:
    """Nao envia nada — so anota o que teria enviado."""

    def __init__(self) -> None:
        self.enviadas: list[tuple[str, str]] = []

    def enviar_mensagem(self, conversa_id: str, texto: str) -> None:
        self.enviadas.append((conversa_id, texto))


class FakeGatewayHandoff:
    """Nao escala nada — so anota os pedidos de escalonamento."""

    def __init__(self) -> None:
        self.escalonamentos: list[tuple[Conversa, str, dict]] = []

    def escalar(self, conversa: Conversa, resumo: str, atributos: dict) -> None:
        self.escalonamentos.append((conversa, resumo, atributos))


def _processar(
    conversa,
    texto_do_llm,
    deve_escalar=False,
    texto_cliente="qual o horario?",
    limite=3,
    trechos=None,
):
    """Roda o fluxo com fakes, e devolve o resultado junto dos fakes usados."""
    base = FakeBaseConhecimento(trechos)
    llm = FakeProvedorLLM(texto_do_llm, deve_escalar=deve_escalar)
    canal = FakeCanal()
    handoff = FakeGatewayHandoff()

    resultado = processar_mensagem_recebida(
        conversa=conversa,
        texto_cliente=texto_cliente,
        timestamp=AGORA,
        base_conhecimento=base,
        provedor_llm=llm,
        triagem=TriagemService(limite_tentativas=limite),
        canal=canal,
        gateway_handoff=handoff,
    )
    return resultado, base, llm, canal, handoff


def _conversa_com_respostas_da_ia(quantidade: int) -> Conversa:
    """Conversa onde a IA respondeu `quantidade` vezes — com fundamento.

    Estas contam como sucesso, nao como tentativa frustrada: e o que
    distingue um cliente sendo bem atendido de um que a IA nao consegue
    ajudar.
    """
    conversa = Conversa(conversa_id="c1")
    for i in range(quantidade):
        conversa.registrar_mensagem(
            Mensagem(Autor.CLIENTE, f"pergunta {i}", datetime(2026, 9, 13, 10, i * 2))
        )
        conversa.registrar_mensagem(
            Mensagem(Autor.IA, f"resposta util {i}", datetime(2026, 9, 13, 10, i * 2 + 1))
        )
    return conversa


def _conversa_com_tentativas_frustradas(quantidade: int) -> Conversa:
    """Conversa onde a IA ficou `quantidade` vezes seguidas sem ajudar."""
    conversa = Conversa(conversa_id="c1")
    for i in range(quantidade):
        conversa.registrar_mensagem(
            Mensagem(Autor.CLIENTE, f"pergunta {i}", datetime(2026, 9, 13, 10, i * 2))
        )
        conversa.registrar_mensagem(
            Mensagem(
                Autor.IA, MENSAGEM_FORA_DO_DOMINIO, datetime(2026, 9, 13, 10, i * 2 + 1)
            )
        )
    return conversa


class TestClienteBemAtendidoNaoEscala:
    """A regressao que o contador antigo causava, travada pelo fluxo inteiro.

    Somando todas as mensagens da IA, quatro perguntas bem respondidas
    acabavam no humano. Aqui o cenario roda pelo caminho de producao, e nao
    so pela unidade do TriagemService.
    """

    def test_seis_perguntas_respondidas_seguem_com_a_ia(self):
        conversa = Conversa(conversa_id="c1")

        decisoes = []
        for i in range(6):
            resultado, *_ = _processar(
                conversa, f"resposta {i}", texto_cliente=f"pergunta {i}", limite=3
            )
            decisoes.append(resultado.decisao)

        assert all(d is Decisao.RESOLVER for d in decisoes), decisoes
        assert conversa.status is StatusConversa.ATIVA


class TestQuandoAIAResolve:
    def test_devolve_decisao_de_resolver(self):
        resultado, *_ = _processar(Conversa(conversa_id="c1"), "Das 9h as 18h.")

        assert resultado.decisao is Decisao.RESOLVER

    def test_a_resposta_chega_ao_cliente_pelo_canal(self):
        _, _, _, canal, _ = _processar(Conversa(conversa_id="c1"), "Das 9h as 18h.")

        assert canal.enviadas == [("c1", "Das 9h as 18h.")]

    def test_o_handoff_nao_e_acionado(self):
        *_, handoff = _processar(Conversa(conversa_id="c1"), "Das 9h as 18h.")

        assert handoff.escalonamentos == []

    def test_a_conversa_continua_ativa(self):
        conversa = Conversa(conversa_id="c1")

        _processar(conversa, "Das 9h as 18h.")

        assert conversa.status is StatusConversa.ATIVA

    def test_o_historico_guarda_a_pergunta_e_a_resposta_nessa_ordem(self):
        conversa = Conversa(conversa_id="c1")

        _processar(conversa, "Das 9h as 18h.", texto_cliente="qual o horario?")

        assert conversa.mensagens == (
            Mensagem(Autor.CLIENTE, "qual o horario?", AGORA),
            Mensagem(Autor.IA, "Das 9h as 18h.", AGORA),
        )

    def test_o_historico_guarda_o_texto_e_nao_a_RespostaLLM_inteira(self):
        conversa = Conversa(conversa_id="c1")

        _processar(conversa, "Das 9h as 18h.")

        ultima = conversa.mensagens[-1]
        assert isinstance(ultima.conteudo, str)
        assert ultima.conteudo == "Das 9h as 18h."


class TestOQueOFluxoEntregaAsPortas:
    def test_a_base_de_conhecimento_recebe_a_pergunta_do_cliente(self):
        _, base, _, _, _ = _processar(
            Conversa(conversa_id="c1"), "Das 9h as 18h.", texto_cliente="qual o horario?"
        )

        assert base.perguntas_recebidas == ["qual o horario?"]

    def test_o_llm_recebe_os_trechos_da_base_de_conhecimento(self):
        _, base, llm, _, _ = _processar(Conversa(conversa_id="c1"), "Das 9h as 18h.")

        assert llm.trechos_recebidos == [base.trechos]

    def test_o_llm_recebe_o_historico_ja_com_a_pergunta_atual(self):
        conversa = Conversa(conversa_id="c1")

        _, _, llm, _, _ = _processar(
            conversa, "Das 9h as 18h.", texto_cliente="qual o horario?"
        )

        assert llm.mensagens_recebidas == [
            (Mensagem(Autor.CLIENTE, "qual o horario?", AGORA),)
        ]

    def test_o_llm_nao_ve_a_propria_resposta_candidata(self):
        conversa = _conversa_com_respostas_da_ia(1)

        _, _, llm, _, _ = _processar(conversa, "Das 9h as 18h.")

        assert all(
            mensagem.conteudo != "Das 9h as 18h." for mensagem in llm.mensagens_recebidas[0]
        )


class TestQuandoAIAPedeParaEscalar:
    def test_devolve_decisao_de_escalar(self):
        resultado, *_ = _processar(
            Conversa(conversa_id="c1"), "nao sei responder", deve_escalar=True
        )

        assert resultado.decisao is Decisao.ESCALAR

    def test_o_handoff_recebe_o_motivo_da_triagem(self):
        resultado, _, _, _, handoff = _processar(
            Conversa(conversa_id="c1"), "nao sei responder", deve_escalar=True
        )

        assert [resumo for _, resumo, _ in handoff.escalonamentos] == [resultado.motivo]

    def test_o_handoff_recebe_a_conversa_ja_escalada(self):
        conversa = Conversa(conversa_id="c1")

        _, _, _, _, handoff = _processar(conversa, "vou transferir", deve_escalar=True)

        (conversa_escalada, _, _) = handoff.escalonamentos[0]
        assert conversa_escalada is conversa
        assert conversa_escalada.status is StatusConversa.ESCALADA

    def test_o_cliente_recebe_o_aviso_e_nao_a_candidata(self):
        """O texto da IA continua descartado — so o aviso fixo vai."""
        _, _, _, canal, _ = _processar(
            Conversa(conversa_id="c1"), "nao sei responder", deve_escalar=True
        )

        assert canal.enviadas == [("c1", MENSAGEM_DE_ESCALONAMENTO)]
        assert all("nao sei responder" not in t for _, t in canal.enviadas)

    def test_a_conversa_fica_escalada(self):
        conversa = Conversa(conversa_id="c1")

        _processar(conversa, "vou transferir", deve_escalar=True)

        assert conversa.status is StatusConversa.ESCALADA

    def test_a_resposta_candidata_nao_entra_no_historico(self):
        conversa = Conversa(conversa_id="c1")

        _processar(
            conversa, "nao sei", deve_escalar=True, texto_cliente="pergunta dificil"
        )

        assert conversa.mensagens == (
            Mensagem(Autor.CLIENTE, "pergunta dificil", AGORA),
        )

    def test_um_texto_que_parece_resposta_normal_ainda_escala(self):
        """A decisao vem do campo, nao de inspecionar o texto."""
        conversa = Conversa(conversa_id="c1")

        _, _, _, canal, handoff = _processar(
            conversa, "Das 9h as 18h.", deve_escalar=True
        )

        assert all("Das 9h as 18h." not in t for _, t in canal.enviadas)
        assert len(handoff.escalonamentos) == 1


class TestOClienteEAvisadoAoEscalar:
    """Escalar sem avisar deixa o cliente no vacuo.

    Foi o que aconteceu na prova da Fase 5: a mensagem escalou, o handoff
    entrou no log, e do lado do cliente nao chegou absolutamente nada. Ele
    nao tem como saber se a mensagem sequer foi recebida. Enquanto a Fase 6
    nao existe isso e total; mesmo com o Flex pronto, deixar o cliente sem
    retorno enquanto a fila anda nao e aceitavel em atendimento.
    """

    def test_avisa_quando_a_ia_pede_para_escalar(self):
        _, _, _, canal, _ = _processar(
            Conversa(conversa_id="c1"), "nao sei", deve_escalar=True
        )

        assert canal.enviadas == [("c1", MENSAGEM_DE_ESCALONAMENTO)]

    def test_avisa_quando_estoura_o_limite_de_tentativas(self):
        conversa = _conversa_com_tentativas_frustradas(3)

        _, _, _, canal, _ = _processar(conversa, "mais uma tentativa", limite=3)

        assert canal.enviadas == [("c1", MENSAGEM_DE_ESCALONAMENTO)]

    def test_o_aviso_sai_antes_do_handoff(self):
        """Se o gateway falhar, o cliente ja foi avisado."""
        conversa = Conversa(conversa_id="c1")

        _, _, _, canal, handoff = _processar(conversa, "x", deve_escalar=True)

        assert canal.enviadas and handoff.escalonamentos

    def test_o_aviso_nao_conta_como_tentativa_da_ia(self):
        """Ele nao entra no historico: nao e uma tentativa de resposta."""
        conversa = Conversa(conversa_id="c1")

        _processar(conversa, "x", deve_escalar=True, texto_cliente="pergunta")

        assert conversa.mensagens == (
            Mensagem(Autor.CLIENTE, "pergunta", AGORA),
        )

    def test_conversa_ja_escalada_nao_avisa_de_novo(self):
        """Repetir o aviso a cada mensagem viraria spam."""
        conversa = Conversa(conversa_id="c1")
        conversa.escalar(motivo="ja foi")

        _, _, _, canal, _ = _processar(conversa, "x")

        assert canal.enviadas == []


class TestQuandoABaseNaoTemNadaRelevante:
    """Fora do dominio o agente se apresenta, em vez de escalar calado.

    Escalar na primeira mensagem fora do escopo mandava pro humano qualquer
    "oi" ou pergunta de outro assunto — e, antes do aviso de transferencia,
    em silencio absoluto. Agora o agente diz o que sabe responder e da ao
    cliente a chance de reformular.

    Isso passa pela triagem como qualquer outra resposta, entao o limite de
    tentativas continua valendo: quem insiste fora do escopo acaba no humano
    de qualquer forma.
    """

    def test_o_llm_nao_e_chamado(self):
        """Sem acervo nao ha o que fundamentar — perguntar ao modelo so
        convida a alucinacao (ver Fase 3.1)."""
        _, _, llm, _, _ = _processar(
            Conversa(conversa_id="c1"), "resposta que nunca sera gerada", trechos=[]
        )

        assert llm.mensagens_recebidas == []

    def test_o_cliente_recebe_a_apresentacao_do_dominio(self):
        _, _, _, canal, _ = _processar(
            Conversa(conversa_id="c1"), "irrelevante", trechos=[]
        )

        assert canal.enviadas == [("c1", MENSAGEM_FORA_DO_DOMINIO)]

    def test_nao_escala_na_primeira_vez(self):
        resultado, _, _, _, handoff = _processar(
            Conversa(conversa_id="c1"), "irrelevante", trechos=[]
        )

        assert resultado.decisao is Decisao.RESOLVER
        assert handoff.escalonamentos == []

    def test_a_conversa_continua_ativa(self):
        conversa = Conversa(conversa_id="c1")

        _processar(conversa, "irrelevante", trechos=[])

        assert conversa.status is StatusConversa.ATIVA

    def test_a_apresentacao_entra_no_historico(self):
        """Diferente do aviso de transferencia: isto e uma resposta da IA."""
        conversa = Conversa(conversa_id="c1")

        _processar(conversa, "irrelevante", texto_cliente="ola", trechos=[])

        assert conversa.mensagens == (
            Mensagem(Autor.CLIENTE, "ola", AGORA),
            Mensagem(Autor.IA, MENSAGEM_FORA_DO_DOMINIO, AGORA),
        )

    def test_insistir_fora_do_escopo_acaba_escalando(self):
        """O limite de tentativas continua sendo a rede de seguranca."""
        conversa = Conversa(conversa_id="c1")

        decisoes = []
        for _ in range(6):
            resultado, _, _, _, _ = _processar(conversa, "x", trechos=[], limite=3)
            decisoes.append(resultado.decisao)
            if conversa.status is not StatusConversa.ATIVA:
                break

        assert decisoes[0] is Decisao.RESOLVER, "a primeira deve orientar"
        assert decisoes[-1] is Decisao.ESCALAR, "insistir deve acabar no humano"
        assert conversa.status is StatusConversa.ESCALADA
        assert len(decisoes) == 4, f"esperava escalar na 4a, foi na {len(decisoes)}a"

    def test_quando_finalmente_escala_o_cliente_e_avisado(self):
        conversa = _conversa_com_tentativas_frustradas(3)

        _, _, _, canal, handoff = _processar(conversa, "x", trechos=[], limite=3)

        assert canal.enviadas == [("c1", MENSAGEM_DE_ESCALONAMENTO)]
        assert len(handoff.escalonamentos) == 1


class TestQuandoAConversaJaSaiuDasMaosDaIA:
    """Depois do handoff, quem conduz a conversa e o humano.

    Sem esta guarda acontecem duas coisas, as duas vistas na prova ponta a
    ponta da Fase 5: a IA continua respondendo por cima do atendente, e uma
    segunda decisao de escalar estoura `ValueError` em `Conversa.escalar`,
    que vira HTTP 500 no webhook — e o Twilio reenvia em 500, entao o erro
    se repete.
    """

    def _conversa_escalada(self) -> Conversa:
        conversa = Conversa(conversa_id="c1")
        conversa.escalar(motivo="a IA sinalizou que nao sabe resolver")
        return conversa

    def test_nao_chama_o_llm(self):
        _, _, llm, _, _ = _processar(self._conversa_escalada(), "irrelevante")

        assert llm.mensagens_recebidas == []

    def test_nao_responde_ao_cliente(self):
        _, _, _, canal, _ = _processar(self._conversa_escalada(), "irrelevante")

        assert canal.enviadas == []

    def test_nao_escala_de_novo(self):
        """Escalar duas vezes criaria Task duplicada e estourava ValueError."""
        _, _, _, _, handoff = _processar(self._conversa_escalada(), "irrelevante")

        assert handoff.escalonamentos == []

    def test_devolve_decisao_de_aguardar_o_humano(self):
        resultado, *_ = _processar(self._conversa_escalada(), "irrelevante")

        assert resultado.decisao is Decisao.AGUARDANDO_HUMANO

    def test_a_mensagem_do_cliente_entra_no_historico_para_o_atendente(self):
        conversa = self._conversa_escalada()

        _processar(conversa, "irrelevante", texto_cliente="e ai, alguem me ajuda?")

        assert conversa.mensagens == (
            Mensagem(Autor.CLIENTE, "e ai, alguem me ajuda?", AGORA),
        )

    def test_a_conversa_continua_escalada(self):
        conversa = self._conversa_escalada()

        _processar(conversa, "irrelevante")

        assert conversa.status is StatusConversa.ESCALADA

    def test_conversa_encerrada_nao_levanta_nem_registra(self):
        """`registrar_mensagem` recusaria uma conversa ENCERRADA."""
        conversa = Conversa(conversa_id="c1")
        conversa.encerrar()

        resultado, _, llm, canal, handoff = _processar(conversa, "irrelevante")

        assert resultado.decisao is Decisao.AGUARDANDO_HUMANO
        assert conversa.mensagens == ()
        assert llm.mensagens_recebidas == []
        assert canal.enviadas == []
        assert handoff.escalonamentos == []


class TestQuandoEstouraOLimiteDeTentativas:
    def test_a_quarta_pergunta_escala_com_limite_de_tres(self):
        conversa = _conversa_com_tentativas_frustradas(3)

        resultado, *_ = _processar(conversa, "Tente reiniciar o app.", limite=3)

        assert resultado.decisao is Decisao.ESCALAR

    def test_a_terceira_pergunta_ainda_e_respondida_com_limite_de_tres(self):
        conversa = _conversa_com_tentativas_frustradas(2)

        resultado, _, _, canal, _ = _processar(
            conversa, "Tente reiniciar o app.", limite=3
        )

        assert resultado.decisao is Decisao.RESOLVER
        assert canal.enviadas == [("c1", "Tente reiniciar o app.")]

    def test_o_motivo_cita_as_tentativas_e_nao_o_pedido_da_ia(self):
        conversa = _conversa_com_tentativas_frustradas(3)

        resultado, *_ = _processar(conversa, "Tente reiniciar o app.", limite=3)

        assert "3" in resultado.motivo

    def test_o_cliente_nao_recebe_a_resposta_fraca(self):
        conversa = _conversa_com_tentativas_frustradas(3)

        _, _, _, canal, _ = _processar(conversa, "Tente reiniciar o app.", limite=3)

        assert all("Tente reiniciar" not in t for _, t in canal.enviadas)
