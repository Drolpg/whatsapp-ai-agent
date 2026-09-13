"""A decisao de triagem e o fluxo que a usa.

Duas pecas, ambas sem dependencia externa:

`TriagemService` recebe uma `Conversa` e a `RespostaLLM` gerada pela IA, e
decide se ela resolve o atendimento ou se a conversa deve ser escalada pra
um humano (ex: a IA pediu escalar explicitamente, ou o numero de tentativas
sem sucesso passou do limite). Repare no que ele *nao* faz: nao gera a
resposta, nao sabe quem a gerou e nao le o texto dela — isso e problema de
um `ProvedorLLM` la em `adapters/`. Ele so decide o que fazer com ela.

`processar_mensagem_recebida` e a funcao que costura o fluxo inteiro:

    1. registra a mensagem do cliente na `Conversa`;
    2. busca trechos relevantes na `BaseConhecimento` (RAG);
    3. pede uma resposta candidata ao `ProvedorLLM`;
    4. entrega essa candidata ao `TriagemService`, que decide;
    5. conforme a decisao, ou responde pelo `Canal` ou aciona o
       `GatewayHandoff`.

Os passos 2, 3 e 5 falam com as interfaces de `ports.py`, nunca com Ollama,
FAISS ou Twilio direto: as implementacoes chegam prontas, passadas como
argumento pelo `main.py`. E por isso que este fluxo pode ser testado
inteiro com adapters falsos, sem nada real rodando.
"""

from dataclasses import dataclass
from datetime import datetime
from enum import Enum

from core.conversa import Autor, Conversa, Mensagem
from core.ports import (
    BaseConhecimento,
    Canal,
    GatewayHandoff,
    ProvedorLLM,
    RespostaLLM,
)

LIMITE_TENTATIVAS_PADRAO = 3
"""Quantas respostas da IA sem resolver antes de chamar um humano.

Tres e um meio-termo: da a IA espaco pra se corrigir depois de um
mal-entendido, sem deixar o cliente repetindo a mesma pergunta por muito
tempo. E ajustavel por conversa via `TriagemService(limite_tentativas=...)`.
"""


class Decisao(Enum):
    """O que fazer com a resposta candidata da IA."""

    RESOLVER = "RESOLVER"
    ESCALAR = "ESCALAR"


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
    real, adapters falsos nos testes). Esta funcao so sequencia as chamadas:
    a unica decisao que existe aqui e delegada ao `TriagemService`.

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
    conversa.registrar_mensagem(Mensagem(Autor.CLIENTE, texto_cliente, timestamp))

    trechos = base_conhecimento.buscar_trechos_relevantes(texto_cliente)
    resposta_llm = provedor_llm.gerar_resposta(conversa.mensagens, trechos)

    resultado = triagem.decidir(conversa, resposta_llm)

    if resultado.decisao is Decisao.RESOLVER:
        conversa.registrar_mensagem(Mensagem(Autor.IA, resposta_llm.texto, timestamp))
        canal.enviar_mensagem(conversa.conversa_id, resultado.resposta)
    else:
        conversa.escalar(resultado.motivo)
        gateway_handoff.escalar(conversa, resumo=resultado.motivo, atributos={})

    return resultado
