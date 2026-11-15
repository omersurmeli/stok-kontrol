"""Netsis stok fiyatları için iş kuralları ve kontrollü SQL erişimi.

Varsayılan çalışma biçimi SALT OKUNUR. SQL yazma sadece açıkça
NETSIS_WRITE_ENABLED=1 yapıldığında ve kullanıcı onayıyla kullanılabilir.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation, ROUND_CEILING, ROUND_HALF_UP
from pathlib import Path
from datetime import datetime, timezone
import getpass
import json
import os

CENT = Decimal("0.01")


def decimal_value(value) -> Decimal:
    if value is None or value == "":
        return Decimal("0")
    try:
        result = Decimal(str(value).strip().replace(",", "."))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError("Geçerli bir sayısal değer giriniz.") from exc
    if not result.is_finite():
        raise ValueError("Sonsuz/NaN fiyat kullanılamaz.")
    return result


def money(value: Decimal) -> Decimal:
    return decimal_value(value).quantize(CENT, rounding=ROUND_HALF_UP)


def percentage(value) -> Decimal:
    number = decimal_value(value)
    if number < Decimal("-100") or number > Decimal("1000"):
        raise ValueError("Yüzde değeri -100 ile 1000 arasında olmalıdır.")
    return number


def profit_markup(purchase: Decimal, sale: Decimal) -> Decimal | None:
    """Maliyet üzerinden kâr yüzdesi."""
    if purchase <= 0:
        return None
    return (sale - purchase) * 100 / purchase


def profit_margin(purchase: Decimal, sale: Decimal) -> Decimal | None:
    """Satış fiyatı üzerinden brüt kâr marjı."""
    if sale <= 0:
        return None
    return (sale - purchase) * 100 / sale


def round_up_to_90(value: Decimal) -> Decimal:
    """Hedef fiyatın altına düşmeden ... ,90 ile biten ilk tutar."""
    price = decimal_value(value)
    if price < 0:
        raise ValueError("Negatif fiyat geçersiz.")
    if price == 0:
        return Decimal("0")
    units = (price - Decimal("0.90")).to_integral_value(rounding=ROUND_CEILING)
    return money(units + Decimal("0.90"))


@dataclass(frozen=True)
class Stock:
    code: str
    name: str
    group: str
    code1: str
    code2: str
    purchase: Decimal
    sale: Decimal
    barcode1: str = ""
    barcode2: str = ""
    barcode3: str = ""


@dataclass(frozen=True)
class PriceChange:
    code: str
    old_purchase: Decimal
    old_sale: Decimal
    new_purchase: Decimal
    new_sale: Decimal


def propose_change(stock: Stock, purchase_percent, sale_percent, round_sale=False) -> PriceChange | None:
    ap, sp = percentage(purchase_percent), percentage(sale_percent)
    new_purchase = money(stock.purchase * (Decimal("1") + ap / 100))
    new_sale = money(stock.sale * (Decimal("1") + sp / 100))
    if round_sale and sp != 0:
        new_sale = round_up_to_90(new_sale)
    if min(new_purchase, new_sale) < 0:
        raise ValueError("Negatif fiyat kaydedilemez.")
    if new_purchase == stock.purchase and new_sale == stock.sale:
        return None
    return PriceChange(stock.code, stock.purchase, stock.sale, new_purchase, new_sale)


@dataclass(frozen=True)
class NetsisSettings:
    server: str
    database: str
    driver: str = "ODBC Driver 17 for SQL Server"
    auth: str = "windows"
    user: str = ""
    password: str = ""
    write_enabled: bool = False

    @classmethod
    def from_env(cls) -> NetsisSettings:
        server = os.getenv("NETSIS_SERVER", "").strip()
        database = os.getenv("NETSIS_DATABASE", "").strip()
        auth = os.getenv("NETSIS_AUTH", "windows").strip().lower()
        if not server or not database:
            raise ValueError("NETSIS_SERVER ve NETSIS_DATABASE tanımlanmalı.")
        if auth not in ("windows", "sql"):
            raise ValueError("NETSIS_AUTH yalnızca windows veya sql olabilir.")
        user = os.getenv("NETSIS_USER", "").strip()
        password = os.getenv("NETSIS_PASSWORD", "")
        if auth == "sql" and (not user or not password):
            raise ValueError("SQL bağlantısı için NETSIS_USER ve NETSIS_PASSWORD gerekli.")
        return cls(
            server=server, database=database,
            driver=os.getenv("NETSIS_DRIVER", "ODBC Driver 17 for SQL Server"),
            auth=auth, user=user, password=password,
            write_enabled=os.getenv("NETSIS_WRITE_ENABLED", "0") == "1",
        )

    def connection_string(self) -> str:
        def brace(v: str) -> str:
            return "{" + v.replace("}", "}}") + "}"
        fields = [
            "DRIVER=" + brace(self.driver),
            "SERVER=" + brace(self.server),
            "DATABASE=" + brace(self.database),
            "APP=MVM-Stok-Kontrol",
            "Connection Timeout=8",
        ]
        if self.auth == "windows":
            fields.append("Trusted_Connection=yes")
        else:
            fields.extend(("UID=" + brace(self.user), "PWD=" + brace(self.password)))
        return ";".join(fields) + ";"


class ConcurrentPriceChangeError(RuntimeError):
    """Netsis fiyatı okunduktan sonra değiştirilmiş ya da stok bulunamamış."""


class AuditLogError(RuntimeError):
    """SQL commit başarılı ancak yerel işlem günlüğü kaydedilemedi."""


class NetsisRepository:
    """Yalnızca bilinen Netsis alanlarına erişir; kullanıcı girdisi SQL'e eklenmez."""

    def __init__(self, settings: NetsisSettings, connect_factory=None):
        self.settings = settings
        self.connect_factory = connect_factory

    def _connect(self):
        if self.connect_factory:
            return self.connect_factory(self.settings.connection_string())
        try:
            import pyodbc
        except ImportError as exc:
            raise RuntimeError("pyodbc kurulu değil. requirements.txt dosyasını yükleyin.") from exc
        return pyodbc.connect(self.settings.connection_string(), autocommit=False, timeout=8)

    def load_stocks(self) -> list[Stock]:
        conn = self._connect()
        try:
            cur = conn.cursor()
            # Netsis kurulumları arasında opsiyonel barkod sütunları farklı olabilir.
            cur.execute(
                "SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS "
                "WHERE TABLE_NAME = 'TBLSTSABIT' AND TABLE_SCHEMA = 'dbo'"
            )
            available = {str(row[0]).upper() for row in cur.fetchall()}
            required = {
                "STOK_KODU", "STOK_ADI", "GRUP_KODU", "KOD_1",
                "KOD_2", "ALIS_FIAT1", "SATIS_FIAT1",
            }
            missing = required - available
            if missing:
                raise RuntimeError("Netsis TBLSTSABIT alanları eksik: " + ", ".join(sorted(missing)))
            barcode_columns = [
                ("COALESCE(BARKOD1, '')" if "BARKOD1" in available else "''"),
                ("COALESCE(BARKOD2, '')" if "BARKOD2" in available else "''"),
                ("COALESCE(BARKOD3, '')" if "BARKOD3" in available else "''"),
            ]
            query = (
                "SELECT STOK_KODU, STOK_ADI, ISNULL(GRUP_KODU,''), "
                "ISNULL(KOD_1,''), ISNULL(KOD_2,''), "
                "ISNULL(ALIS_FIAT1,0), ISNULL(SATIS_FIAT1,0), "
                + ", ".join(barcode_columns) + " FROM dbo.TBLSTSABIT ORDER BY STOK_KODU"
            )
            cur.execute(query)
            rows = cur.fetchall()
            return [
                Stock(str(r[0]).strip(), str(r[1] or "").strip(),
                      str(r[2] or "").strip(), str(r[3] or "").strip(),
                      str(r[4] or "").strip(), decimal_value(r[5]), decimal_value(r[6]),
                      str(r[7] or "").strip(), str(r[8] or "").strip(),
                      str(r[9] or "").strip())
                for r in rows
            ]
        finally:
            conn.close()

    def save_changes(self, changes: list[PriceChange]) -> int:
        """Tek transaction; sadece değişen stoklar; eşzamanlı değişiklikte tam rollback."""
        if not self.settings.write_enabled:
            raise PermissionError("SQL yazma kapalı: NETSIS_WRITE_ENABLED=1 gerekli.")
        if not changes:
            return 0
        codes = [x.code for x in changes]
        if len(set(codes)) != len(codes):
            raise ValueError("Aynı stok kodu birden fazla kez gönderildi.")
        for ch in changes:
            if not ch.code or min(ch.new_purchase, ch.new_sale) < 0:
                raise ValueError("Stok kodu boş veya fiyat negatif olamaz.")
            if ch.old_purchase == ch.new_purchase and ch.old_sale == ch.new_sale:
                raise ValueError("Değişiklik içermeyen stok kaydedilemez.")
        conn = self._connect()
        try:
            cur = conn.cursor()
            for ch in changes:
                cur.execute(
                    "UPDATE dbo.TBLSTSABIT "
                    "SET ALIS_FIAT1=?, SATIS_FIAT1=? "
                    "WHERE STOK_KODU=? "
                    "AND ISNULL(ALIS_FIAT1,0)=? AND ISNULL(SATIS_FIAT1,0)=?",
                    str(ch.new_purchase), str(ch.new_sale), ch.code,
                    str(ch.old_purchase), str(ch.old_sale)
                )
                if cur.rowcount != 1:
                    raise ConcurrentPriceChangeError(
                        ch.code + ": fiyat başka bir işlemde değişmiş ya da stok bulunamamış."
                    )
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()
        # Commit başarılı oldu; audit hatası yanlışlıkla SQL rollback gibi sunulmaz.
        try:
            self._write_audit(changes)
        except OSError as exc:
            raise AuditLogError(
                "Netsis fiyatları GÜNCELLENDİ; ancak yerel işlem geçmişi yazılamadı. "
                "Günlük klasörünün yazma iznini kontrol edin."
            ) from exc
        return len(changes)

    @staticmethod
    def _write_audit(changes: list[PriceChange]) -> None:
        folder = Path.home() / ".mvm-stok-kontrol"
        folder.mkdir(parents=True, exist_ok=True)
        record = {
            "time_utc": datetime.now(timezone.utc).isoformat(),
            "windows_user": getpass.getuser(),
            "changes": [
                {"stock_code": c.code, "old_purchase": str(c.old_purchase),
                 "old_sale": str(c.old_sale), "new_purchase": str(c.new_purchase),
                 "new_sale": str(c.new_sale)}
                for c in changes
            ],
        }
        with (folder / "price_audit.jsonl").open("a", encoding="utf-8") as out:
            out.write(json.dumps(record, ensure_ascii=False) + "\n")
