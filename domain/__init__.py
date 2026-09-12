"""Camada de dominio: a regra de negocio pura do bounded context
"Atendimento Assistido por IA".

Esta camada e Python puro — nao importa `twilio`, `langchain`, `requests`
nem qualquer outra biblioteca externa, e nunca importa de `application/` ou
`infrastructure/`. A dependencia so aponta pra dentro: infraestrutura e
aplicacao conhecem o dominio, o dominio nao conhece ninguem.

Se um teste de dominio precisar de rede, de um arquivo ou de um mock, e
sinal de que algo vazou de infraestrutura pra ca.

Conteudo (implementado a partir da Fase 1):
    entidades.py      Conversa (Entity / aggregate root)
    value_objects.py  Mensagem, ResultadoTriagem, Trecho
    services.py       TriagemService (Domain Service)
    ports.py          as portas que a infraestrutura implementa
"""
