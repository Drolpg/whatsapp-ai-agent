"""Testes da camada de aplicacao — o fluxo inteiro, sem nada real.

Exercitam `ProcessarMensagemRecebida` de ponta a ponta usando
implementacoes falsas (in-memory) das quatro portas. Rodam sem Ollama, sem
Twilio e sem indice FAISS — e essa e justamente a demonstracao de que a
inversao de dependencia funcionou.

TODO(Fase 2): dubles in-memory das portas + testes dos dois caminhos do
caso de uso (resolvido pela IA e escalado pro humano).
"""
