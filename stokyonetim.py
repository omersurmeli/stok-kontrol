import tkinter as tk
from tkinter import ttk, messagebox
import pandas as pd
import pyodbc
import math

# --- SQL BAĞLANTI AYARLARI ---
SERVER = 'yavaslarsrv'
DATABASE = 'YAVASLAR2026'
CONN_STR = f"DRIVER={{ODBC Driver 17 for SQL Server}};SERVER={SERVER};DATABASE={DATABASE};UID=sa;PWD=SAPASS;"

class YavaslarApp:
    def __init__(self, root):
        self.root = root
        self.root.title("YAVAŞLAR 2026 | Profesyonel Stok Yönetimi V151")
        self.root.geometry("1600x900")
        
        self.full_df = pd.DataFrame()
        self.f_vars = {k: tk.StringVar() for k in ['key', 'kod1', 'kod2']}
        self.arayuz_hazirla()
        self.verileri_yukle()

    def arayuz_hazirla(self):
        # --- MODÜL 1: DİNAMİK DASHBOARD ---
        dash = tk.Frame(self.root, bg="#f8f9fa", pady=15, relief="flat")
        dash.pack(fill="x", padx=15, pady=5)
        
        # Dashboard Finansal Kartlar
        self.lbl_total = self.create_card(dash, "Toplam Ürün", "#1976d2")
        self.lbl_alis_top = self.create_card(dash, "Filtreli Alış Top.", "#d32f2f")
        self.lbl_pot_kar = self.create_card(dash, "Potansiyel Kar", "#388e3c")
        
        # Modül 1 Kontrol Butonları (Sağa Sabitlendi)
        btn_container = tk.Frame(dash, bg="#f8f9fa")
        btn_container.pack(side="right", padx=20)
        
        tk.Button(btn_container, text="📊 KAR ANALİZİ", bg="#ef6c00", fg="white", 
                  font=("Segoe UI", 9, "bold"), width=15, height=2, command=self.pencere_kar_analizi).pack(side="right", padx=5)
        
        tk.Button(btn_container, text="🔄 VERİLERİ YENİLE", bg="#455a64", fg="white", 
                  font=("Segoe UI", 9, "bold"), width=15, height=2, command=self.verileri_yukle).pack(side="right", padx=5)

        # --- MODÜL 2: GELİŞMİŞ FİLTRE & REHBER ---
        f_box = tk.LabelFrame(self.root, text=" 🔍 MODÜL 2: Gelişmiş Filtreler (Rehber İçin Kutucuğa Çift Tıklayın) ", bg="white", padx=15, pady=10)
        f_box.pack(fill="x", padx=20, pady=5)
        
        tk.Label(f_box, text="Stok/Barkod:", bg="white").grid(row=0, column=0)
        tk.Entry(f_box, textvariable=self.f_vars['key'], width=20).grid(row=0, column=1, padx=5)
        
        tk.Label(f_box, text="Grup:", bg="white").grid(row=0, column=2, padx=5)
        self.cb_grup = ttk.Combobox(f_box, width=15); self.cb_grup.grid(row=0, column=3, padx=5)
        
        # Kod1 & Kod2 Rehber Alanları
        tk.Label(f_box, text="Kod1 (Raf):", bg="white").grid(row=0, column=4, padx=5)
        e1 = tk.Entry(f_box, textvariable=self.f_vars['kod1'], width=12, bg="#fffde7")
        e1.grid(row=0, column=5, padx=5); e1.bind("<Double-Button-1>", lambda e: self.rehber_ac("KOD_1", self.f_vars['kod1']))

        tk.Label(f_box, text="Kod2 (Özel):", bg="white").grid(row=0, column=6, padx=5)
        e2 = tk.Entry(f_box, textvariable=self.f_vars['kod2'], width=12, bg="#fffde7")
        e2.grid(row=0, column=7, padx=5); e2.bind("<Double-Button-1>", lambda e: self.rehber_ac("KOD_2", self.f_vars['kod2']))

        for v in self.f_vars.values(): v.trace_add("write", lambda *a: self.akilli_filtrele())
        self.cb_grup.bind("<<ComboboxSelected>>", lambda e: self.akilli_filtrele())

        # --- MODÜL 3: TOPLU İŞLEM PANELİ ---
        # Sadece seçili ürünlere müdahale eder
        edit_box = tk.LabelFrame(self.root, text=" ⚙️ MODÜL 3: Fiyat Güncelleme (Mavi Seçili Ürünler) ", bg="#e3f2fd", padx=15, pady=10)
        edit_box.pack(fill="x", padx=20, pady=5)
        
        tk.Label(edit_box, text="Alış %:", bg="#e3f2fd").pack(side="left")
        self.ent_ao = tk.Entry(edit_box, width=5); self.ent_ao.insert(0, "0"); self.ent_ao.pack(side="left", padx=5)
        tk.Label(edit_box, text="Satış %:", bg="#e3f2fd").pack(side="left")
        self.ent_so = tk.Entry(edit_box, width=5); self.ent_so.insert(0, "0"); self.ent_so.pack(side="left", padx=5)
        
        self.round_var = tk.BooleanVar(value=True)
        tk.Checkbutton(edit_box, text="0.90'a Yuvarla", variable=self.round_var, bg="#e3f2fd").pack(side="left", padx=10)

        tk.Button(edit_box, text="💾 MİKRO'YA YAZ", bg="#1565c0", fg="white", font=("Segoe UI", 9, "bold"), width=15, command=self.sql_kaydet).pack(side="right", padx=5)
        tk.Button(edit_box, text="⚡ ÖNİZLEME UYGULA", bg="#2e7d32", fg="white", font=("Segoe UI", 9, "bold"), width=15, command=self.toplu_uygula).pack(side="right", padx=5)

        # --- TABLO ALANI ---
        self.main_cols = ["STOK KODU", "STOK ADI", "GRUP", "KOD1", "KOD2", "ALIS FIYATI", "SATIS 1", "KAR %", "YENİ ALIS", "YENİ SATIŞ"]
        m_view = tk.Frame(self.root); m_view.pack(fill="both", expand=True, padx=20, pady=10)
        self.tree = ttk.Treeview(m_view, columns=self.main_cols, show="headings", selectmode="extended")
        for c in self.main_cols: self.tree.heading(c, text=c); self.tree.column(c, width=100, anchor="center")
        self.tree.column("STOK ADI", width=350, anchor="w"); self.tree.pack(fill="both", expand=True)

    def create_card(self, parent, text, color):
        f = tk.Frame(parent, bg="white", highlightbackground="#ddd", highlightthickness=1, width=200, height=70)
        f.pack(side="left", padx=15); f.pack_propagate(False)
        tk.Label(f, text=text, bg="white", fg="#666", font=("Segoe UI", 8, "bold")).pack(pady=5)
        l = tk.Label(f, text="0", bg="white", fg=color, font=("Segoe UI", 12, "bold")); l.pack(); return l

    def verileri_yukle(self):
        try:
            conn = pyodbc.connect(CONN_STR)
            q = "SELECT STOK_KODU, STOK_ADI, ISNULL(GRUP_KODU,''), ISNULL(KOD_1,''), ISNULL(KOD_2,''), CAST(ALIS_FIAT1 AS FLOAT), CAST(SATIS_FIAT1 AS FLOAT) FROM TBLSTSABIT"
            df = pd.read_sql(q, conn); conn.close()
            # nan değerleri 0 ve boşluk ile temizle
            df.fillna({'ALIS_FIAT1': 0, 'SATIS_FIAT1': 0}, inplace=True)
            self.full_df = df
            self.cb_grup['values'] = ["HEPSİ"] + sorted(self.full_df.iloc[:,2].unique().astype(str).tolist())
            self.akilli_filtrele()
        except Exception as e: messagebox.showerror("Hata", f"SQL Bağlantı Sorunu: {e}")

    def akilli_filtrele(self, *args):
        df = self.full_df.copy()
        k, g = self.f_vars['key'].get().upper(), self.cb_grup.get()
        k1, k2 = self.f_vars['kod1'].get().upper(), self.f_vars['kod2'].get().upper()
        
        if k: df = df[df.iloc[:,1].str.contains(k, na=False) | df.iloc[:,0].str.contains(k, na=False)]
        if g and g != "HEPSİ": df = df[df.iloc[:,2] == g]
        if k1: df = df[df.iloc[:,3].str.contains(k1, na=False)]
        if k2: df = df[df.iloc[:,4].str.contains(k2, na=False)]
        
        self.tree.delete(*self.tree.get_children())
        t_alis, t_satis = 0, 0
        
        for _, r in df.head(1500).iterrows():
            a, s = float(r[5] or 0), float(r[6] or 0)
            t_alis += a; t_satis += s
            kar = ((s-a)/a*100) if a>0 else 0
            self.tree.insert("", "end", values=(r[0], r[1], r[2], r[3], r[4], f"{a:.2f}", f"{s:.2f}", f"%{kar:.2f}", f"{a:.2f}", f"{s:.2f}"))
        
        # nan ₺ hatası düzeltildi, Dashboard güncellendi
        self.lbl_total.config(text=f"{len(df):,}")
        self.lbl_alis_top.config(text=f"{t_alis:,.2f} ₺")
        self.lbl_pot_kar.config(text=f"{(t_satis - t_alis):,.2f} ₺")

    def rehber_ac(self, kolon, hedef_var):
        """Modül 2 Rehber Sistemi"""
        r_win = tk.Toplevel(self.root); r_win.title("Seçim Rehberi"); r_win.geometry("350x450"); r_win.grab_set()
        lb = tk.Listbox(r_win, font=("Segoe UI", 10))
        lb.pack(fill="both", expand=True, padx=10, pady=10)
        idx = 3 if kolon == "KOD_1" else 4
        for m in sorted(self.full_df.iloc[:, idx].unique().astype(str).tolist()):
            if m != "nan" and m.strip(): lb.insert("end", m)
        def sec(): hedef_var.set(lb.get(lb.curselection())); r_win.destroy()
        tk.Button(r_win, text="SEÇ VE UYGULA", bg="#1976d2", fg="white", command=sec).pack(pady=5)
        lb.bind("<Double-Button-1>", lambda e: sec())

    def sql_kaydet(self):
        """Hata dökümü veren güvenli kayıt"""
        if not messagebox.askyesno("Onay", "Fiyatlar Mikro'ya yazılsın mı?"): return
        try:
            conn = pyodbc.connect(CONN_STR); cur = conn.cursor()
            ok, err = 0, 0
            for i in self.tree.get_children():
                v = self.tree.item(i)['values']
                try:
                    cur.execute("UPDATE TBLSTSABIT SET ALIS_FIAT1=CAST(? AS FLOAT), SATIS_FIAT1=CAST(? AS FLOAT) WHERE STOK_KODU=?", (float(v[8]), float(v[9]), str(v[0])))
                    ok += 1
                except: err += 1
            conn.commit(); conn.close(); self.verileri_yukle()
            messagebox.showinfo("Sonuç", f"✅ {ok} Ürün güncellendi.\n❌ {err} Hata oluştu.")
        except Exception as e: messagebox.showerror("Hata", str(e))

    def toplu_uygula(self):
        selected = self.tree.selection()
        if not selected: return
        try:
            ao = float(self.ent_ao.get() or 0)/100; so = float(self.ent_so.get() or 0)/100
            for i in selected:
                v = list(self.tree.item(i)['values'])
                ya = float(v[5]) * (1 + ao); ys = float(v[6]) * (1 + so)
                if self.round_var.get(): ys = math.floor(ys) + 0.90
                v[8], v[9] = f"{ya:.2f}", f"{ys:.2f}"
                self.tree.item(i, values=v)
        except: pass

    def pencere_kar_analizi(self):
        k_win = tk.Toplevel(self.root); k_win.title("📊 Kar Analizi")
        kt = ttk.Treeview(k_win, columns=("K","AD","KR"), show="headings")
        kt.heading("K", text="KOD"); kt.heading("AD", text="STOK ADI"); kt.heading("KR", text="KAR %")
        kt.pack(fill="both", expand=True, padx=10, pady=10)
        for i in self.tree.get_children():
            v = self.tree.item(i)['values']
            if float(v[7].replace('%','')) < 20: kt.insert("", "end", values=(v[0], v[1], v[7]))

if __name__ == "__main__":
    root = tk.Tk(); app = YavaslarApp(root); root.mainloop()