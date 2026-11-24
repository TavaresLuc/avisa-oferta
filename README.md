# Avisa Oferta

App para Windows que vigia grupos/canais de promoção do Telegram e te avisa
(notificação do Windows, beep e mensagem no celular) quando aparece algo dos seus alertas.

## Instalação
```
pip install -r requirements.txt
python app.py
```
Na primeira execução, abra a aba **Como configurar** dentro do app. Resumo:

1. Pegue `api_id` e `api_hash` em https://my.telegram.org → *API development tools*, e cole em **Ajustes**.
2. Entre com seu número do Telegram (código + senha 2FA, se tiver).
3. (Opcional) Crie um bot no @BotFather, cole o token em **Ajustes** e mande `/start` para ele.
4. Em **Grupos**, escolha onde procurar. Em **Alertas**, crie as palavras.

Seus dados (`config.ini`, `alertas.txt`, `*.session`) ficam só na sua máquina e não vão pro git.
Em `config.example.ini` e `alertas.example.txt` há modelos.
