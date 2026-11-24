"""Leitura/gravação de config.ini, alertas.txt e histórico — compartilhado pelo app."""
import configparser
import json
import re
from dataclasses import dataclass, field
from pathlib import Path

BASE = Path(__file__).resolve().parent
CONFIG = BASE / "config.ini"
ALERTAS = BASE / "alertas.txt"
HISTORICO = BASE / "ofertas.json"

SIM = ("sim", "s", "yes", "1", "true")


# ------------------------------------------------------------------ config
def carregar_config() -> dict:
    cfg = configparser.ConfigParser()
    cfg.read(CONFIG, encoding="utf-8")
    g = lambda s, k, d="": cfg.get(s, k, fallback=d).strip()
    ids = [int(x) for x in re.split(r"[,\s]+", g("grupos", "ids")) if re.fullmatch(r"-?\d+", x)]
    nx, ny = g("interface", "notch_x"), g("interface", "notch_y")
    return {
        "api_id": g("telegram", "api_id"),
        "api_hash": g("telegram", "api_hash"),
        "bot_token": g("aviso", "bot_token"),
        "beep": g("aviso", "beep", "sim").lower() in SIM,
        "toast": g("aviso", "notificacao_windows", "sim").lower() in SIM,
        "grupos": ids,
        "notch": g("interface", "notch", "sim").lower() in SIM,
        "notch_x": int(nx) if nx.lstrip("-").isdigit() else None,
        "notch_y": int(ny) if ny.lstrip("-").isdigit() else None,
    }


def salvar_config(c: dict):
    sn = lambda b: "sim" if b else "nao"
    texto = f"""# Configuração do Avisa Oferta (editável pelo app em Ajustes)

[telegram]
# https://my.telegram.org -> API development tools
api_id = {c['api_id']}
api_hash = {c['api_hash']}

[aviso]
# Token do bot (@BotFather). Mande /start pro bot para ele poder te avisar.
bot_token = {c['bot_token']}
beep = {sn(c['beep'])}
notificacao_windows = {sn(c['toast'])}

[grupos]
ids = {', '.join(str(i) for i in c['grupos'])}

[interface]
notch = {sn(c['notch'])}
notch_x = {'' if c['notch_x'] is None else c['notch_x']}
notch_y = {'' if c['notch_y'] is None else c['notch_y']}
"""
    CONFIG.write_text(texto, encoding="utf-8")


# ------------------------------------------------------------------ alertas
@dataclass
class RegraRaw:
    termos: list[str]
    excluir: list[str] = field(default_factory=list)
    minimo: float | None = None
    maximo: float | None = None
    ativo: bool = True

    @property
    def titulo(self) -> str:
        t = self.termos[0] if self.termos else "?"
        return t.upper() if len(t) <= 5 else t[:1].upper() + t[1:]


def _num(v: str) -> float:
    return float(v.strip().replace(".", "").replace(",", "."))


def fmt_preco(v: float | None) -> str:
    if v is None:
        return ""
    if float(v).is_integer():
        return f"{int(v):,}".replace(",", ".")
    return f"{v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _fmt_num_linha(v: float) -> str:
    return str(int(v)) if float(v).is_integer() else f"{v:.2f}".replace(".", ",")


def parse_linha(linha: str) -> RegraRaw | None:
    linha = linha.strip()
    ativo = True
    if linha.lower().startswith("#off"):
        ativo, linha = False, linha[4:].strip()
    elif not linha or linha.startswith("#"):
        return None
    partes = [p.strip() for p in linha.split(";")]
    termos = [t.strip() for t in partes[0].split("|") if t.strip()]
    if not termos:
        return None
    r = RegraRaw(termos=termos, ativo=ativo)
    for p in partes[1:]:
        k, _, v = p.partition(":")
        k = k.strip().lower()
        try:
            if k == "sem":
                r.excluir = [w.strip() for w in v.split(",") if w.strip()]
            elif k == "min" and v.strip():
                r.minimo = _num(v)
            elif k == "max" and v.strip():
                r.maximo = _num(v)
        except ValueError:
            pass
    return r


def para_linha(r: RegraRaw) -> str:
    s = " | ".join(r.termos)
    if r.excluir:
        s += " ; sem: " + ", ".join(r.excluir)
    if r.minimo is not None:
        s += f" ; min: {_fmt_num_linha(r.minimo)}"
    if r.maximo is not None:
        s += f" ; max: {_fmt_num_linha(r.maximo)}"
    return s if r.ativo else "#off " + s


def ler_regras() -> list[RegraRaw]:
    if not ALERTAS.exists():
        return []
    return [r for r in map(parse_linha, ALERTAS.read_text(encoding="utf-8").splitlines()) if r]


CABECALHO = """# ============================================================
#  ALERTAS DE OFERTA — uma regra por linha (editável pelo app)
#  termo1 | termo2 ; sem: palavra, palavra ; min: 100 ; max: 500
#  "|" = alternativas · "+" dentro do termo = palavras juntas
#  Linhas "#off" são alertas desligados.
# ============================================================
"""


def salvar_regras(regras: list[RegraRaw]):
    ALERTAS.write_text(CABECALHO + "\n" + "\n".join(para_linha(r) for r in regras) + "\n",
                       encoding="utf-8")


# ------------------------------------------------------------------ histórico
def ler_historico() -> list[dict]:
    try:
        return json.loads(HISTORICO.read_text(encoding="utf-8"))
    except Exception:
        return []


def salvar_historico(itens: list[dict]):
    try:
        HISTORICO.write_text(json.dumps(itens[:200], ensure_ascii=False, indent=1), encoding="utf-8")
    except Exception:
        pass
