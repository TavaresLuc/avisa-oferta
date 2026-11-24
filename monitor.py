"""Monitora grupos de promoção do Telegram e avisa quando aparecer algo de alertas.txt."""
import asyncio
import configparser
import hashlib
import json
import re
import sys
import time
import unicodedata
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from telethon import TelegramClient, events

for _s in (sys.stdout, sys.stderr):  # console do Windows não aguenta emoji
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

BASE = Path(__file__).resolve().parent
ALERTAS = BASE / "alertas.txt"
CONFIG = BASE / "config.ini"
DEDUP_SEGUNDOS = 30 * 60  # não repete a mesma oferta postada em vários grupos


# ---------------------------------------------------------------- texto
def normalizar(texto: str) -> str:
    texto = unicodedata.normalize("NFKD", texto.lower())
    texto = "".join(c for c in texto if not unicodedata.combining(c))
    texto = re.sub(r"[^a-z0-9]+", " ", texto)
    return f" {texto.strip()} "


PRECO_RE = re.compile(r"r\$\s*(\d{1,3}(?:\.\d{3})+|\d+)(?:,(\d{1,2}))?", re.IGNORECASE)


def extrair_precos(texto: str) -> list[float]:
    precos = []
    for inteiro, centavos in PRECO_RE.findall(texto):
        valor = float(inteiro.replace(".", ""))
        if centavos:
            valor += float(centavos) / (10 ** len(centavos))
        precos.append(valor)
    return precos


# ---------------------------------------------------------------- regras
@dataclass
class Regra:
    linha: str
    alternativas: list[list[str]]  # [[palavras que precisam aparecer juntas], ...]
    excluir: list[str] = field(default_factory=list)
    minimo: float | None = None
    maximo: float | None = None

    @property
    def nome(self) -> str:
        return " ".join(self.alternativas[0]).strip()

    def bate(self, norm: str, precos: list[float]) -> bool:
        if not any(all(p in norm for p in alt) for alt in self.alternativas):
            return False
        if any(e in norm for e in self.excluir):
            return False
        if precos and (self.minimo is not None or self.maximo is not None):
            lo = self.minimo if self.minimo is not None else 0
            hi = self.maximo if self.maximo is not None else float("inf")
            if not any(lo <= p <= hi for p in precos):
                return False
        return True


def _num(v: str) -> float:
    return float(v.strip().replace(".", "").replace(",", "."))


def carregar_regras() -> list[Regra]:
    regras = []
    for linha in ALERTAS.read_text(encoding="utf-8").splitlines():
        linha = linha.strip()
        if not linha or linha.startswith("#"):
            continue
        partes = [p.strip() for p in linha.split(";")]
        alternativas = []
        for termo in partes[0].split("|"):
            palavras = [normalizar(w) for w in termo.split("+") if normalizar(w).strip()]
            if palavras:
                alternativas.append(palavras)
        if not alternativas:
            continue
        regra = Regra(linha=linha, alternativas=alternativas)
        try:
            for p in partes[1:]:
                chave, _, valor = p.partition(":")
                chave = chave.strip().lower()
                if chave == "sem":
                    regra.excluir = [normalizar(w) for w in valor.split(",") if w.strip()]
                elif chave == "min":
                    regra.minimo = _num(valor)
                elif chave == "max":
                    regra.maximo = _num(valor)
        except ValueError:
            print(f"[!] Regra com número inválido, ignorada: {linha}")
            continue
        regras.append(regra)
    return regras


class Regras:
    """Relê alertas.txt sempre que o arquivo for salvo."""

    def __init__(self):
        self._mtime = None
        self.lista: list[Regra] = []
        self.atualizar()

    def atualizar(self):
        mtime = ALERTAS.stat().st_mtime
        if mtime != self._mtime:
            self._mtime = mtime
            self.lista = carregar_regras()
            print(f"[{agora()}] {len(self.lista)} alerta(s) ativo(s):")
            for r in self.lista:
                print(f"    • {r.linha}")


# ---------------------------------------------------------------- avisos
def agora() -> str:
    return datetime.now().strftime("%H:%M:%S")


def enviar_bot(token: str, chat_id: int, texto: str):
    dados = urllib.parse.urlencode(
        {"chat_id": chat_id, "text": texto, "disable_web_page_preview": "false"}
    ).encode()
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    with urllib.request.urlopen(url, data=dados, timeout=15) as r:
        resposta = json.loads(r.read())
    if not resposta.get("ok"):
        raise RuntimeError(resposta)


def beep():
    try:
        import winsound
        for _ in range(3):
            winsound.Beep(1500, 250)
    except Exception:
        print("\a", end="", flush=True)


def notificar_windows(titulo: str, texto: str, link: str):
    """Notificação do Windows; clicar nela abre a oferta no Telegram."""
    if sys.platform != "win32":
        return
    try:
        from winotify import Notification, audio
        n = Notification(app_id="Avisa Oferta", title=titulo, msg=texto[:250],
                         duration="long", launch=link)
        n.set_audio(audio.Reminder, loop=False)
        n.add_actions(label="Abrir oferta", launch=link)
        n.show()
    except Exception as e:
        print(f"[!] Notificação do Windows falhou: {e}")


def link_mensagem(chat, msg_id: int) -> str:
    if getattr(chat, "username", None):
        return f"https://t.me/{chat.username}/{msg_id}"
    return f"https://t.me/c/{chat.id}/{msg_id}"


# ---------------------------------------------------------------- avisos de parada
AVISO_PARADA = {"token": "", "chat": None, "enviado": False}
SAIDA_ERRO = 3  # iniciar.bat reinicia o monitor quando sai com esse código


def avisar_parada(motivo: str):
    """Manda pelo bot que o monitor parou (só uma vez)."""
    if AVISO_PARADA["enviado"] or not AVISO_PARADA["token"]:
        return
    AVISO_PARADA["enviado"] = True
    try:
        enviar_bot(
            AVISO_PARADA["token"], AVISO_PARADA["chat"],
            f"🛑 Monitor de ofertas PAROU ({agora()})\nMotivo: {motivo}\n"
            "Enquanto estiver parado você NÃO recebe alertas.",
        )
        print(f"[ok] Aviso de parada enviado: {motivo}")
    except Exception as e:
        print(f"[!] Não consegui avisar a parada: {e}")


def instalar_aviso_ao_fechar_janela():
    """No Windows, avisa quando a janela é fechada no X, logoff ou desligamento."""
    if sys.platform != "win32":
        return
    import ctypes
    from ctypes import wintypes

    motivos = {2: "janela fechada", 5: "logoff do Windows", 6: "Windows desligando"}

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.DWORD)
    def handler(evento):
        if evento in motivos:
            avisar_parada(motivos[evento])  # o Windows dá ~5s antes de matar o processo
        return False  # deixa o Python tratar o resto (Ctrl+C etc.)

    instalar_aviso_ao_fechar_janela._ref = handler  # evita o handler ser coletado
    ctypes.windll.kernel32.SetConsoleCtrlHandler(handler, True)


async def vigiar_suspensao(token: str, chat_id: int):
    """Detecta se o PC dormiu / travou e avisa quando voltar."""
    ultimo = time.time()
    while True:
        await asyncio.sleep(30)
        t = time.time()
        if t - ultimo > 120:
            de = datetime.fromtimestamp(ultimo).strftime("%H:%M")
            ate = datetime.fromtimestamp(t).strftime("%H:%M")
            msg = (f"⚠️ Fiquei fora do ar das {de} às {ate} (PC suspenso ou travado?).\n"
                   "Posso ter perdido ofertas nesse período. Já voltei a monitorar.")
            print(f"[{agora()}] {msg}")
            for _ in range(10):  # a internet pode demorar a voltar depois de acordar
                try:
                    await asyncio.to_thread(enviar_bot, token, chat_id, msg)
                    break
                except Exception:
                    await asyncio.sleep(15)
        ultimo = t


# ---------------------------------------------------------------- main
async def main():
    cfg = configparser.ConfigParser()
    cfg.read(CONFIG, encoding="utf-8")
    api_id = cfg.get("telegram", "api_id", fallback="").strip()
    api_hash = cfg.get("telegram", "api_hash", fallback="").strip()
    if not api_id or not api_hash:
        sys.exit("Preencha api_id e api_hash em config.ini (veja https://my.telegram.org).")
    bot_token = cfg.get("aviso", "bot_token", fallback="").strip()
    tocar_beep = cfg.get("aviso", "beep", fallback="sim").strip().lower() in ("sim", "s", "yes", "1")
    ids = [int(x) for x in re.split(r"[,\s]+", cfg.get("grupos", "ids", fallback="")) if x]

    regras = Regras()
    client = TelegramClient(str(BASE / "sessao"), int(api_id), api_hash)
    await client.start()  # na 1ª vez pede telefone e o código do Telegram
    eu = await client.get_me()

    await client.get_dialogs()  # carrega os grupos para poder achar pelos IDs
    grupos = []
    for gid in ids:
        try:
            ent = await client.get_entity(gid)
            grupos.append(ent)
            print(f"[ok] Monitorando: {getattr(ent, 'title', gid)}")
        except Exception as e:
            print(f"[!] Não achei o grupo {gid} (você participa dele?): {e}")
    if not grupos:
        sys.exit("Nenhum grupo encontrado.")

    if bot_token:
        try:
            enviar_bot(bot_token, eu.id, "✅ Monitor de ofertas ligado. Vou te avisar por aqui.")
            print("[ok] Avisos via bot funcionando (confira o celular).")
            AVISO_PARADA.update(token=bot_token, chat=eu.id)
            instalar_aviso_ao_fechar_janela()
            asyncio.create_task(vigiar_suspensao(bot_token, eu.id))
        except Exception as e:
            print(f"[!] Bot falhou ({e}). Você mandou /start pro seu bot? Usando Mensagens Salvas.")
            bot_token = ""

    vistos: dict[str, float] = {}

    @client.on(events.NewMessage(chats=grupos))
    async def ao_receber(event):
        texto = event.raw_text or ""
        if not texto.strip():
            return
        regras.atualizar()
        norm = normalizar(texto)
        precos = extrair_precos(texto)
        achou = [r for r in regras.lista if r.bate(norm, precos)]
        if not achou:
            return

        chave = hashlib.md5(norm.encode()).hexdigest()
        t = time.time()
        for k in [k for k, v in vistos.items() if t - v > DEDUP_SEGUNDOS]:
            del vistos[k]
        if chave in vistos:
            return
        vistos[chave] = t

        chat = await event.get_chat()
        nomes = ", ".join(r.nome.upper() for r in achou)
        link = link_mensagem(chat, event.id)
        aviso = (
            f"🚨 OFERTA: {nomes}\n"
            f"📢 {getattr(chat, 'title', '')}\n"
            f"🔗 {link}\n\n"
            f"{texto[:3500]}"
        )
        print(f"\n[{agora()}] 🚨 {nomes} em {getattr(chat, 'title', '')} -> {link}")
        print("    " + texto[:200].replace("\n", " ") + "\n")
        await asyncio.to_thread(
            notificar_windows, f"🚨 {nomes} — {getattr(chat, 'title', '')}", texto, link
        )
        if tocar_beep:
            beep()
        try:
            if bot_token:
                await asyncio.to_thread(enviar_bot, bot_token, eu.id, aviso)
            else:
                await client.send_message("me", aviso, link_preview=False)
        except Exception as e:
            print(f"[!] Falha ao enviar aviso: {e}")

    print(f"\n[{agora()}] Rodando. Deixe esta janela aberta. Ctrl+C para parar.\n")
    await client.run_until_disconnected()
    raise ConnectionError("conexão com o Telegram caiu")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        avisar_parada("encerrado por você (Ctrl+C)")
        print("\nParado.")
    except SystemExit:
        raise
    except BaseException as e:
        avisar_parada(f"erro: {e!r} — reiniciando sozinho em 10s")
        print(f"\n[!] Erro: {e!r}")
        sys.exit(SAIDA_ERRO)
