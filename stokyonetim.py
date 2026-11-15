"""MVM Yavaşlar | Netsis Stok Kontrol. Windows/Tkinter masaüstü arayüzü."""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk, messagebox
from decimal import Decimal

from netsis_core import (
    NetsisRepository, NetsisSettings, Stock, PriceChange,
    profit_markup, profit_margin, propose_change,
)

BG = "#f4f7fb"
NAVY = "#123b68"
BLUE = "#1766b1"
ORANGE = "#ee8d24"
MAX_VISIBLE = 3000


def fmt(value: Decimal | None) -> str:
    return "—" if value is None else f"{value:,.2f}"


class StockControlApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        root.title("MVM YAVAŞLAR | Netsis Stok ve Fiyat Kontrol")
        root.geometry("1480x860")
        root.minsize(1100, 650)
        root.configure(bg=BG)
        self.stocks: dict[str, Stock] = {}
        self.pending: dict[str, PriceChange] = {}
        self.visible_codes: list[str] = []
        self.search = tk.StringVar()
        self.group = tk.StringVar(value="Tümü")
        self.code1 = tk.StringVar()
        self.code2 = tk.StringVar()
        self.condition = tk.StringVar(value="Tümü")
        self.purchase_pct = tk.StringVar(value="0")
        self.sale_pct = tk.StringVar(value="0")
        self.round_sale = tk.BooleanVar(value=False)
        self.status = tk.StringVar(value="Yapılandırma okunuyor...")
        try:
            self.settings = NetsisSettings.from_env()
            self.repo = NetsisRepository(self.settings)
            self.settings_error = None
        except ValueError as exc:
            self.settings = None
            self.repo = None
            self.settings_error = str(exc)
        self._build_ui()
        if self.repo:
            root.after(100, self.reload)
        else:
            self.status.set("Bağlantı ayarları eksik.")
            root.after(100, lambda: messagebox.showwarning("Netsis bağlantısı", self.settings_error))

    def _build_ui(self):
        style = ttk.Style()
        if "clam" in style.theme_names():
            style.theme_use("clam")
        style.configure("Treeview", rowheight=29, font=("Segoe UI", 9),
                        background="#ffffff", foreground="#243244", fieldbackground="white")
        style.configure("Treeview.Heading", font=("Segoe UI", 9, "bold"),
                        background="#e6edf6", foreground=NAVY, relief="flat")
        style.map("Treeview", background=[("selected", BLUE)], foreground=[("selected", "white")])
        style.configure("TCombobox", padding=5)

        header = tk.Frame(self.root, bg=NAVY, height=70)
        header.pack(fill="x")
        tk.Label(header, text="MVM  |  STOK & FİYAT KONTROL", bg=NAVY,
                 fg="white", font=("Segoe UI", 18, "bold")).pack(side="left", padx=24, pady=17)
        mode = "SQL YAZMA AÇIK • ONAY GEREKLİ" if self.settings and self.settings.write_enabled else "SALT OKUNUR • GÜVENLİ MOD"
        tk.Label(header, text=mode, bg=NAVY, fg="#fcb45e",
                 font=("Segoe UI", 10, "bold")).pack(side="right", padx=26)

        cards = tk.Frame(self.root, bg=BG)
        cards.pack(fill="x", padx=18, pady=(16, 8))
        self.total_label = self._card(cards, "Filtrelenen stok", "#1766b1")
        self.loss_label = self._card(cards, "Zararlı fiyatlanan", "#ba3c3c")
        self.pending_label = self._card(cards, "Onay bekleyen", "#d27b16")
        self.avg_margin_label = self._card(cards, "Ort. brüt marj % (birim bazlı)", "#2d8750")

        filter_box = tk.LabelFrame(self.root, text="  STOK FİLTRELERİ  ", bg="white", fg=NAVY,
                                   font=("Segoe UI", 10, "bold"), padx=12, pady=10)
        filter_box.pack(fill="x", padx=18, pady=6)
        entries = [
            ("Stok adı / kod / barkod", self.search, 27),
            ("Kod 1 (raf)", self.code1, 13),
            ("Kod 2", self.code2, 13),
        ]
        for index, (title, var, width) in enumerate(entries):
            cell = tk.Frame(filter_box, bg="white")
            cell.grid(row=0, column=index, padx=8, sticky="w")
            tk.Label(cell, text=title, bg="white", fg="#4b5b71").pack(anchor="w")
            tk.Entry(cell, textvariable=var, width=width, font=("Segoe UI", 10)).pack(pady=4)
            var.trace_add("write", lambda *_: self.refresh())
        group_cell = tk.Frame(filter_box, bg="white")
        group_cell.grid(row=0, column=3, padx=8, sticky="w")
        tk.Label(group_cell, text="Stok grubu", bg="white", fg="#4b5b71").pack(anchor="w")
        self.group_box = ttk.Combobox(group_cell, textvariable=self.group, state="readonly", width=17,
                                      values=["Tümü"])
        self.group_box.pack(pady=4)
        self.group_box.bind("<<ComboboxSelected>>", lambda _: self.refresh())
        cond_cell = tk.Frame(filter_box, bg="white")
        cond_cell.grid(row=0, column=4, padx=8, sticky="w")
        tk.Label(cond_cell, text="Analiz filtresi", bg="white", fg="#4b5b71").pack(anchor="w")
        ttk.Combobox(cond_cell, textvariable=self.condition, state="readonly", width=19,
                     values=["Tümü", "Alış 0", "Satış 0", "Zarar", "Marj <%20", "Maliyet kârı >= %100"]).pack(pady=4)
        self.condition.trace_add("write", lambda *_: self.refresh())

        operation = tk.LabelFrame(self.root, text="  SEÇİLİ ÜRÜNLER İÇİN FİYAT ÖNERİSİ  ", bg="white",
                                   fg=NAVY, font=("Segoe UI", 10, "bold"), padx=12, pady=10)
        operation.pack(fill="x", padx=18, pady=6)
        tk.Label(operation, text="Alış değişim %", bg="white").pack(side="left", padx=(8, 4))
        tk.Entry(operation, width=8, textvariable=self.purchase_pct).pack(side="left", padx=(0, 16))
        tk.Label(operation, text="Satış değişim %", bg="white").pack(side="left", padx=(0, 4))
        tk.Entry(operation, width=8, textvariable=self.sale_pct).pack(side="left", padx=(0, 16))
        tk.Checkbutton(operation, text="Satışı yukarı ... ,90'a yuvarla", bg="white",
                       variable=self.round_sale).pack(side="left")
        tk.Button(operation, text="SEÇİLİLERE ÖNİZLEME", bg="#267d56", fg="white", relief="flat",
                  font=("Segoe UI", 9, "bold"), padx=12, pady=8,
                  command=self.preview_selected).pack(side="right", padx=4)
        tk.Button(operation, text="ÖNİZLEMEYİ TEMİZLE", bg="#65788f", fg="white", relief="flat",
                  font=("Segoe UI", 9, "bold"), padx=12, pady=8,
                  command=self.clear_pending).pack(side="right", padx=4)

        table_frame = tk.Frame(self.root, bg="white")
        table_frame.pack(fill="both", expand=True, padx=18, pady=(8, 4))
        self.columns = (
            "code", "name", "group", "code1", "code2", "purchase", "sale",
            "markup", "margin", "new_purchase", "new_sale",
        )
        titles = (
            "STOK KODU", "STOK ADI", "GRUP", "KOD 1", "KOD 2", "ALIŞ BF",
            "SATIŞ BF", "MALİYET KÂR %", "BRÜT MARJ %", "YENİ ALIŞ", "YENİ SATIŞ",
        )
        self.tree = ttk.Treeview(table_frame, columns=self.columns, show="headings", selectmode="extended")
        for key, title in zip(self.columns, titles):
            self.tree.heading(key, text=title)
            self.tree.column(key, width=(285 if key == "name" else 105), anchor="w" if key == "name" else "center")
        self.tree.tag_configure("pending", background="#fff2d5")
        self.tree.tag_configure("loss", foreground="#b32727")
        scroll_y = ttk.Scrollbar(table_frame, orient="vertical", command=self.tree.yview)
        scroll_x = ttk.Scrollbar(table_frame, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=scroll_y.set, xscrollcommand=scroll_x.set)
        self.tree.grid(row=0, column=0, sticky="nsew")
        scroll_y.grid(row=0, column=1, sticky="ns")
        scroll_x.grid(row=1, column=0, sticky="ew")
        table_frame.rowconfigure(0, weight=1)
        table_frame.columnconfigure(0, weight=1)

        bottom = tk.Frame(self.root, bg=BG)
        bottom.pack(fill="x", padx=20, pady=(6, 15))
        tk.Label(bottom, textvariable=self.status, bg=BG, fg="#526477",
                 font=("Segoe UI", 9)).pack(side="left", padx=3)
        tk.Button(bottom, text="VERİLERİ YENİLE", bg=BLUE, fg="white",
                  font=("Segoe UI", 9, "bold"), padx=16, pady=9,
                  command=self.reload).pack(side="right", padx=5)
        self.save_button = tk.Button(bottom, text="ONAYLA VE NETSİS'E KAYDET",
                                     bg=ORANGE, fg="#152b44", font=("Segoe UI", 9, "bold"),
                                     padx=16, pady=9, command=self.save)
        self.save_button.pack(side="right", padx=5)
        if not (self.settings and self.settings.write_enabled):
            self.save_button.configure(state="disabled")
        self.root.bind("<Control-r>", lambda _: self.reload())

    @staticmethod
    def _card(parent, heading: str, color: str):
        panel = tk.Frame(parent, bg="white", highlightbackground="#dce5ee",
                         highlightthickness=1, width=260, height=83)
        panel.pack(side="left", padx=(0, 12))
        panel.pack_propagate(False)
        tk.Label(panel, text=heading, bg="white", fg="#526477", font=("Segoe UI", 9)).pack(pady=(12, 4))
        label = tk.Label(panel, text="—", bg="white", fg=color, font=("Segoe UI", 17, "bold"))
        label.pack()
        return label

    def reload(self):
        if not self.repo:
            messagebox.showwarning("Ayar gerekli", "Önce Netsis bağlantı ayarlarını tanımlayın.")
            return
        if self.pending and not messagebox.askyesno(
            "Bekleyen değişiklikler", "Önizlemedeki değişiklikler silinecek. Devam edilsin mi?"
        ):
            return
        self.status.set("Netsis stok kartları okunuyor...")
        self.root.update_idletasks()
        try:
            stocks = self.repo.load_stocks()
        except Exception as exc:
            self.status.set("SQL okuma başarısız.")
            messagebox.showerror("Netsis bağlantı hatası", str(exc))
            return
        self.pending.clear()
        self.stocks = {s.code: s for s in stocks}
        values = sorted({s.group for s in stocks if s.group})
        self.group_box.configure(values=["Tümü"] + values)
        if self.group.get() not in values:
            self.group.set("Tümü")
        self.refresh()
        self.status.set(f"Netsis bağlantısı başarılı. {len(stocks):,} stok kartı yüklendi. "
                        + ("Yazma yetkisi açık." if self.settings.write_enabled else "Salt okunur."))

    def filtered(self) -> list[Stock]:
        query = self.search.get().strip().casefold()
        code1 = self.code1.get().strip().casefold()
        code2 = self.code2.get().strip().casefold()
        group = self.group.get()
        condition = self.condition.get()
        result = []
        for s in self.stocks.values():
            if query and not any(query in item.casefold() for item in
                                 (s.code, s.name, s.barcode1, s.barcode2, s.barcode3)):
                continue
            if code1 and code1 not in s.code1.casefold():
                continue
            if code2 and code2 not in s.code2.casefold():
                continue
            if group != "Tümü" and s.group != group:
                continue
            margin = profit_margin(s.purchase, s.sale)
            markup = profit_markup(s.purchase, s.sale)
            matches = {
                "Alış 0": s.purchase == 0,
                "Satış 0": s.sale == 0,
                "Zarar": s.sale < s.purchase,
                "Marj <%20": margin is not None and margin < 20,
                "Maliyet kârı >= %100": markup is not None and markup >= 100,
            }
            if condition != "Tümü" and not matches.get(condition, True):
                continue
            result.append(s)
        return result

    def refresh(self):
        if not hasattr(self, "tree"):
            return
        selected_codes = {self.tree.item(i)["values"][0] for i in self.tree.selection()}
        stocks = self.filtered()
        self.visible_codes = [s.code for s in stocks]
        self.tree.delete(*self.tree.get_children())
        losses, margins = 0, []
        for s in stocks:
            if s.sale < s.purchase:
                losses += 1
            margin = profit_margin(s.purchase, s.sale)
            if margin is not None:
                margins.append(margin)
        for s in stocks[:MAX_VISIBLE]:
            ch = self.pending.get(s.code)
            purchase = ch.new_purchase if ch else s.purchase
            sale = ch.new_sale if ch else s.sale
            markup = profit_markup(s.purchase, s.sale)
            margin = profit_margin(s.purchase, s.sale)
            tags = ("pending",) if ch else ("loss",) if s.sale < s.purchase else ()
            self.tree.insert("", "end", iid=s.code, tags=tags, values=(
                s.code, s.name, s.group, s.code1, s.code2, fmt(s.purchase),
                fmt(s.sale), fmt(markup), fmt(margin),
                fmt(purchase), fmt(sale),
            ))
        for code in selected_codes:
            if self.tree.exists(code):
                self.tree.selection_add(code)
        self.total_label.configure(text=f"{len(stocks):,}")
        self.loss_label.configure(text=f"{losses:,}")
        self.pending_label.configure(text=f"{len(self.pending):,}")
        average = sum(margins, Decimal("0")) / len(margins) if margins else None
        self.avg_margin_label.configure(text=fmt(average))
        if len(stocks) > MAX_VISIBLE:
            self.status.set(f"{len(stocks):,} eşleşme var; ilk {MAX_VISIBLE:,} ürün gösteriliyor. "
                            "Daha dar bir filtre uygulayın.")

    def preview_selected(self):
        selected = self.tree.selection()
        if not selected:
            messagebox.showinfo("Seçim gerekli", "Önizlemek için bir veya daha fazla ürün seçiniz.")
            return
        try:
            proposed = {}
            for code in selected:
                s = self.stocks[code]
                change = propose_change(s, self.purchase_pct.get(), self.sale_pct.get(),
                                        self.round_sale.get())
                proposed[code] = change
        except ValueError as exc:
            messagebox.showerror("Geçersiz oran", str(exc))
            return
        for code, change in proposed.items():
            if change is None:
                self.pending.pop(code, None)
            else:
                self.pending[code] = change
        self.refresh()
        self.status.set(f"{len(self.pending):,} stok için önizleme hazır. SQL'e henüz yazılmadı.")

    def clear_pending(self):
        self.pending.clear()
        self.refresh()
        self.status.set("Önizleme temizlendi, Netsis verisi değiştirilmedi.")

    def save(self):
        if not self.repo or not self.settings.write_enabled:
            messagebox.showwarning("Salt okunur", "SQL yazma ayarı etkin değil.")
            return
        if not self.pending:
            messagebox.showinfo("Değişiklik yok", "Önce seçili ürünlerde fiyat önizlemesi oluşturun.")
            return
        changes = list(self.pending.values())
        examples = "\n".join(
            f"{ch.code}: {fmt(ch.old_sale)} → {fmt(ch.new_sale)} TL"
            for ch in changes[:8]
        )
        if len(changes) > 8:
            examples += f"\n... ve {len(changes)-8} stok daha"
        confirmation = (
            f"{len(changes)} stok kartının ALIŞ_FIAT1 / SATIS_FIAT1 alanları değişecek.\n\n"
            f"Satış fiyatı örnekleri:\n{examples}\n\n"
            "Bu işlem gerçek Netsis veritabanına yazılacaktır. Onaylıyor musunuz?"
        )
        if not messagebox.askyesno("NETSİS SQL KAYIT ONAYI", confirmation, icon="warning"):
            return
        try:
            count = self.repo.save_changes(changes)
        except Exception as exc:
            messagebox.showerror("Kayıt tamamlanamadı", str(exc))
            self.status.set("Kayıt sonucu kontrol edilmeli; hata rapor edildi.")
            return
        self.pending.clear()
        messagebox.showinfo("Kayıt başarılı", f"{count} ürün Netsis'te güncellendi.")
        self.reload()


def main():
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        pass
    root = tk.Tk()
    StockControlApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
