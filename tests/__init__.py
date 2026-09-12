"""Suite de testes, espelhando as camadas da aplicacao.

A divisao nao e so organizacional — ela torna visivel o custo de cada
camada. Quanto mais pra dentro, mais barato e mais rapido o teste:

    tests/domain/          regra pura: sem I/O, sem mock, sem framework
    tests/application/     casos de uso com dubles in-memory das portas
    tests/infrastructure/  adapters contra as tecnologias reais

Se um teste em `tests/domain/` um dia precisar de rede ou de arquivo, o
problema esta no codigo de producao, nao no teste.
"""
