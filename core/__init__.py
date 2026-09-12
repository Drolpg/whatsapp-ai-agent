"""Nucleo de decisao: a logica de negocio do agente.

Aqui mora a unica pergunta que o sistema precisa responder de verdade — "a
IA resolveu esta mensagem ou a conversa precisa ir pra um humano?" — junto
dos dados necessarios pra responder isso.

E Python puro: nao importa `twilio`, `langchain`, `requests` nem qualquer
outra biblioteca que fale com o mundo externo, e nunca importa de
`adapters/`. A dependencia so aponta pra ca, nunca daqui pra fora. Se um
teste desta pasta precisar de rede, de um arquivo ou de um mock, e sinal de
que algo vazou de infraestrutura pra dentro do nucleo.

Conteudo (implementado a partir da Fase 1):
    conversa.py   Conversa e Mensagem
    triagem.py    TriagemService e processar_mensagem_recebida
    ports.py      as interfaces que os adapters implementam
"""
