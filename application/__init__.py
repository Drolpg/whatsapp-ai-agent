"""Camada de aplicacao: os casos de uso do sistema.

Esta camada orquestra — ela sequencia chamadas ao dominio e as portas, mas
nao tem regra de negocio propria. Toda decisao ("responder ou escalar?")
pertence ao dominio; o caso de uso so sabe em que ordem as coisas
acontecem.

Depende de `domain/` (entidades, services e portas), nunca de
`infrastructure/`: os adapters concretos chegam prontos, injetados pelo
composition root (`main.py`). E por isso que os testes desta camada rodam
com dubles in-memory das portas, sem Ollama e sem Twilio.

Conteudo (implementado a partir da Fase 2):
    casos_de_uso.py   ProcessarMensagemRecebida
"""
