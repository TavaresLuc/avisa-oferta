"""Avisa Oferta — interface (PySide6) com notch flutuante."""
import os
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent
if sys.stdout is None or sys.stderr is None:  # rodando com pythonw (sem console)
    _log = open(BASE / "app.log", "a", encoding="utf-8", buffering=1)
    sys.stdout = sys.stderr = _log

import asyncio
import hashlib
import math
import re
import sqlite3
import time
from datetime import datetime

from PySide6.QtCore import (QEasingCurve, QPoint, QPropertyAnimation, QRect, QRectF, QSize,
                            Qt, QThread, QTimer, QUrl, Property, Signal)
from PySide6.QtGui import (QAction, QColor, QDesktopServices, QFont, QFontMetrics, QGuiApplication,
                           QIcon, QLinearGradient, QPainter, QPainterPath, QPen, QPixmap)
from PySide6.QtNetwork import QLocalServer, QLocalSocket
from PySide6.QtWidgets import (QAbstractButton, QApplication, QFrame, QHBoxLayout, QLabel,
                               QLayout, QLineEdit, QMenu, QPushButton, QScrollArea, QSizeGrip,
                               QSizePolicy, QStackedWidget, QSystemTrayIcon, QVBoxLayout, QWidget,
                               QWidgetItem)

import core
import monitor as m

# ======================================================================= tema
C = {
    "bg": "#1C1C1E", "side": "#232326", "card": "#2A2A2D", "card2": "#323236",
    "line": "#3A3A3C", "txt": "#F5F5F7", "sub": "#9A9AA0", "dim": "#6E6E73",
    "blue": "#0A84FF", "green": "#30D158", "red": "#FF453A", "orange": "#FF9F0A",
    "yellow": "#FFD60A", "purple": "#BF5AF2",
}
ESTADO_COR = {"running": C["green"], "connecting": C["orange"], "login": C["blue"],
              "error": C["red"], "stopped": C["red"]}

QSS = f"""
* {{ color: {C['txt']}; font-size: 13px; outline: none; }}
QLabel {{ background: transparent; }}
QLabel#H1 {{ font-size: 26px; font-weight: 700; }}
QLabel#H2 {{ font-size: 15px; font-weight: 600; }}
QLabel#Sub {{ color: {C['sub']}; }}
QLabel#Dim {{ color: {C['dim']}; font-size: 12px; }}
QLabel#Big {{ font-size: 24px; font-weight: 700; }}
QLabel#Section {{ color: {C['sub']}; font-size: 11px; font-weight: 600; letter-spacing: 0.6px; }}
QFrame#Card {{ background: {C['card']}; border: 1px solid rgba(255,255,255,0.05); border-radius: 14px; }}
QFrame#Card:hover[clickable="true"] {{ background: {C['card2']}; }}
QFrame#SheetCard {{ background: #2C2C2F; border: 1px solid rgba(255,255,255,0.09); border-radius: 18px; }}
QFrame#Sep {{ background: rgba(255,255,255,0.06); max-height: 1px; min-height: 1px; border: none; }}
QFrame#Chip {{ background: rgba(10,132,255,0.18); border-radius: 11px; }}
QFrame#ChipRed {{ background: rgba(255,69,58,0.16); border-radius: 11px; }}
QFrame#ChipBox {{ background: #1F1F22; border: 1px solid {C['line']}; border-radius: 10px; }}
QLineEdit {{ background: #1F1F22; border: 1px solid {C['line']}; border-radius: 10px;
             padding: 8px 11px; selection-background-color: {C['blue']}; }}
QLineEdit:focus {{ border: 1px solid {C['blue']}; }}
QLineEdit#Bare {{ background: transparent; border: none; padding: 4px 2px; }}
QPushButton {{ border: none; border-radius: 9px; padding: 8px 16px; font-weight: 600;
               background: #3A3A3D; }}
QPushButton:hover {{ background: #46464A; }}
QPushButton#Primary {{ background: {C['blue']}; }}
QPushButton#Primary:hover {{ background: #2B95FF; }}
QPushButton#Primary:disabled {{ background: #2A3F57; color: #7E8FA3; }}
QPushButton#Danger {{ background: transparent; color: {C['red']}; padding: 8px 6px; }}
QPushButton#Danger:hover {{ background: rgba(255,69,58,0.12); }}
QPushButton#Ghost {{ background: transparent; color: {C['blue']}; padding: 6px 8px; }}
QPushButton#Ghost:hover {{ background: rgba(10,132,255,0.12); }}
QPushButton#Nav {{ text-align: left; padding: 8px 12px; border-radius: 8px; background: transparent;
                   color: #D6D6DB; font-weight: 500; }}
QPushButton#Nav:hover {{ background: rgba(255,255,255,0.05); }}
QPushButton#Nav:checked {{ background: rgba(255,255,255,0.11); color: white; }}
QPushButton#X {{ background: transparent; color: {C['sub']}; padding: 0; font-size: 14px; }}
QPushButton#X:hover {{ color: white; }}
QScrollArea, QScrollArea > QWidget > QWidget {{ background: transparent; border: none; }}
QScrollBar:vertical {{ width: 10px; background: transparent; margin: 2px; }}
QScrollBar::handle:vertical {{ background: rgba(255,255,255,0.16); border-radius: 3px; min-height: 30px; }}
QScrollBar::handle:vertical:hover {{ background: rgba(255,255,255,0.28); }}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: none; }}
QMenu {{ background: #2C2C2F; border: 1px solid rgba(255,255,255,0.1); border-radius: 10px; padding: 5px; }}
QMenu::item {{ padding: 6px 22px 6px 12px; border-radius: 6px; }}
QMenu::item:selected {{ background: {C['blue']}; }}
QMenu::separator {{ height: 1px; background: rgba(255,255,255,0.1); margin: 4px 6px; }}
QToolTip {{ background: #2C2C2F; color: white; border: 1px solid #444; border-radius: 6px; padding: 4px 8px; }}
"""


def fonte(tam=13, peso=QFont.Weight.Normal) -> QFont:
    f = QFont()
    f.setFamilies(["Segoe UI Variable Text", "Segoe UI", "Arial"])
    f.setPointSizeF(tam * 0.75)
    f.setWeight(peso)
    return f


def criar_icone(tam=256) -> QIcon:
    pm = QPixmap(tam, tam)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    g = QLinearGradient(0, 0, tam, tam)
    g.setColorAt(0, QColor("#FF9F0A"))
    g.setColorAt(1, QColor("#FF375F"))
    p.setBrush(g)
    p.setPen(Qt.NoPen)
    p.drawRoundedRect(QRectF(tam * .06, tam * .06, tam * .88, tam * .88), tam * .22, tam * .22)
    p.setPen(QColor("white"))
    f = QFont("Segoe UI", -1, QFont.Weight.Black)
    f.setPixelSize(int(tam * .56))
    p.setFont(f)
    p.drawText(QRectF(0, -tam * .02, tam, tam), Qt.AlignCenter, "%")
    p.end()
    return QIcon(pm)


def tempo_relativo(ts: float) -> str:
    d = time.time() - ts
    if d < 60:
        return "agora"
    if d < 3600:
        return f"há {int(d // 60)} min"
    if datetime.fromtimestamp(ts).date() == datetime.now().date():
        return datetime.fromtimestamp(ts).strftime("%H:%M")
    return datetime.fromtimestamp(ts).strftime("%d/%m %H:%M")


# ======================================================================= worker
class Worker(QThread):
    status = Signal(str, str)        # estado, detalhe
    oferta = Signal(object)
    grupos_info = Signal(object)     # {id: titulo}
    dialogos = Signal(object)        # [(id, titulo, tipo)]
    resolvido = Signal(object)       # (id, titulo) ou str de erro
    pedir = Signal(str, str)         # phone/code/password, erro
    conta = Signal(str)
    lidas = Signal(int)

    def __init__(self, cfg: dict):
        super().__init__()
        self.cfg = cfg
        self.ids = set(cfg["grupos"])
        self.loop = None
        self.client = None
        self.me = None
        self._fut = None
        self._parar = False
        self.n_lidas = 0
        self.vistos = {}
        self.regras = None
        self._vigia = False

    # ---- chamadas vindas da interface (thread-safe)
    def _call(self, coro_or_fn, *a):
        if not self.loop:
            return
        if asyncio.iscoroutinefunction(coro_or_fn):
            asyncio.run_coroutine_threadsafe(coro_or_fn(*a), self.loop)
        else:
            self.loop.call_soon_threadsafe(coro_or_fn, *a)

    def responder(self, valor: str):
        def _set():
            if self._fut and not self._fut.done():
                self._fut.set_result(valor)
        self._call(_set)

    def set_grupos(self, ids):
        self.ids = set(ids)
        self._call(self._info_grupos)

    def pedir_dialogos(self):
        self._call(self._listar_dialogos)

    def resolver(self, texto: str):
        self._call(self._resolver, texto)

    def parar(self):
        self._parar = True
        if self.loop and self.client:
            self._call(self.client.disconnect)

    # ---- loop principal
    def run(self):
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        self.loop.run_until_complete(self._principal())

    async def _principal(self):
        espera = 5
        while not self._parar:
            try:
                await self._sessao()
                espera = 5
            except sqlite3.OperationalError as e:
                self.status.emit("error", "Sessão em uso — feche o iniciar.bat / monitor.py"
                                 if "locked" in str(e) else f"Erro: {e}")
            except Exception as e:
                self.status.emit("error", f"{type(e).__name__}: {e}"[:140])
            if self._parar:
                break
            for _ in range(espera):
                if self._parar:
                    break
                await asyncio.sleep(1)
            espera = min(espera * 2, 60)
        self.status.emit("stopped", "Parado")

    async def _ask(self, tipo, erro=""):
        self._fut = self.loop.create_future()
        self.pedir.emit(tipo, erro)
        return (await self._fut).strip()

    async def _login(self, client):
        from telethon.errors import (PhoneCodeInvalidError, SessionPasswordNeededError,
                                     PasswordHashInvalidError, PhoneNumberInvalidError)
        self.status.emit("login", "Entre na sua conta do Telegram")
        erro = ""
        while True:
            phone = await self._ask("phone", erro)
            try:
                await client.send_code_request(phone)
                break
            except PhoneNumberInvalidError:
                erro = "Número inválido. Use +55 DDD número."
        erro = ""
        while True:
            code = await self._ask("code", erro)
            try:
                await client.sign_in(phone, code)
                return
            except PhoneCodeInvalidError:
                erro = "Código incorreto, tente de novo."
            except SessionPasswordNeededError:
                break
        erro = ""
        while True:
            pw = await self._ask("password", erro)
            try:
                await client.sign_in(password=pw)
                return
            except PasswordHashInvalidError:
                erro = "Senha incorreta."

    async def _sessao(self):
        from telethon import TelegramClient, events
        if not self.cfg["api_id"] or not self.cfg["api_hash"]:
            self.status.emit("error", "Preencha api_id e api_hash em Ajustes")
            while not (self.cfg["api_id"] and self.cfg["api_hash"]) and not self._parar:
                await asyncio.sleep(2)
            return
        self.status.emit("connecting", "Conectando ao Telegram…")
        self.regras = m.Regras()
        client = TelegramClient(str(BASE / "sessao"), int(self.cfg["api_id"]), self.cfg["api_hash"])
        self.client = client
        try:
            await client.connect()
            if not await client.is_user_authorized():
                await self._login(client)
            self.me = await client.get_me()
            nome = " ".join(x for x in [self.me.first_name, self.me.last_name] if x)
            self.conta.emit(f"{nome}  ·  +{self.me.phone}" if self.me.phone else nome)
            await client.get_dialogs()
            await self._info_grupos()

            if self.cfg["bot_token"]:
                m.AVISO_PARADA.update(token=self.cfg["bot_token"], chat=self.me.id, enviado=False)
                if not self._vigia:
                    self._vigia = True
                    asyncio.create_task(m.vigiar_suspensao(self.cfg["bot_token"], self.me.id))

            client.add_event_handler(self._ao_receber, events.NewMessage())
            self.status.emit("running", "")
            await client.run_until_disconnected()
        finally:
            self.client = None
            await client.disconnect()
        if not self._parar:
            raise ConnectionError("Conexão caiu, reconectando…")

    async def _info_grupos(self):
        if not self.client:
            return
        info = {}
        for gid in list(self.ids):
            try:
                ent = await self.client.get_entity(gid)
                info[gid] = getattr(ent, "title", str(gid))
            except Exception:
                info[gid] = None
        self.grupos_info.emit(info)

    async def _listar_dialogos(self):
        if not self.client:
            self.dialogos.emit([])
            return
        lst = []
        async for d in self.client.iter_dialogs():
            if d.is_group or d.is_channel:
                lst.append((d.id, d.name, "Canal" if d.is_channel and not d.is_group else "Grupo"))
        self.dialogos.emit(lst)

    async def _resolver(self, texto: str):
        t = texto.strip()
        mt = re.search(r"-100\d{6,}", t) or re.search(r"(?<![\d])-?\d{7,}", t)
        alvo = int(mt.group()) if mt else re.sub(r"^(https?://)?(t\.me/|telegram\.me/)|^@", "", t)
        try:
            if not self.client:
                raise RuntimeError("não conectado")
            from telethon import utils
            ent = await self.client.get_entity(alvo)
            self.resolvido.emit((utils.get_peer_id(ent), getattr(ent, "title", None) or str(alvo)))
        except Exception as e:
            self.resolvido.emit(f"Não encontrei esse grupo ({e.__class__.__name__}). Você participa dele?")

    async def _ao_receber(self, event):
        if event.chat_id not in self.ids:
            return
        texto = event.raw_text or ""
        if not texto.strip():
            return
        self.n_lidas += 1
        self.lidas.emit(self.n_lidas)
        self.regras.atualizar()
        norm = m.normalizar(texto)
        precos = m.extrair_precos(texto)
        achou = [r for r in self.regras.lista if r.bate(norm, precos)]
        if not achou:
            return
        chave = hashlib.md5(norm.encode()).hexdigest()
        t = time.time()
        for k in [k for k, v in self.vistos.items() if t - v > m.DEDUP_SEGUNDOS]:
            del self.vistos[k]
        if chave in self.vistos:
            return
        self.vistos[chave] = t

        chat = await event.get_chat()
        titulo = getattr(chat, "title", "")
        nomes = ", ".join(r.nome.upper() if len(r.nome) <= 5 else r.nome.title() for r in achou)
        link = m.link_mensagem(chat, event.id)
        faixa = [p for p in precos for r in achou
                 if (r.minimo or 0) <= p <= (r.maximo if r.maximo is not None else 1e12)]
        preco = min(faixa) if faixa else None
        self.oferta.emit({"ts": t, "produto": nomes, "grupo": titulo, "link": link,
                          "texto": texto[:2000], "preco": preco})

        if self.cfg["toast"]:
            await asyncio.to_thread(m.notificar_windows, f"🚨 {nomes} — {titulo}", texto, link)
        if self.cfg["beep"]:
            await asyncio.to_thread(m.beep)
        aviso = f"🚨 OFERTA: {nomes}\n📢 {titulo}\n🔗 {link}\n\n{texto[:3500]}"
        try:
            if self.cfg["bot_token"]:
                await asyncio.to_thread(m.enviar_bot, self.cfg["bot_token"], self.me.id, aviso)
            else:
                await self.client.send_message("me", aviso, link_preview=False)
        except Exception as e:
            print(f"[!] Falha ao enviar aviso: {e}")


# ======================================================================= widgets base
class Toggle(QAbstractButton):
    def __init__(self, checked=False, parent=None):
        super().__init__(parent)
        self.setCheckable(True)
        self.setChecked(checked)
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedSize(44, 26)
        self._p = 1.0 if checked else 0.0
        self._anim = QPropertyAnimation(self, b"pos_", self)
        self._anim.setDuration(180)
        self._anim.setEasingCurve(QEasingCurve.OutCubic)
        self.toggled.connect(self._animar)

    def _animar(self, on):
        self._anim.stop()
        self._anim.setEndValue(1.0 if on else 0.0)
        self._anim.start()

    def _get(self):
        return self._p

    def _set(self, v):
        self._p = v
        self.update()

    pos_ = Property(float, _get, _set)

    def setChecked(self, v):
        super().setChecked(v)
        self._p = 1.0 if v else 0.0
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        off, on = QColor("#48484C"), QColor(C["green"])
        c = QColor(int(off.red() + (on.red() - off.red()) * self._p),
                   int(off.green() + (on.green() - off.green()) * self._p),
                   int(off.blue() + (on.blue() - off.blue()) * self._p))
        p.setPen(Qt.NoPen)
        p.setBrush(c)
        p.drawRoundedRect(QRectF(0, 0, 44, 26), 13, 13)
        p.setBrush(QColor(0, 0, 0, 40))
        x = 2 + self._p * 18
        p.drawEllipse(QRectF(x, 3, 22, 22))
        p.setBrush(QColor("white"))
        p.drawEllipse(QRectF(x, 2, 22, 22))


class Pulso(QWidget):
    """Bolinha de status com halo pulsando."""
    def __init__(self, tam=12, parent=None):
        super().__init__(parent)
        self.tam = tam
        self.cor = QColor(C["orange"])
        self.setFixedSize(tam * 3, tam * 3)
        self._t = 0.0
        self._timer = QTimer(self, interval=40, timeout=self._tick)
        self._timer.start()

    def set_cor(self, cor):
        self.cor = QColor(cor)
        self.update()

    def _tick(self):
        self._t = (self._t + 0.04) % 1.0
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        c = self.rect().center()
        r = self.tam / 2
        halo = QColor(self.cor)
        halo.setAlphaF(0.45 * (1 - self._t))
        p.setPen(Qt.NoPen)
        p.setBrush(halo)
        rr = r + r * 1.6 * self._t
        p.drawEllipse(QRectF(c.x() - rr + .5, c.y() - rr + .5, rr * 2, rr * 2))
        p.setBrush(self.cor)
        p.drawEllipse(QRectF(c.x() - r + .5, c.y() - r + .5, r * 2, r * 2))


class FlowLayout(QLayout):
    def __init__(self, parent=None, esp=6):
        super().__init__(parent)
        self._itens = []
        self._esp = esp
        self.setContentsMargins(0, 0, 0, 0)

    def addItem(self, item):
        self._itens.append(item)

    def insertWidget(self, i, w):
        self.addChildWidget(w)
        self._itens.insert(i, QWidgetItem(w))
        self.invalidate()

    def count(self):
        return len(self._itens)

    def itemAt(self, i):
        return self._itens[i] if 0 <= i < len(self._itens) else None

    def takeAt(self, i):
        return self._itens.pop(i) if 0 <= i < len(self._itens) else None

    def expandingDirections(self):
        return Qt.Orientation(0)

    def hasHeightForWidth(self):
        return True

    def heightForWidth(self, w):
        return self._fazer(QRect(0, 0, w, 0), True)

    def setGeometry(self, r):
        super().setGeometry(r)
        self._fazer(r, False)

    def sizeHint(self):
        return self.minimumSize()

    def minimumSize(self):
        s = QSize()
        for it in self._itens:
            s = s.expandedTo(it.minimumSize())
        mg = self.contentsMargins()
        return s + QSize(mg.left() + mg.right(), mg.top() + mg.bottom())

    def _fazer(self, rect, teste):
        mg = self.contentsMargins()
        r = rect.adjusted(mg.left(), mg.top(), -mg.right(), -mg.bottom())
        x, y, lh = r.x(), r.y(), 0
        for it in self._itens:
            sh = it.sizeHint()
            edit = it.widget() is not None and isinstance(it.widget(), QLineEdit)
            if edit:  # o campo de texto ocupa o resto da linha
                if r.right() - x + 1 < 120 and lh > 0:
                    x, y, lh = r.x(), y + lh + self._esp, 0
                sh = QSize(max(120, r.right() - x + 1), sh.height())
            elif x + sh.width() - 1 > r.right() and x > r.x():
                x, y, lh = r.x(), y + lh + self._esp, 0
            if not teste:
                it.setGeometry(QRect(QPoint(x, y), sh))
            x, lh = x + sh.width() + self._esp, max(lh, sh.height())
        return y + lh - r.y() + mg.top() + mg.bottom()


class Chip(QFrame):
    remover = Signal(object)

    def __init__(self, texto, vermelho=False):
        super().__init__()
        self.texto = texto
        self.setObjectName("ChipRed" if vermelho else "Chip")
        h = QHBoxLayout(self)
        h.setContentsMargins(10, 3, 5, 3)
        h.setSpacing(4)
        lb = QLabel(texto)
        lb.setStyleSheet(f"color: {'#FF8A80' if vermelho else '#8EC5FF'}; font-weight: 500;")
        x = QPushButton("✕")
        x.setObjectName("X")
        x.setFixedSize(16, 16)
        x.setStyleSheet("font-size: 10px;")
        x.setCursor(Qt.PointingHandCursor)
        x.clicked.connect(lambda: self.remover.emit(self))
        h.addWidget(lb)
        h.addWidget(x)


class ChipInput(QFrame):
    """Campo de 'etiquetas': digite e aperte Enter."""
    def __init__(self, placeholder, vermelho=False):
        super().__init__()
        self.setObjectName("ChipBox")
        self.vermelho = vermelho
        self.flow = FlowLayout(self)
        self.flow.setContentsMargins(8, 7, 8, 7)
        self.edit = QLineEdit()
        self.edit.setObjectName("Bare")
        self.edit.setPlaceholderText(placeholder)
        self.edit.returnPressed.connect(self._add_texto)
        self.edit.textEdited.connect(self._virgula)
        self.edit.installEventFilter(self)
        self.flow.addWidget(self.edit)
        self.chips = []

    def eventFilter(self, obj, ev):
        if ev.type() == ev.Type.KeyPress and ev.key() == Qt.Key_Backspace \
                and not self.edit.text() and self.chips:
            self._rem(self.chips[-1])
            return True
        if ev.type() == ev.Type.FocusOut:
            self._add_texto()
        return False

    def _virgula(self, t):
        if "," in t:
            for parte in t.split(","):
                self.add(parte)
            self.edit.clear()

    def _add_texto(self):
        self.add(self.edit.text())
        self.edit.clear()

    def add(self, texto):
        texto = texto.strip()
        if not texto or texto.lower() in [c.texto.lower() for c in self.chips]:
            return
        c = Chip(texto, self.vermelho)
        c.remover.connect(self._rem)
        self.chips.append(c)
        self.flow.insertWidget(len(self.chips) - 1, c)
        self.updateGeometry()

    def _rem(self, c):
        self.chips.remove(c)
        self.flow.removeWidget(c)
        c.deleteLater()
        self.updateGeometry()

    def valores(self):
        self._add_texto()
        return [c.texto for c in self.chips]


def card(clicavel=False) -> QFrame:
    f = QFrame()
    f.setObjectName("Card")
    if clicavel:
        f.setProperty("clickable", True)
        f.setCursor(Qt.PointingHandCursor)
    return f


def label(texto, nome=None, wrap=False) -> QLabel:
    lb = QLabel(texto)
    if nome:
        lb.setObjectName(nome)
    lb.setWordWrap(wrap)
    return lb


def botao(texto, nome=None, cb=None) -> QPushButton:
    b = QPushButton(texto)
    if nome:
        b.setObjectName(nome)
    b.setCursor(Qt.PointingHandCursor)
    if cb:
        b.clicked.connect(cb)
    return b


def limpar(layout):
    while layout.count():
        it = layout.takeAt(0)
        if it.widget():
            it.widget().deleteLater()


def scroll_de(widget) -> QScrollArea:
    sa = QScrollArea()
    sa.setWidgetResizable(True)
    sa.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
    sa.setWidget(widget)
    return sa


class Semaforo(QWidget):
    """Botões fechar/minimizar/maximizar estilo macOS."""
    fechar = Signal()
    minimizar = Signal()
    maximizar = Signal()

    def __init__(self):
        super().__init__()
        self.setFixedSize(60, 14)
        self.setMouseTracking(True)
        self._hover = False
        self.setCursor(Qt.ArrowCursor)

    def enterEvent(self, _):
        self._hover = True
        self.update()

    def leaveEvent(self, _):
        self._hover = False
        self.update()

    def mousePressEvent(self, e):
        i = int(e.position().x() // 20)
        [self.fechar, self.minimizar, self.maximizar][min(i, 2)].emit()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        cores = ["#FF5F57", "#FEBC2E", "#28C840"]
        for i, c in enumerate(cores):
            x = i * 20 + 1
            p.setPen(QPen(QColor(0, 0, 0, 50), 0.6))
            p.setBrush(QColor(c))
            p.drawEllipse(QRectF(x, 1, 12, 12))
            if self._hover:
                p.setPen(QPen(QColor(0, 0, 0, 150), 1.3))
                cx, cy = x + 6, 7
                if i == 0:
                    p.drawLine(QPoint(cx - 3, cy - 3), QPoint(cx + 3, cy + 3))
                    p.drawLine(QPoint(cx - 3, cy + 3), QPoint(cx + 3, cy - 3))
                elif i == 1:
                    p.drawLine(QPoint(cx - 3, cy), QPoint(cx + 3, cy))
                else:
                    p.drawLine(QPoint(cx - 3, cy), QPoint(cx + 3, cy))
                    p.drawLine(QPoint(cx, cy - 3), QPoint(cx, cy + 3))


# ======================================================================= sheet (modal)
class Sheet(QWidget):
    """Painel modal sobre a janela, com fundo escurecido."""
    def __init__(self, parent, conteudo: QWidget, largura=460):
        super().__init__(parent)
        self._geo()
        lay = QVBoxLayout(self)
        lay.setAlignment(Qt.AlignCenter)
        self.cartao = QFrame()
        self.cartao.setObjectName("SheetCard")
        self.cartao.setFixedWidth(largura)
        cl = QVBoxLayout(self.cartao)
        cl.setContentsMargins(24, 22, 24, 20)
        cl.addWidget(conteudo)
        lay.addWidget(self.cartao)
        parent.installEventFilter(self)
        self.show()
        self.raise_()

    def eventFilter(self, obj, ev):
        if obj is self.parent() and ev.type() in (ev.Type.Resize, ev.Type.LayoutRequest):
            self._geo()
        return False

    def _geo(self):
        mg = self.parent().layout().contentsMargins().left()
        self.raio = 14 if mg else 0
        self.setGeometry(self.parent().rect().adjusted(mg, mg, -mg, -mg))

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(0, 0, 0, 125))
        p.drawRoundedRect(QRectF(self.rect()), self.raio, self.raio)

    def fechar(self):
        self.parent().removeEventFilter(self)
        self.deleteLater()


# ======================================================================= páginas
class Pagina(QWidget):
    def __init__(self, titulo, sub=""):
        super().__init__()
        self.lay = QVBoxLayout(self)
        self.lay.setContentsMargins(34, 22, 34, 24)
        self.lay.setSpacing(16)
        topo = QHBoxLayout()
        tl = QVBoxLayout()
        tl.setSpacing(2)
        tl.addWidget(label(titulo, "H1"))
        self.sub = label(sub, "Sub")
        tl.addWidget(self.sub)
        topo.addLayout(tl)
        topo.addStretch()
        self.acoes = QHBoxLayout()
        topo.addLayout(self.acoes)
        self.lay.addLayout(topo)


class PaginaVisao(Pagina):
    def __init__(self, win):
        super().__init__("Visão geral", "O que está acontecendo agora")
        self.win = win
        hero = card()
        hl = QHBoxLayout(hero)
        hl.setContentsMargins(18, 16, 22, 16)
        self.pulso = Pulso(14)
        hl.addWidget(self.pulso)
        tx = QVBoxLayout()
        tx.setSpacing(2)
        self.st_titulo = label("Conectando…", "H2")
        self.st_titulo.setStyleSheet("font-size: 18px; font-weight: 700;")
        self.st_det = label("", "Sub")
        tx.addWidget(self.st_titulo)
        tx.addWidget(self.st_det)
        hl.addLayout(tx, 1)
        self.lay.addWidget(hero)

        stats = QHBoxLayout()
        stats.setSpacing(12)
        self.n_lidas = self._stat(stats, "MENSAGENS LIDAS", "0")
        self.n_ofertas = self._stat(stats, "OFERTAS HOJE", "0")
        self.desde = self._stat(stats, "LIGADO DESDE", datetime.now().strftime("%H:%M"))
        self.lay.addLayout(stats)

        cab = QHBoxLayout()
        cab.addWidget(label("Ofertas encontradas", "H2"))
        cab.addStretch()
        cab.addWidget(botao("Limpar", "Ghost", self._limpar))
        self.lay.addLayout(cab)

        self.feed_w = QWidget()
        self.feed = QVBoxLayout(self.feed_w)
        self.feed.setContentsMargins(0, 0, 4, 0)
        self.feed.setSpacing(10)
        self.feed.setAlignment(Qt.AlignTop)
        self.lay.addWidget(scroll_de(self.feed_w), 1)
        self.atualizar_feed()
        QTimer(self, interval=30000, timeout=self.atualizar_feed).start()

    def _stat(self, lay, titulo, valor):
        c = card()
        v = QVBoxLayout(c)
        v.setContentsMargins(16, 12, 16, 12)
        v.setSpacing(2)
        v.addWidget(label(titulo, "Section"))
        val = label(valor, "Big")
        v.addWidget(val)
        lay.addWidget(c)
        return val

    def _limpar(self):
        self.win.historico.clear()
        core.salvar_historico([])
        self.atualizar_feed()
        self.win.atualizar_resumo()

    def atualizar_feed(self):
        limpar(self.feed)
        hist = self.win.historico
        hoje = datetime.now().date()
        self.n_ofertas.setText(str(sum(1 for o in hist if datetime.fromtimestamp(o["ts"]).date() == hoje)))
        if not hist:
            vazio = card()
            vl = QVBoxLayout(vazio)
            vl.setContentsMargins(20, 34, 20, 34)
            t = label("🛍️", None)
            t.setAlignment(Qt.AlignCenter)
            t.setStyleSheet("font-size: 30px;")
            vl.addWidget(t)
            a = label("Nenhuma oferta ainda", "H2")
            a.setAlignment(Qt.AlignCenter)
            vl.addWidget(a)
            b = label("Assim que aparecer algo dos seus alertas, surge aqui —\n"
                      "e você recebe aviso no celular e no Windows.", "Sub")
            b.setAlignment(Qt.AlignCenter)
            vl.addWidget(b)
            self.feed.addWidget(vazio)
            return
        for o in hist[:60]:
            self.feed.addWidget(self._card_oferta(o))

    def _card_oferta(self, o):
        c = card()
        v = QVBoxLayout(c)
        v.setContentsMargins(16, 13, 16, 13)
        v.setSpacing(6)
        top = QHBoxLayout()
        tag = QLabel(o["produto"])
        tag.setStyleSheet(f"background: rgba(255,159,10,0.18); color: {C['orange']}; font-weight: 700;"
                          "font-size: 11px; padding: 3px 9px; border-radius: 9px;")
        top.addWidget(tag)
        if o.get("preco"):
            pr = QLabel(f"R$ {core.fmt_preco(o['preco'])}")
            pr.setStyleSheet(f"color: {C['green']}; font-weight: 700; font-size: 14px;")
            top.addWidget(pr)
        top.addStretch()
        top.addWidget(label(f"{o['grupo']}  ·  {tempo_relativo(o['ts'])}", "Dim"))
        v.addLayout(top)
        linhas = [l for l in o["texto"].splitlines() if l.strip()][:3]
        corpo = label("\n".join(linhas), wrap=True)
        corpo.setStyleSheet(f"color: #D8D8DC;")
        corpo.setTextInteractionFlags(Qt.TextSelectableByMouse)
        v.addWidget(corpo)
        bl = QHBoxLayout()
        bl.addStretch()
        bl.addWidget(botao("Abrir no Telegram ↗", "Ghost",
                           lambda: QDesktopServices.openUrl(QUrl(o["link"]))))
        v.addLayout(bl)
        return c

    def set_status(self, estado, titulo, detalhe):
        self.pulso.set_cor(ESTADO_COR.get(estado, C["orange"]))
        self.st_titulo.setText(titulo)
        self.st_det.setText(detalhe)


class PaginaAlertas(Pagina):
    def __init__(self, win):
        super().__init__("Alertas", "Palavras que você quer ser avisado")
        self.win = win
        self.acoes.addWidget(botao("＋  Novo alerta", "Primary", lambda: self.editar(None)))
        self.lista_w = QWidget()
        self.lista = QVBoxLayout(self.lista_w)
        self.lista.setContentsMargins(0, 0, 4, 0)
        self.lista.setSpacing(10)
        self.lista.setAlignment(Qt.AlignTop)
        self.lay.addWidget(scroll_de(self.lista_w), 1)
        dica = label("Dica: o preço mínimo ajuda a ignorar acessórios e jogos. "
                     "Mensagens sem preço sempre avisam, pra você não perder nada.", "Dim", wrap=True)
        self.lay.addWidget(dica)
        self.recarregar()

    def recarregar(self):
        self.regras = core.ler_regras()
        limpar(self.lista)
        for i, r in enumerate(self.regras):
            self.lista.addWidget(self._card(i, r))
        if not self.regras:
            self.lista.addWidget(label("Nenhum alerta. Clique em “Novo alerta”.", "Sub"))
        self.win.atualizar_resumo()

    def _card(self, i, r: core.RegraRaw):
        c = card(True)
        h = QHBoxLayout(c)
        h.setContentsMargins(18, 14, 16, 14)
        h.setSpacing(14)
        v = QVBoxLayout()
        v.setSpacing(6)
        t = label(r.titulo, "H2")
        if not r.ativo:
            t.setStyleSheet(f"color: {C['dim']};")
        v.addWidget(t)
        chips = QWidget()
        fl = FlowLayout(chips, 5)
        for termo in r.termos:
            ch = QLabel(termo)
            ch.setStyleSheet("background: rgba(10,132,255,0.16); color: #8EC5FF; padding: 2px 9px;"
                             "border-radius: 9px; font-size: 12px;")
            fl.addWidget(ch)
        for ex in r.excluir:
            ch = QLabel(f"sem {ex}")
            ch.setStyleSheet("background: rgba(255,69,58,0.13); color: #FF8A80; padding: 2px 9px;"
                             "border-radius: 9px; font-size: 12px;")
            fl.addWidget(ch)
        v.addWidget(chips)
        if r.minimo is not None or r.maximo is not None:
            if r.minimo is not None and r.maximo is not None:
                fx = f"R$ {core.fmt_preco(r.minimo)} – R$ {core.fmt_preco(r.maximo)}"
            elif r.maximo is not None:
                fx = f"até R$ {core.fmt_preco(r.maximo)}"
            else:
                fx = f"a partir de R$ {core.fmt_preco(r.minimo)}"
            v.addWidget(label(f"💰  {fx}", "Sub"))
        h.addLayout(v, 1)
        tg = Toggle(r.ativo)
        tg.toggled.connect(lambda on, i=i: self._ativar(i, on))
        h.addWidget(tg, 0, Qt.AlignTop)
        c.mousePressEvent = lambda e, i=i: self.editar(i)
        return c

    def _ativar(self, i, on):
        self.regras[i].ativo = on
        core.salvar_regras(self.regras)
        QTimer.singleShot(200, self.recarregar)

    def editar(self, i):
        r = self.regras[i] if i is not None else core.RegraRaw(termos=[])
        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(8)
        v.addWidget(label("Editar alerta" if i is not None else "Novo alerta", "H1"))
        v.addSpacing(6)
        v.addWidget(label("PALAVRAS QUE DISPARAM", "Section"))
        termos = ChipInput("Digite e aperte Enter… ex: ps5")
        for t in r.termos:
            termos.add(t)
        v.addWidget(termos)
        v.addWidget(label("Basta uma aparecer. Use + para exigir juntas: air fryer + mondial", "Dim", True))
        v.addSpacing(6)
        v.addWidget(label("IGNORAR SE TIVER", "Section"))
        excl = ChipInput("ex: capa, película…", vermelho=True)
        for t in r.excluir:
            excl.add(t)
        v.addWidget(excl)
        v.addSpacing(6)
        v.addWidget(label("FAIXA DE PREÇO (R$)", "Section"))
        ph = QHBoxLayout()
        emin, emax = QLineEdit(core.fmt_preco(r.minimo)), QLineEdit(core.fmt_preco(r.maximo))
        emin.setPlaceholderText("Mínimo")
        emax.setPlaceholderText("Máximo")
        ph.addWidget(emin)
        ph.addWidget(label("até", "Sub"))
        ph.addWidget(emax)
        v.addLayout(ph)
        erro = label("", None)
        erro.setStyleSheet(f"color: {C['red']};")
        v.addWidget(erro)
        v.addSpacing(6)
        bt = QHBoxLayout()
        sheet = None
        if i is not None:
            def excluir():
                del self.regras[i]
                core.salvar_regras(self.regras)
                sheet.fechar()
                self.recarregar()
            bt.addWidget(botao("Excluir", "Danger", excluir))
        bt.addStretch()
        bt.addWidget(botao("Cancelar", None, lambda: sheet.fechar()))

        def salvar():
            ts = termos.valores()
            if not ts:
                erro.setText("Adicione pelo menos uma palavra.")
                return
            try:
                mn = core._num(emin.text()) if emin.text().strip() else None
                mx = core._num(emax.text()) if emax.text().strip() else None
            except ValueError:
                erro.setText("Preço inválido. Use só números, ex: 3500")
                return
            nova = core.RegraRaw(ts, excl.valores(), mn, mx, r.ativo)
            if i is None:
                self.regras.append(nova)
            else:
                self.regras[i] = nova
            core.salvar_regras(self.regras)
            sheet.fechar()
            self.recarregar()
        s = botao("Salvar", "Primary", salvar)
        s.setDefault(True)
        bt.addWidget(s)
        v.addLayout(bt)
        sheet = Sheet(self.win, w, 500)
        termos.edit.setFocus()


class PaginaGrupos(Pagina):
    def __init__(self, win):
        super().__init__("Grupos", "Onde procurar ofertas")
        self.win = win
        self.titulos = {}
        self.acoes.addWidget(botao("＋  Adicionar", "Primary", self.abrir_seletor))
        self.lista_w = QWidget()
        self.lista = QVBoxLayout(self.lista_w)
        self.lista.setContentsMargins(0, 0, 4, 0)
        self.lista.setSpacing(8)
        self.lista.setAlignment(Qt.AlignTop)
        self.lay.addWidget(scroll_de(self.lista_w), 1)
        self.sheet = None
        win.worker.dialogos.connect(self._dialogos)
        win.worker.resolvido.connect(self._resolvido)
        win.worker.grupos_info.connect(self._info)
        self.recarregar()

    def _info(self, info):
        self.titulos.update(info)
        self.recarregar()

    def recarregar(self):
        limpar(self.lista)
        for gid in self.win.cfg["grupos"]:
            self.lista.addWidget(self._linha(gid))
        if not self.win.cfg["grupos"]:
            self.lista.addWidget(label("Nenhum grupo. Clique em “Adicionar”.", "Sub"))
        self.win.atualizar_resumo()

    def _avatar(self, texto, gid):
        cores = ["#FF9F0A", "#30D158", "#0A84FF", "#BF5AF2", "#FF375F", "#64D2FF", "#FFD60A"]
        a = QLabel((texto or "?").strip()[:1].upper())
        a.setFixedSize(38, 38)
        a.setAlignment(Qt.AlignCenter)
        a.setStyleSheet(f"background: {cores[abs(gid) % len(cores)]}; border-radius: 19px;"
                        "font-weight: 700; font-size: 16px; color: white;")
        return a

    def _linha(self, gid):
        titulo = self.titulos.get(gid, "")
        c = card()
        h = QHBoxLayout(c)
        h.setContentsMargins(14, 10, 10, 10)
        h.setSpacing(12)
        h.addWidget(self._avatar(titulo or "?", gid))
        v = QVBoxLayout()
        v.setSpacing(0)
        if titulo is None:
            t = label("Grupo não encontrado", "H2")
            t.setStyleSheet(f"color: {C['red']};")
        else:
            t = label(titulo or "Carregando…", "H2")
        v.addWidget(t)
        v.addWidget(label(str(gid), "Dim"))
        h.addLayout(v, 1)
        rm = botao("Remover", "Danger", lambda: self._remover(gid))
        h.addWidget(rm)
        return c

    def _remover(self, gid):
        self.win.cfg["grupos"] = [g for g in self.win.cfg["grupos"] if g != gid]
        self.win.salvar_cfg()
        self.win.worker.set_grupos(self.win.cfg["grupos"])
        self.recarregar()

    def _adicionar(self, gid, titulo):
        if gid not in self.win.cfg["grupos"]:
            self.win.cfg["grupos"].append(gid)
            self.titulos[gid] = titulo
            self.win.salvar_cfg()
            self.win.worker.set_grupos(self.win.cfg["grupos"])
        self.recarregar()

    # ---- seletor
    def abrir_seletor(self):
        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(10)
        v.addWidget(label("Adicionar grupos", "H1"))
        v.addWidget(label("Escolha entre os grupos e canais em que você participa.", "Sub"))
        self.busca = QLineEdit()
        self.busca.setPlaceholderText("🔍  Buscar…")
        self.busca.textChanged.connect(self._filtrar)
        v.addWidget(self.busca)
        self.sel_w = QWidget()
        self.sel = QVBoxLayout(self.sel_w)
        self.sel.setContentsMargins(0, 0, 4, 0)
        self.sel.setSpacing(2)
        self.sel.setAlignment(Qt.AlignTop)
        self.sel.addWidget(label("Carregando seus grupos…", "Sub"))
        sa = scroll_de(self.sel_w)
        sa.setFixedHeight(300)
        v.addWidget(sa)
        v.addWidget(label("OU COLE UM ID / LINK", "Section"))
        mh = QHBoxLayout()
        self.manual = QLineEdit()
        self.manual.setPlaceholderText("-1001234567890 ou t.me/grupo")
        mh.addWidget(self.manual, 1)
        mh.addWidget(botao("Adicionar", None, lambda: self.win.worker.resolver(self.manual.text())))
        v.addLayout(mh)
        self.msg = label("", "Dim", True)
        v.addWidget(self.msg)
        bt = QHBoxLayout()
        bt.addStretch()
        bt.addWidget(botao("Concluído", "Primary", lambda: (self.sheet.fechar(), setattr(self, "sheet", None))))
        v.addLayout(bt)
        self.sheet = Sheet(self.win, w, 520)
        self.linhas_sel = []
        self.win.worker.pedir_dialogos()

    def _dialogos(self, lst):
        if not self.sheet:
            return
        limpar(self.sel)
        self.linhas_sel = []
        if not lst:
            self.sel.addWidget(label("Não consegui listar (ainda conectando?).", "Sub"))
        for gid, nome, tipo in lst:
            row = QFrame()
            row.setStyleSheet("QFrame { border-radius: 8px; } QFrame:hover { background: rgba(255,255,255,0.05); }")
            h = QHBoxLayout(row)
            h.setContentsMargins(8, 6, 8, 6)
            av = self._avatar(nome, gid)
            av.setFixedSize(30, 30)
            av.setStyleSheet(av.styleSheet().replace("19px", "15px").replace("16px", "13px"))
            h.addWidget(av)
            h.addWidget(label(nome), 1)
            h.addWidget(label(tipo, "Dim"))
            tg = Toggle(gid in self.win.cfg["grupos"])
            tg.toggled.connect(lambda on, g=gid, n=nome: self._adicionar(g, n) if on else self._remover(g))
            h.addWidget(tg)
            self.sel.addWidget(row)
            self.linhas_sel.append((nome.lower(), row))

    def _filtrar(self, t):
        t = t.lower().strip()
        for nome, row in self.linhas_sel:
            row.setVisible(t in nome)

    def _resolvido(self, r):
        if not self.sheet:
            return
        if isinstance(r, str):
            self.msg.setStyleSheet(f"color: {C['red']};")
            self.msg.setText(r)
        else:
            self._adicionar(*r)
            self.msg.setStyleSheet(f"color: {C['green']};")
            self.msg.setText(f"✓ Adicionado: {r[1]}")
            self.manual.clear()


class PaginaAjustes(Pagina):
    def __init__(self, win):
        super().__init__("Ajustes", "")
        self.win = win
        cfg = win.cfg
        cont = QWidget()
        v = QVBoxLayout(cont)
        v.setContentsMargins(0, 0, 4, 0)
        v.setSpacing(8)
        v.setAlignment(Qt.AlignTop)

        v.addWidget(label("NOTIFICAÇÕES", "Section"))
        g = self._grupo(v)
        self._linha_toggle(g, "Notificação do Windows", "Aparece no canto da tela; clique para abrir",
                           cfg["toast"], lambda on: self._set("toast", on))
        self._linha_toggle(g, "Beep", "Três apitos no PC quando achar oferta",
                           cfg["beep"], lambda on: self._set("beep", on))
        self._linha_toggle(g, "Notch flutuante", "Pílula no topo da tela mostrando que está rodando",
                           cfg["notch"], self._notch, ultimo=True)

        v.addSpacing(10)
        v.addWidget(label("CELULAR (BOT DO TELEGRAM)", "Section"))
        g = self._grupo(v)
        lin = QHBoxLayout()
        self.token = QLineEdit(cfg["bot_token"])
        self.token.setPlaceholderText("Token do @BotFather")
        self.token.setEchoMode(QLineEdit.EchoMode.Password)
        self.token.editingFinished.connect(lambda: self._set("bot_token", self.token.text().strip()))
        lin.addWidget(self.token, 1)
        lin.addWidget(botao("Testar", None, self._testar_bot))
        g.addLayout(lin)
        self.bot_msg = label("Mande /start pro seu bot uma vez, para ele poder te escrever.", "Dim", True)
        g.addWidget(self.bot_msg)

        v.addSpacing(10)
        v.addWidget(label("SISTEMA", "Section"))
        g = self._grupo(v)
        self._linha_toggle(g, "Abrir com o Windows", "Liga sozinho (direto no notch) quando o PC iniciar",
                           autostart_ativo(), self._autostart, ultimo=True)

        v.addSpacing(10)
        v.addWidget(label("CONTA DO TELEGRAM", "Section"))
        g = self._grupo(v)
        self.conta = label("Conectando…", "H2")
        g.addWidget(self.conta)
        win.worker.conta.connect(self.conta.setText)
        api = QHBoxLayout()
        self.api_id = QLineEdit(cfg["api_id"])
        self.api_id.setPlaceholderText("api_id")
        self.api_hash = QLineEdit(cfg["api_hash"])
        self.api_hash.setPlaceholderText("api_hash")
        self.api_hash.setEchoMode(QLineEdit.EchoMode.Password)
        for e, k in ((self.api_id, "api_id"), (self.api_hash, "api_hash")):
            e.editingFinished.connect(lambda e=e, k=k: self._set(k, e.text().strip()))
        api.addWidget(self.api_id, 1)
        api.addWidget(self.api_hash, 2)
        g.addLayout(api)
        g.addWidget(label("Chaves de my.telegram.org — mudar exige reabrir o app.", "Dim"))

        v.addSpacing(16)
        sair = botao("Parar monitor e sair", "Danger", win.sair)
        v.addWidget(sair, 0, Qt.AlignLeft)
        self.lay.addWidget(scroll_de(cont), 1)

    def _grupo(self, v):
        c = card()
        l = QVBoxLayout(c)
        l.setContentsMargins(16, 12, 16, 12)
        l.setSpacing(10)
        v.addWidget(c)
        return l

    def _linha_toggle(self, g, titulo, sub, val, cb, ultimo=False):
        h = QHBoxLayout()
        t = QVBoxLayout()
        t.setSpacing(1)
        t.addWidget(label(titulo))
        t.addWidget(label(sub, "Dim"))
        h.addLayout(t, 1)
        tg = Toggle(val)
        tg.toggled.connect(cb)
        h.addWidget(tg)
        g.addLayout(h)
        if not ultimo:
            s = QFrame()
            s.setObjectName("Sep")
            g.addWidget(s)

    def _set(self, k, v):
        if self.win.cfg.get(k) != v:
            self.win.cfg[k] = v
            self.win.salvar_cfg()
            if k == "bot_token" and v and self.win.worker.me:
                m.AVISO_PARADA.update(token=v, chat=self.win.worker.me.id, enviado=False)

    def _notch(self, on):
        self._set("notch", on)
        self.win.notch.setVisible(on)

    def _autostart(self, on):
        try:
            definir_autostart(on)
        except Exception as e:
            print(f"[!] autostart: {e}")

    def _testar_bot(self):
        self._set("bot_token", self.token.text().strip())
        me = self.win.worker.me
        if not me:
            self.bot_msg.setText("Aguarde conectar ao Telegram e tente de novo.")
            return
        try:
            m.enviar_bot(self.win.cfg["bot_token"], me.id, "🔔 Teste do Avisa Oferta — está funcionando!")
            self.bot_msg.setStyleSheet(f"color: {C['green']};")
            self.bot_msg.setText("✓ Mensagem enviada! Confira o celular.")
        except Exception as e:
            self.bot_msg.setStyleSheet(f"color: {C['red']};")
            self.bot_msg.setText(f"Falhou: {e}. Você mandou /start pro bot?")


class PaginaAjuda(Pagina):
    PASSOS = [
        ("1", "Pegue o api_id e o api_hash",
         "Acesse my.telegram.org e entre com seu número.\n"
         "Clique em “API development tools” e crie um app (nome e apelido livres).\n"
         "Copie o api_id e o api_hash e cole em Ajustes → Conta do Telegram.\n"
         "Feche e abra o app de novo.", "https://my.telegram.org"),
        ("2", "Entre na sua conta",
         "Ao abrir, o app pede seu número (+55 DDD número), o código que chega no Telegram "
         "e, se tiver, a senha de duas etapas. Só na primeira vez.", None),
        ("3", "Crie um bot para avisar no celular",
         "No Telegram, fale com o @BotFather e envie /newbot.\n"
         "Escolha um nome e copie o token que ele devolver.\n"
         "Cole em Ajustes → Celular (Bot do Telegram) e clique em Testar.\n"
         "Importante: abra o seu bot e mande /start uma vez, senão ele não consegue te escrever.",
         "https://t.me/BotFather"),
        ("4", "Escolha os grupos",
         "Em Grupos → Adicionar, marque os grupos e canais de ofertas em que você já participa. "
         "Também dá para colar um link (t.me/grupo) ou o ID numérico.\n"
         "Para descobrir o ID de um grupo, use o bot @userinfobot ou @getidsbot "
         "encaminhando uma mensagem do grupo para ele.", "https://t.me/userinfobot"),
        ("5", "Crie seus alertas",
         "Em Alertas → Novo alerta, digite as palavras (ex: ps5) e aperte Enter.\n"
         "Use + para exigir várias juntas (air fryer + mondial), “Ignorar se tiver” para "
         "descartar (capa, película) e a faixa de preço para filtrar.", None),
        ("6", "Deixe rodando",
         "Em Ajustes ligue “Abrir com o Windows” e o notch. Pode fechar a janela: o app continua "
         "na bandeja, vigiando. Quando surgir uma oferta você recebe notificação, beep e "
         "mensagem no celular.", None),
    ]

    def __init__(self, win):
        super().__init__("Como configurar", "Passo a passo para começar")
        cont = QWidget()
        v = QVBoxLayout(cont)
        v.setContentsMargins(0, 0, 4, 0)
        v.setSpacing(10)
        v.setAlignment(Qt.AlignTop)
        for num, titulo, texto, url in self.PASSOS:
            c = card()
            h = QHBoxLayout(c)
            h.setContentsMargins(16, 14, 16, 14)
            h.setSpacing(14)
            n = QLabel(num)
            n.setFixedSize(28, 28)
            n.setAlignment(Qt.AlignCenter)
            n.setStyleSheet(f"background: {C['blue']}; border-radius: 14px; font-weight: 700;")
            h.addWidget(n, 0, Qt.AlignTop)
            col = QVBoxLayout()
            col.setSpacing(4)
            col.addWidget(label(titulo, "H2"))
            col.addWidget(label(texto, "Sub", True))
            if url:
                b = botao("Abrir " + url.replace("https://", ""), "Ghost",
                          lambda _=None, u=url: QDesktopServices.openUrl(QUrl(u)))
                col.addWidget(b, 0, Qt.AlignLeft)
            h.addLayout(col, 1)
            v.addWidget(c)
        self.lay.addWidget(scroll_de(cont), 1)


# ======================================================================= autostart
STARTUP = Path(os.environ.get("APPDATA", "")) / r"Microsoft\Windows\Start Menu\Programs\Startup\Avisa Oferta.vbs"


def pythonw() -> str:
    p = Path(sys.executable)
    w = p.with_name("pythonw.exe")
    return str(w if w.exists() else p)


def autostart_ativo() -> bool:
    return STARTUP.exists()


def definir_autostart(on: bool):
    if on:
        STARTUP.write_text(
            f'CreateObject("Wscript.Shell").Run """{pythonw()}"" ""{BASE / "app.py"}"" --oculto", 0, False\n',
            encoding="utf-8")
    elif STARTUP.exists():
        STARTUP.unlink()


# ======================================================================= notch
class Notch(QWidget):
    abrir = Signal()
    sair = Signal()
    esconder = Signal()

    H = 34

    def __init__(self, cfg, salvar_pos):
        super().__init__(None, Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setMouseTracking(True)
        self.setCursor(Qt.PointingHandCursor)
        self.salvar_pos = salvar_pos
        self.estado, self.curto, self.longo = "connecting", "Conectando", "Conectando…"
        self.oferta = None
        self.hover = False
        self._t = 0.0
        self._w = 150.0
        self.cx, self.y0 = cfg["notch_x"], cfg["notch_y"]
        if self.cx is None:
            scr = QGuiApplication.primaryScreen().availableGeometry()
            self.cx, self.y0 = scr.right() - 340, scr.top() + 8  # canto superior direito
        self._aplicar_geo()
        self._anim = QPropertyAnimation(self, b"larg", self)
        self._anim.setDuration(420)
        self._anim.setEasingCurve(QEasingCurve.OutBack)
        self._timer = QTimer(self, interval=40, timeout=self._tick)
        self._timer.start()
        self._fim_oferta = QTimer(self, singleShot=True, timeout=self._encerrar_oferta)
        self._drag = None
        self._moveu = False

    def _get(self):
        return self._w

    def _set(self, v):
        self._w = v
        self._aplicar_geo()

    larg = Property(float, _get, _set)

    def _aplicar_geo(self):
        w = int(self._w)
        self.setGeometry(int(self.cx - w / 2), int(self.y0), w, self.H)
        self.update()

    def _alvo(self) -> float:
        fm = QFontMetrics(fonte(12.5, QFont.Weight.DemiBold))
        if self.oferta:
            return min(480, fm.horizontalAdvance("🚨  " + self._texto()) + 60)
        return fm.horizontalAdvance(self._texto()) + 52

    def _texto(self):
        if self.oferta:
            o = self.oferta
            p = f"  ·  R$ {core.fmt_preco(o['preco'])}" if o.get("preco") else ""
            return f"{o['produto']}{p}  ·  {o['grupo']}"
        return self.longo if self.hover else self.curto

    def _redimensionar(self):
        self._anim.stop()
        self._anim.setStartValue(self._w)
        self._anim.setEndValue(self._alvo())
        self._anim.start()

    def set_info(self, estado, curto, longo):
        self.estado, self.curto, self.longo = estado, curto, longo
        self._redimensionar()

    def mostrar_oferta(self, o):
        self.oferta = o
        self._redimensionar()
        self._fim_oferta.start(15000)

    def _encerrar_oferta(self):
        self.oferta = None
        self._redimensionar()

    def _tick(self):
        self._t = (self._t + 0.03) % 1.0
        self.update()

    # ---- mouse
    def enterEvent(self, _):
        self.hover = True
        self._redimensionar()

    def leaveEvent(self, _):
        self.hover = False
        self._redimensionar()

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self._drag = e.globalPosition().toPoint()
            self._orig = (self.cx, self.y0)
            self._moveu = False

    def mouseMoveEvent(self, e):
        if self._drag is not None and e.buttons() & Qt.LeftButton:
            d = e.globalPosition().toPoint() - self._drag
            if abs(d.x()) + abs(d.y()) > 4:
                self._moveu = True
            if self._moveu:
                self.cx, self.y0 = self._orig[0] + d.x(), self._orig[1] + d.y()
                scr = self.screen().availableGeometry()
                if abs(self.y0 - scr.top()) < 18:   # gruda no topo
                    self.y0 = scr.top() + 6
                self._aplicar_geo()

    def mouseReleaseEvent(self, e):
        if e.button() != Qt.LeftButton:
            return
        if self._moveu:
            self.salvar_pos(int(self.cx), int(self.y0))
        elif self.oferta:
            QDesktopServices.openUrl(QUrl(self.oferta["link"]))
            self._encerrar_oferta()
        else:
            self.abrir.emit()
        self._drag = None

    def contextMenuEvent(self, e):
        menu = QMenu()
        menu.addAction("Abrir painel", self.abrir.emit)
        menu.addAction("Esconder notch", self.esconder.emit)
        menu.addSeparator()
        menu.addAction("Parar e sair", self.sair.emit)
        menu.exec(e.globalPos())

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        p.setPen(QPen(QColor(255, 255, 255, 34), 1))
        p.setBrush(QColor(0, 0, 0, 242))
        p.drawRoundedRect(r, r.height() / 2, r.height() / 2)

        cor = QColor(C["orange"] if self.oferta else ESTADO_COR.get(self.estado, C["orange"]))
        cy = self.H / 2
        cx = 18
        onda = self._t
        if self.oferta:  # brilho pulsando enquanto mostra oferta
            glow = QColor(cor)
            glow.setAlphaF(0.10 + 0.10 * math.sin(self._t * 2 * math.pi))
            p.setPen(Qt.NoPen)
            p.setBrush(glow)
            p.drawRoundedRect(r, r.height() / 2, r.height() / 2)
        halo = QColor(cor)
        halo.setAlphaF(0.5 * (1 - onda))
        p.setPen(Qt.NoPen)
        p.setBrush(halo)
        rr = 4 + 6 * onda
        p.drawEllipse(QRectF(cx - rr, cy - rr, rr * 2, rr * 2))
        p.setBrush(cor)
        p.drawEllipse(QRectF(cx - 4, cy - 4, 8, 8))

        p.setFont(fonte(12.5, QFont.Weight.DemiBold))
        p.setPen(QColor("white"))
        txt_r = QRectF(32, 0, self.width() - 46, self.H)
        txt = self._texto()
        if self.oferta:
            txt = "🚨  " + txt
        txt = QFontMetrics(p.font()).elidedText(txt, Qt.ElideRight, int(txt_r.width()))
        p.drawText(txt_r, Qt.AlignVCenter | Qt.AlignLeft, txt)


# ======================================================================= janela
class Janela(QWidget):
    M = 14  # margem para a sombra

    def __init__(self, cfg, worker):
        super().__init__(None, Qt.FramelessWindowHint | Qt.Window)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setWindowTitle("Avisa Oferta")
        self.setWindowIcon(criar_icone())
        self.cfg = cfg
        self.worker = worker
        self.historico = core.ler_historico()
        self.estado, self.detalhe = "connecting", ""
        self.n_lidas = 0
        self.resize(1040 + 2 * self.M, 680 + 2 * self.M)
        self.setMinimumSize(860, 560)

        raiz = QHBoxLayout(self)
        raiz.setContentsMargins(self.M, self.M, self.M, self.M)
        raiz.setSpacing(0)

        # ---- sidebar
        side = QWidget()
        side.setFixedWidth(220)
        sl = QVBoxLayout(side)
        sl.setContentsMargins(16, 16, 12, 16)
        sl.setSpacing(3)
        self.semaforo = Semaforo()
        self.semaforo.fechar.connect(self.ao_fechar)
        self.semaforo.minimizar.connect(self.showMinimized)
        self.semaforo.maximizar.connect(lambda: self.showNormal() if self.isMaximized() else self.showMaximized())
        sl.addWidget(self.semaforo)
        sl.addSpacing(22)
        marca = QHBoxLayout()
        ic = QLabel()
        ic.setPixmap(criar_icone().pixmap(30, 30))
        marca.addWidget(ic)
        mt = QVBoxLayout()
        mt.setSpacing(0)
        mt.addWidget(label("Avisa Oferta", "H2"))
        mt.addWidget(label("Black Friday mode", "Dim"))
        marca.addLayout(mt, 1)
        sl.addLayout(marca)
        sl.addSpacing(18)

        self.navs = []
        for i, (ico, nome) in enumerate([("◉", "Visão geral"), ("🔔", "Alertas"),
                                         ("💬", "Grupos"), ("⚙", "Ajustes"),
                                         ("❓", "Como configurar")]):
            b = QPushButton(f"  {ico}    {nome}")
            b.setObjectName("Nav")
            b.setCheckable(True)
            b.setCursor(Qt.PointingHandCursor)
            b.clicked.connect(lambda _, i=i: self.ir(i))
            sl.addWidget(b)
            self.navs.append(b)
        sl.addStretch()

        st = QHBoxLayout()
        self.mini_pulso = Pulso(8)
        st.addWidget(self.mini_pulso)
        self.mini_txt = label("Conectando…", "Dim", True)
        st.addWidget(self.mini_txt, 1)
        sl.addLayout(st)
        raiz.addWidget(side)

        # ---- conteúdo
        self.conteudo = QWidget()
        cl = QVBoxLayout(self.conteudo)
        cl.setContentsMargins(0, 18, 0, 0)
        self.pilha = QStackedWidget()
        cl.addWidget(self.pilha)
        grip_l = QHBoxLayout()
        grip_l.addStretch()
        grip_l.addWidget(QSizeGrip(self), 0, Qt.AlignBottom | Qt.AlignRight)
        cl.addLayout(grip_l)
        raiz.addWidget(self.conteudo, 1)

        self.pg_visao = PaginaVisao(self)
        self.pg_alertas = PaginaAlertas(self)
        self.pg_grupos = PaginaGrupos(self)
        self.pg_ajustes = PaginaAjustes(self)
        self.pg_ajuda = PaginaAjuda(self)
        for pg in (self.pg_visao, self.pg_alertas, self.pg_grupos, self.pg_ajustes, self.pg_ajuda):
            self.pilha.addWidget(pg)
        self.ir(0)

        # ---- notch / bandeja
        self.notch = Notch(cfg, self._salvar_notch)
        self.notch.abrir.connect(self.mostrar)
        self.notch.sair.connect(self.sair)
        self.notch.esconder.connect(self.notch.hide)
        if cfg["notch"]:
            self.notch.show()
        self.tray = QSystemTrayIcon(criar_icone(), self)
        tm = QMenu()
        tm.addAction("Abrir painel", self.mostrar)
        tm.addAction("Mostrar notch", self.notch.show)
        tm.addSeparator()
        tm.addAction("Parar e sair", self.sair)
        self.tray.setContextMenu(tm)
        self.tray.setToolTip("Avisa Oferta")
        self.tray.activated.connect(lambda r: self.mostrar() if r == QSystemTrayIcon.ActivationReason.Trigger else None)
        self.tray.show()

        worker.status.connect(self._status)
        worker.oferta.connect(self._oferta)
        worker.pedir.connect(self._pedir_login)
        worker.lidas.connect(self._lidas)
        self.sheet_login = None
        self.atualizar_resumo()

    # ---- navegação
    def ir(self, i):
        self.pilha.setCurrentIndex(i)
        for j, b in enumerate(self.navs):
            b.setChecked(i == j)

    def mostrar(self):
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def ao_fechar(self):
        self.hide()  # continua rodando no notch / bandeja
        if not self.cfg["notch"]:
            self.tray.showMessage("Avisa Oferta", "Continuo monitorando aqui na bandeja.",
                                  criar_icone(), 3000)

    def closeEvent(self, e):
        e.ignore()
        self.ao_fechar()

    def sair(self):
        m.avisar_parada("app fechado por você")
        self.worker.parar()
        self.worker.wait(3000)
        self.notch.close()
        self.tray.hide()
        QApplication.instance().quit()

    # ---- arrastar janela pela faixa do topo
    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton and e.position().y() < 70:
            self.windowHandle().startSystemMove()

    def mouseDoubleClickEvent(self, e):
        if e.position().y() < 70:
            self.showNormal() if self.isMaximized() else self.showMaximized()

    def changeEvent(self, e):
        if e.type() == e.Type.WindowStateChange:
            mg = 0 if self.isMaximized() else self.M
            self.layout().setContentsMargins(mg, mg, mg, mg)
        super().changeEvent(e)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        mg = self.layout().contentsMargins().left()
        rad = 0 if mg == 0 else 14
        r = QRectF(self.rect()).adjusted(mg, mg, -mg, -mg)
        # sombra suave
        for i in range(mg):
            a = int(38 * (1 - i / mg) ** 2)
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(0, 0, 0, a))
            k = i + 1
            p.drawRoundedRect(r.adjusted(-k, -k + 3, k, k + 3), rad + k, rad + k)
        path = QPainterPath()
        path.addRoundedRect(r, rad, rad)
        p.setClipPath(path)
        p.fillRect(r, QColor(C["bg"]))
        p.fillRect(QRectF(r.left(), r.top(), 220, r.height()), QColor(C["side"]))
        p.fillRect(QRectF(r.left() + 220, r.top(), 1, r.height()), QColor(0, 0, 0, 90))
        p.setClipping(False)
        p.setPen(QPen(QColor(255, 255, 255, 22), 1))
        p.setBrush(Qt.NoBrush)
        p.drawRoundedRect(r.adjusted(.5, .5, -.5, -.5), rad, rad)

    # ---- estado
    def salvar_cfg(self):
        core.salvar_config(self.cfg)

    def _salvar_notch(self, x, y):
        self.cfg["notch_x"], self.cfg["notch_y"] = x, y
        self.salvar_cfg()

    def _lidas(self, n):
        self.n_lidas = n
        self.pg_visao.n_lidas.setText(f"{n:,}".replace(",", "."))

    def _status(self, estado, detalhe):
        self.estado, self.detalhe = estado, detalhe
        if estado != "login" and self.sheet_login:
            self.sheet_login.fechar()
            self.sheet_login = None
        self.atualizar_resumo()

    def atualizar_resumo(self):
        if not hasattr(self, "pg_ajustes"):
            return
        ng = len(self.cfg["grupos"])
        na = sum(1 for r in core.ler_regras() if r.ativo)
        resumo = f"{ng} grupo{'s' if ng != 1 else ''} · {na} alerta{'s' if na != 1 else ''}"
        hoje = datetime.now().date()
        no = sum(1 for o in self.historico if datetime.fromtimestamp(o["ts"]).date() == hoje)
        titulos = {"running": "Monitorando", "connecting": "Conectando…", "login": "Login necessário",
                   "error": "Problema", "stopped": "Parado"}
        t = titulos.get(self.estado, "…")
        det = self.detalhe if self.estado != "running" else f"{resumo} · você será avisado na hora"
        self.pg_visao.set_status(self.estado, t, det)
        cor = ESTADO_COR.get(self.estado, C["orange"])
        self.mini_pulso.set_cor(cor)
        self.mini_txt.setText(t if self.estado == "running" else (self.detalhe or t))
        curto = {"running": "Monitorando", "connecting": "Conectando", "login": "Faça login",
                 "error": "Problema", "stopped": "Parado"}.get(self.estado, "…")
        longo = (f"{resumo} · {no} oferta{'s' if no != 1 else ''} hoje" if self.estado == "running"
                 else (self.detalhe or curto))
        self.notch.set_info(self.estado, curto, longo)
        self.tray.setToolTip(f"Avisa Oferta — {t}")

    def _oferta(self, o):
        self.historico.insert(0, o)
        core.salvar_historico(self.historico)
        self.pg_visao.atualizar_feed()
        self.atualizar_resumo()
        if self.cfg["notch"]:
            self.notch.mostrar_oferta(o)

    # ---- login
    def _pedir_login(self, tipo, erro):
        self.mostrar()
        if self.sheet_login:
            self.sheet_login.fechar()
        textos = {
            "phone": ("Entrar no Telegram", "Seu número com DDI e DDD.", "+55 11 99999-8888"),
            "code": ("Código de acesso", "Digite o código que o Telegram te mandou (no app).", "12345"),
            "password": ("Verificação em duas etapas", "Sua senha da nuvem do Telegram.", "Senha"),
        }
        tit, sub, ph = textos[tipo]
        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(10)
        v.addWidget(label(tit, "H1"))
        v.addWidget(label(sub, "Sub", True))
        e = QLineEdit()
        e.setPlaceholderText(ph)
        if tipo == "password":
            e.setEchoMode(QLineEdit.EchoMode.Password)
        v.addWidget(e)
        if erro:
            er = label(erro)
            er.setStyleSheet(f"color: {C['red']};")
            v.addWidget(er)
        bt = QHBoxLayout()
        bt.addStretch()
        ok = botao("Continuar", "Primary")
        bt.addWidget(ok)
        v.addLayout(bt)

        def enviar():
            val = e.text().strip()
            if tipo == "phone":
                val = "+" + re.sub(r"\D", "", val)
            if val.strip("+"):
                ok.setEnabled(False)
                self.worker.responder(val)
        ok.clicked.connect(enviar)
        e.returnPressed.connect(enviar)
        self.sheet_login = Sheet(self, w, 420)
        e.setFocus()


# ======================================================================= main
def main():
    if sys.platform == "win32":
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("AvisaOferta.App")

    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    app.setFont(fonte(13))
    app.setStyleSheet(QSS)
    app.setWindowIcon(criar_icone())

    # uma instância só: se já estiver aberto, só mostra a janela
    nome = "avisa-oferta-app"
    sock = QLocalSocket()
    sock.connectToServer(nome)
    if sock.waitForConnected(300):
        sock.write(b"show")
        sock.flush()
        sock.waitForBytesWritten(300)
        return
    QLocalServer.removeServer(nome)
    servidor = QLocalServer()
    servidor.listen(nome)

    cfg = core.carregar_config()
    worker = Worker(cfg)
    win = Janela(cfg, worker)
    servidor.newConnection.connect(lambda: (servidor.nextPendingConnection(), win.mostrar()))

    app.commitDataRequest.connect(lambda *_: m.avisar_parada("Windows desligando"))
    app.aboutToQuit.connect(lambda: m.avisar_parada("app fechado"))

    if "--oculto" not in sys.argv:
        win.show()
    worker.start()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
