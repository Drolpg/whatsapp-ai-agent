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
    4. se nao veio nenhum trecho, responde com a apresentacao do escopo,
       sem chamar o LLM;
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

MENSAGEM_FORA_DO_DOMINIO = (
    "Posso ajudar com horario de funcionamento, endereco da loja, telefone e "
    "e-mail de contato, e com pedidos — acompanhar, alterar, cancelar ou "
    "retirar. E sobre algum desses assuntos?"
)
"""O que o agente responde quando a recuperacao volta de maos vazias.

Antes este caminho escalava direto, e isso mandava pro humano qualquer "oi"
ou pergunta de outro assunto — na primeira mensagem, sem o cliente entender
por que. Agora o agente se apresenta e da a chance de reformular.

O texto e fixo, escrito por nos. A tentacao seria pedir ao modelo que
explicasse o proprio escopo, mas sem acervo pra fundamentar ele inventa (foi
a licao da Fase 3.1) — e justamente aqui nao ha acervo nenhum.

Repare que isto NAO desliga o escalonamento: a mensagem passa pela triagem
como qualquer resposta da IA, entao conta como tentativa. Quem insiste fora
do escopo acaba no atendente humano pelo limite de sempre.

Este texto e conteudo, nao regra — descreve *esta* loja. Se o projeto
atender mais de um cliente, ele precisa virar configuracao injetada, como
os adapters ja sao.
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
"""Quantas vezes SEGUIDAS a IA pode falhar antes de chamar um humano.

Conta apenas fracassos consecutivos: uma resposta fundamentada zera a
sequencia. Tres e um meio-termo — da a IA espaco pra se corrigir depois de
um mal-entendido, sem deixar o cliente repetindo a mesma pergunta por muito
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
    2. a IA ficou `limite_tentativas` vezes SEGUIDAS sem conseguir ajudar —
       sinal de que ela nao vai chegar la sozinha.

    "Seguidas" e a palavra que importa na regra 2: uma resposta fundamentada
    zera a contagem. Sem isso, um cliente satisfeito era escalado so por ter
    feito perguntas demais.

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

        tentativas = self._tentativas_seguidas_sem_ajudar(conversa)
        if tentativas >= self.limite_tentativas:
            return ResultadoTriagem.escalar(
                f"a IA ficou {tentativas} vezes seguidas sem conseguir ajudar "
                f"(limite: {self.limite_tentativas})"
            )

        return ResultadoTriagem.resolver(resposta.texto)

    def _tentativas_seguidas_sem_ajudar(self, conversa: Conversa) -> int:
        """Quantas vezes SEGUIDAS a IA nao conseguiu ajudar, ate agora.

        A versao anterior contava todas as mensagens da IA, sucesso junto com
        fracasso. O efeito era absurdo: um cliente satisfeito que fizesse
        quatro perguntas e recebesse quatro respostas certas era transferido
        pro humano na quarta. O docstring sempre falou em "tentativas sem
        sucesso" — era a contagem que estava errada.

        O unico sinal de fracasso que existe de verdade e a resposta de fora
        do dominio: ela e emitida exatamente quando a recuperacao nao achou
        nada pra fundamentar. Resposta fundamentada zera a sequencia, porque
        significa que a IA voltou a ajudar.

        A contagem depende de reconhecer `MENSAGEM_FORA_DO_DOMINIO` pelo
        texto, e esse acoplamento e proposital e testado: as duas coisas
        moram neste modulo, e um teste quebra se elas se separarem.

        O que isto NAO cobre: uma resposta fundamentada mas errada, que o
        cliente rejeita. Nao ha sinal pra isso — ninguem pergunta ao cliente
        se ficou satisfeito. Nesse caso sobra o `deve_escalar` do modelo.
        """
        seguidas = 0
        for mensagem in reversed(conversa.mensagens):
            if mensagem.autor is not Autor.IA:
                continue
            if mensagem.conteudo != MENSAGEM_FORA_DO_DOMINIO:
                break
            seguidas += 1
        return seguidas


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

    if trechos:
        resposta_llm = provedor_llm.gerar_resposta(conversa.mensagens, trechos)
    else:
        # Sem acervo nao ha o que fundamentar, entao o modelo nem e
        # consultado — perguntar a ele sem contexto so convida a alucinacao.
        # A resposta e a apresentacao do escopo, e ela segue pela triagem
        # como qualquer outra: conta como tentativa, e insistir fora do
        # assunto acaba escalando pelo limite de sempre.
        resposta_llm = RespostaLLM(
            texto=MENSAGEM_FORA_DO_DOMINIO, deve_escalar=False
        )

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
