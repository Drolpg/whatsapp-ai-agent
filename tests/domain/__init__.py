"""Testes da camada de dominio — os mais baratos da suite.

Como `domain/` e Python puro, estes testes constroem os objetos direto e
verificam comportamento: identidade de `Conversa` (Entity), igualdade por
valor de `Mensagem` (Value Object), invariantes do aggregate root e as
regras do `TriagemService`. Nenhum mock, nenhuma rede, nenhum arquivo.

TODO(Fase 1): cobrir Conversa, Mensagem, ResultadoTriagem e TriagemService.
"""
