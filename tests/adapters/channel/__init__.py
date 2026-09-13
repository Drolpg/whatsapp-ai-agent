"""Testes dos adapters de `Canal` — a entrada e a saida do WhatsApp.

Os dois lados sao testados de formas diferentes, por motivo:

    test_webhook.py      a entrada, com o cliente de teste do Flask e portas
                         falsas — nao toca no Twilio, entao roda sempre
    test_tac_channel.py  a saida, contra o Twilio de verdade — pulado quando
                         nao ha credenciais configuradas
"""
