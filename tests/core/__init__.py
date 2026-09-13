"""Testes do nucleo de decisao — os mais baratos da suite.

Como `core/` e Python puro, estes testes constroem os objetos direto e
verificam comportamento: as regras do `TriagemService`, o que a `Conversa`
permite e o que ela recusa, e o fluxo de `processar_mensagem_recebida` com
implementacoes falsas (em memoria) das portas. Nenhuma rede, nenhum
arquivo, nenhum Docker.

    test_conversa.py  Mensagem, Conversa e suas transicoes de estado
    test_triagem.py   as regras de decisao do TriagemService
    test_fluxo.py     processar_mensagem_recebida ponta a ponta, com fakes
"""
