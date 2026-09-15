"""A decisao de triagem e o fluxo que a usa.

Duas pecas, ambas sem dependencia externa:

`TriagemService` recebe uma `Conversa` e a `RespostaLLM` gerada pela IA, e
decide se ela resolve o atendimento ou se a conversa deve ser escalada pra
um humano (ex: a IA pediu escalar explicitamente, ou o numero de tentativas
sem sucesso passou do limite). Repare no que ele *nao* faz: nao gera a
resposta, nao sabe quem a gerou e nao le o texto dela — isso e problema de
um `ProvedorLLM` la em `adapters/`. Ele so decide o que fazer com ela.

`processar_mensagem_recebida` e a funcao que costura o fluxo inteiro:

    1. se a conversa ja saiu das maos da IA (ESCALADA ou ENCERRADA), para
       por aqui — quem conduz dali em diante e o humano;
    2. registra a mensagem do cliente na `Conversa`;
    3. busca trechos relevantes na `BaseConhecimento` (RAG);
    4. se nao veio nenhum trecho, escala na hora — sem chamar o LLM;
    5. pede uma resposta candidata ao `ProvedorLLM`;
    6. entrega essa candidata ao `TriagemService`, que decide;
    7. conforme a decisao, ou responde pelo `Canal` ou aciona o
       `GatewayHandoff`.

Os passos 2, 3 e 5 falam com as interfaces de `ports.py`, nunca com Ollama,
FAISS ou Twilio direto: as implementacoes chegam prontas, passadas como
argumento pelo `main.py`. E por isso que este fluxo pode ser testado
inteiro com adapters falsos, sem nada real rodando.
"""

from dataclasses import dataclass
from datetime import datetime
from enum import Enum

from core.conversa import Autor, Conversa, Mensagem, StatusConversa
from core.ports import (
    BaseConhecimento,
    Canal,
    GatewayHandoff,
    ProvedorLLM,
    RespostaLLM,
)

MOTIVO_SEM_CONTEXTO = (
    "a base de conhecimento nao tem nada relevante pra esta pergunta"
)
"""Motivo do escalonamento quando a recuperacao volta de maos vazias.

Este caminho nem consulta o LLM. A razao esta na Fase 3.1: pedir ao modelo
que admita nao saber nao funciona — ele inventa. Quando a recuperacao ja
disse que o acervo nao cobre a pergunta, nao ha o que a IA possa responder
sem inventar, entao a conversa vai direto pro humano.
"""

MOTIVO_JA_ESCALADA = "a conversa ja esta com um atendente humano"
"""Motivo quando chega mensagem numa conversa que ja foi escalada.

Depois do handoff quem conduz e o humano — e o que o docstring de
`GatewayHandoff.escalar` sempre prometeu ("a IA nao responde mais nessa
conversa"). Sem essa guarda aconteciam duas coisas, as duas observadas na
prova ponta a ponta da Fase 5: a IA respondia por cima do atendente, e uma
segunda decisao de escalar estourava `ValueError` em `Conversa.escalar` —
que no webhook virava HTTP 500, e o Twilio reenvia em 500.
"""

MOTIVO_CONVERSA_ENCERRADA = "a conversa ja foi encerrada"
"""Motivo quando chega mensagem numa conversa encerrada.

Aqui nem se registra a mensagem: `Conversa.registrar_mensagem` recusa uma
conversa ENCERRADA, e com razao. Reabrir atendimento encerrado e uma decisao
de produto que ninguem tomou ainda; por ora a mensagem e ignorada sem
quebrar o processo.
"""

MENSAGEM_DE_ESCALONAMENTO = (
    "Vou transferir voce para um atendente humano. Um momento, por favor."
)
"""O que o cliente recebe quando a conversa escala.

Escalar sem avisar deixa o cliente no vacuo — ele nao sabe nem se a mensagem
chegou. Na prova da Fase 5 isso aconteceu de verdade: a mensagem escalou, o
handoff foi pro log, e do lado do WhatsApp nao chegou nada.

Repare no que este aviso NAO e: ele nao e a resposta candidata da IA. Aquela
continua descartada, porque foi gerada sem a informacao necessaria. Este e
um texto fixo, escrito por nos, que nao tem como alucinar.
"""

LIMITE_TENTATIVAS_PADRAO = 3
"""Quantas respostas da IA sem resolver antes de chamar um humano.

Tres e um meio-termo: da a IA espaco pra se corrigir depois de um
mal-entendido, sem deixar o cliente repetindo a mesma pergunta por muito
tempo. E ajustavel por conversa via `TriagemService(limite_tentativas=...)`.
"""


class Decisao(Enum):
    """O que fazer com a mensagem que acabou de chegar.

    `RESOLVER` e `ESCALAR` sao decisoes sobre a resposta candidata da IA.
    `AGUARDANDO_HUMANO` e diferente: nao ha resposta candidata nenhuma
    porque a IA nem foi consultada — a conversa ja saiu das maos dela.
    """

    RESOLVER = "RESOLVER"
    ESCALAR = "ESCALAR"
    AGUARDANDO_HUMANO = "AGUARDANDO_HUMANO"


@dataclass(frozen=True)
class ResultadoTriagem:
    """A decisao tomada, com o que o chamador precisa pra agir.

    Em `RESOLVER`, `resposta` traz o texto a enviar pro cliente e `motivo` e
    vazio. Em `ESCALAR` e o contrario: `resposta` e `None` (nao ha nada pra
    enviar) e `motivo` explica pro atendente humano por que a conversa caiu
    no colo dele.
    """

    decisao: Decisao
    resposta: str | None = None
    motivo: str = ""

    @classmethod
    def resolver(cls, resposta: str) -> "ResultadoTriagem":
        return cls(decisao=Decisao.RESOLVER, resposta=resposta)

    @classmethod
    def escalar(cls, motivo: str) -> "ResultadoTriagem":
        return cls(decisao=Decisao.ESCALAR, motivo=motivo)

    @classmethod
    def aguardando_humano(cls, motivo: str) -> "ResultadoTriagem":
        return cls(decisao=Decisao.AGUARDANDO_HUMANO, motivo=motivo)


class TriagemService:
    """Decide, a cada resposta da IA, se ela resolve ou se chama um humano.

    Duas regras, nesta ordem:

    1. a IA sinalizou que nao sabe resolver (`resposta.deve_escalar`);
    2. a IA ja tentou `limite_tentativas` vezes nesta conversa e o cliente
       continua voltando — sinal de que ela nao vai chegar la sozinha.

    A regra 1 le um campo, nao o texto: o que a IA escreveu nao influencia
    a decisao, e uma resposta que por acaso fale em "escalar" continua
    sendo uma resposta normal.

    Nao ha estado interno: a contagem de tentativas sai da propria
    `Conversa`, contando as mensagens que a IA ja enviou.
    """

    def __init__(self, limite_tentativas: int = LIMITE_TENTATIVAS_PADRAO) -> None:
        if limite_tentativas < 1:
            raise ValueError(
                f"limite_tentativas precisa ser pelo menos 1, recebido {limite_tentativas}"
            )
        self.limite_tentativas = limite_tentativas

    def decidir(self, conversa: Conversa, resposta: RespostaLLM) -> ResultadoTriagem:
        """Diz se a resposta candidata vai pro cliente ou se a conversa escala."""
        if resposta.deve_escalar:
            return ResultadoTriagem.escalar("a IA sinalizou que nao sabe resolver")

        tentativas = self._tentativas_da_ia(conversa)
        if tentativas >= self.limite_tentativas:
            return ResultadoTriagem.escalar(
                f"a IA ja respondeu {tentativas} vezes sem resolver "
                f"(limite: {self.limite_tentativas})"
            )

        return ResultadoTriagem.resolver(resposta.texto)

    def _tentativas_da_ia(self, conversa: Conversa) -> int:
        return sum(1 for mensagem in conversa.mensagens if mensagem.autor is Autor.IA)


def processar_mensagem_recebida(
    conversa: Conversa,
    texto_cliente: str,
    timestamp: datetime,
    base_conhecimento: BaseConhecimento,
    provedor_llm: ProvedorLLM,
    triagem: TriagemService,
    canal: Canal,
    gateway_handoff: GatewayHandoff,
) -> ResultadoTriagem:
    """Processa uma mensagem do cliente do comeco ao fim, e diz o que houve.

    Quem chama passa as quatro portas ja resolvidas (o `main.py` na vida
    real, adapters falsos nos testes). Esta funcao so sequencia as chamadas
    — a decisao sobre a resposta da IA e delegada ao `TriagemService`.

    A excecao e a checagem de contexto vazio, que fica aqui de proposito: ela
    acontece *antes* de existir qualquer resposta candidata pra triar, entao
    nao teria como morar no `TriagemService`. Quando a recuperacao nao acha
    nada relevante, a conversa escala direto, sem gastar uma chamada de LLM
    pra perguntar ao modelo se ele sabe algo que o acervo nao tem.

    Um detalhe de ordem que muda o comportamento: `triagem.decidir` e
    consultado *antes* de a resposta da IA entrar no historico. Isso mantem
    a contagem de tentativas honesta — ela conta respostas que o cliente
    realmente recebeu. Por consequencia, no caminho de escalonamento a
    resposta candidata e descartada: ela nunca foi entregue, entao nao vira
    `Mensagem` nem conta como tentativa. O atendente humano recebe o motivo
    da triagem, nao o rascunho que a IA nao soube terminar.

    O `timestamp` da mensagem do cliente e reaproveitado na resposta da IA.
    Manter `core/` sem relogio proprio e o que torna estes testes
    deterministicos; quando a precisao importar, quem tem o horario de
    entrega de verdade e o adapter do canal.

    Devolve o `ResultadoTriagem` pra quem chamou poder inspecionar o que
    aconteceu sem ter que deduzir a partir do estado da conversa.
    """
    if conversa.status is StatusConversa.ENCERRADA:
        return ResultadoTriagem.aguardando_humano(MOTIVO_CONVERSA_ENCERRADA)

    if conversa.status is StatusConversa.ESCALADA:
        # A mensagem entra no historico pro atendente ler, e para por aqui.
        conversa.registrar_mensagem(Mensagem(Autor.CLIENTE, texto_cliente, timestamp))
        return ResultadoTriagem.aguardando_humano(MOTIVO_JA_ESCALADA)

    conversa.registrar_mensagem(Mensagem(Autor.CLIENTE, texto_cliente, timestamp))

    trechos = base_conhecimento.buscar_trechos_relevantes(texto_cliente)

    if not trechos:
        return _escalar(
            conversa, ResultadoTriagem.escalar(MOTIVO_SEM_CONTEXTO), canal,
            gateway_handoff,
        )

    resposta_llm = provedor_llm.gerar_resposta(conversa.mensagens, trechos)

    resultado = triagem.decidir(conversa, resposta_llm)

    if resultado.decisao is Decisao.RESOLVER:
        conversa.registrar_mensagem(Mensagem(Autor.IA, resposta_llm.texto, timestamp))
        canal.enviar_mensagem(conversa.conversa_id, resultado.resposta)
    else:
        _escalar(conversa, resultado, canal, gateway_handoff)

    return resultado


def _escalar(
    conversa: Conversa,
    resultado: ResultadoTriagem,
    canal: Canal,
    gateway_handoff: GatewayHandoff,
) -> ResultadoTriagem:
    """Avisa o cliente, marca a conversa e aciona o handoff — nessa ordem.

    O aviso vem primeiro de proposito: se o gateway falhar, o cliente pelo
    menos ja sabe que alguem vai assumir. O contrario deixaria de novo o
    silencio que a prova da Fase 5 expos.

    O aviso nao entra no historico da conversa: ele nao e uma tentativa de
    resposta da IA, e conta-lo como tal estragaria o limite de tentativas.
    """
    canal.enviar_mensagem(conversa.conversa_id, MENSAGEM_DE_ESCALONAMENTO)
    conversa.escalar(resultado.motivo)
    gateway_handoff.escalar(conversa, resumo=resultado.motivo, atributos={})
    return resultado
