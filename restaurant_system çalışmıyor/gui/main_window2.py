"""
Ana GUI Penceresi - RestaurantSystemV7 Sınıfı
Orijinal koddan modüler yapıya uyarlanmıştır
"""

# Standart kütüphaneler
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, simpledialog
import pandas as pd
from functools import partial
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
import time

# Proje modülleri
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import find_excel_file, PAYMENT_TYPES
from datetime import datetime, timedelta
import calendar
import os
import threading
import json
import traceback

# Proje modülleri - Dinamik path ekleme
import sys
module_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if module_path not in sys.path:
    sys.path.insert(0, module_path)

# Config ve modüller
from config import *
from models.data_models import (
    menu, tables, table_widgets, paket_masalar, selected_table_name,
    table_people, table_notes, active_orders, table_active_order_id,
    table_ready_baseline, pending_payment_method
)
from utils.formatters import parse_float, format_currency
from utils.helpers import (
    safe_float_input, get_local_ip, find_column, get_recent_avg_price,
    normalize_yemek_cols, normalize_urunler_cols
)
from utils.excel_handler import (
    safe_excel_write, safe_excel_append, safe_excel_replace_meal,
    create_sample_excels
)

# API import
from api.kitchen_api import start_kitchen_server

# Winsound kontrolü
if WINSOUND_AVAILABLE:
    import winsound

# Global app referansı
app = None


class RestaurantSystemV7:
    
    # =========================================================================
    # V7 YENİLİK: RENKLİ SEKMELER
    # =========================================================================
    
    def setup_colored_notebook_style(self):
        """Sekmeler için renkli stil ayarları"""
        style = ttk.Style()
        
        # Genel tema ayarla
        try:
            available_themes = style.theme_names()
            if 'clam' in available_themes:
                style.theme_use('clam')
            elif 'default' in available_themes:
                style.theme_use('default')
        except:
            pass
        
        # Sekme renkleri tanımla
        style.configure('Red.TNotebook.Tab', background='#ffcccb', foreground='#8B0000')      # Sipariş - Açık kırmızı
        style.configure('Green.TNotebook.Tab', background='#c8e6c9', foreground='#2E7D32')    # Maliyet - Açık yeşil  
        style.configure('Blue.TNotebook.Tab', background='#bbdefb', foreground='#1565C0')     # Planlama - Açık mavi
        style.configure('Orange.TNotebook.Tab', background='#ffe0b2', foreground='#E65100')   # Ciro - Açık turuncu
        style.configure('Purple.TNotebook.Tab', background='#e1bee7', foreground='#6A1B9A')   # Mutfak - Açık mor
        
        # Seçili sekme stilleri
        style.map('Red.TNotebook.Tab', background=[('selected', '#ff8a80')])
        style.map('Green.TNotebook.Tab', background=[('selected', '#a5d6a7')])
        style.map('Blue.TNotebook.Tab', background=[('selected', '#90caf9')])
        style.map('Orange.TNotebook.Tab', background=[('selected', '#ffcc02')])
        style.map('Purple.TNotebook.Tab', background=[('selected', '#ce93d8')])
        
        try:
            print("Renkli sekme stilleri hazırlandı!")
        except Exception:
            pass
    def __init__(self, root):
        self.root = root
        try:
            self.root.title("Tencere Tava Sistemi v8.0 Enhanced - Kapsamlı İyileştirmeler")
        except Exception:
            self.root.title("Tencere Tava Sistemi")
        self.root.geometry("1400x900")
        
        global app
        app = self
        
        # API modülüne de app referansını aktar
        import api.kitchen_api
        api.kitchen_api.app = self
        
        # Global değişkenleri instance variable olarak bağla (API'den erişim için)
        self.table_ready_baseline = table_ready_baseline
        self.table_active_order_id = table_active_order_id
        self.active_orders = active_orders
        
        # Günlük planlama verileri - önce bunları tanımla
        self.selected_days = set()
        self.day_widgets = {}
        
        # Excel dosya yollarını yükle
        self.load_excel_paths()
        
        # Veri yükleme
        self.load_menu_cache()
        self.load_cost_dataframes()
        
        # GUI oluşturma
        self.setup_colored_notebook_style()  # V7 YENİLİK: Renkli sekmeler
        self.create_main_interface()
        
        # Günlük planlama verilerini yükle
        self.load_daily_planning_data()
        
        # Ciro analizini güncelle
        if hasattr(self, 'ciro_file_path') and os.path.exists(self.ciro_file_path):
            try:
                self.apply_revenue_filter()
            except:
                self.update_revenue_label()
        
        # Mutfak sunucusunu başlat
        try:
            threading.Thread(target=start_kitchen_server, daemon=True).start()
            print(f"Mutfak ekranı yayında: http://localhost:{KITCHEN_PORT}")
        except Exception:
            pass

    # =========================================================================
    # DOSYA İŞLEMLERİ
    # =========================================================================
    
    def load_menu_cache(self):
        """Menü önbelleğini yükle"""
        last_path = self.load_last_path()
        if last_path and os.path.exists(last_path):
            try:
                if last_path.lower().endswith(".csv"):
                    df = pd.read_csv(last_path)
                else:
                    df = pd.read_excel(last_path, engine="openpyxl")
                menu.clear()
                for _, r in df.iterrows():
                    try:
                        menu[str(r.iloc[0])] = float(r.iloc[1])
                    except:
                        continue
                return
            except Exception:
                pass
        
        if os.path.exists(MENU_CACHE):
            try:
                df = pd.read_excel(MENU_CACHE, engine="openpyxl")
                menu.clear()
                if "Ürün" in df.columns and "Fiyat" in df.columns:
                    for _, r in df.iterrows():
                        try:
                            menu[str(r["Ürün"])] = float(r["Fiyat"])
                        except:
                            continue
                else:
                    for _, r in df.iterrows():
                        try:
                            menu[str(r.iloc[0])] = float(r.iloc[1])
                        except:
                            continue
            except Exception:
                pass

    def load_cost_dataframes(self):
        """Maliyet hesaplama için veri yükle"""
        # Excel dosya yollarını yükle (esnek arama ile)
        self.load_excel_paths()
        
        # Dosyaları yeniden kontrol et (user_input_files klasörü de dahil)
        self.yemek_file_path = find_excel_file("yemekler.xlsx")
        self.urun_file_path = find_excel_file("urunler.xlsx")
        
        # Eksik dosyalar için örnek oluştur
        missing = []
        if not os.path.exists(self.yemek_file_path):
            missing.append("yemekler.xlsx")
        if not os.path.exists(self.urun_file_path):
            missing.append("urunler.xlsx")
        if missing:
            create_sample_excels(BASE_DIR)
            messagebox.showinfo("Örnek oluşturuldu", f"Bulunmayan dosyalar için örnekler oluşturuldu: {', '.join(missing)}\nLütfen excel dosyalarını bu klasöre koyun: {BASE_DIR}")

        try:
            self.yemek_df = pd.read_excel(self.yemek_file_path, engine="openpyxl")
            self.yemek_df = normalize_yemek_cols(self.yemek_df)
            
            # V6: Porsiyon sütunu kontrolü ve ekleme
            if "porsiyon" not in self.yemek_df.columns:
                self.yemek_df["porsiyon"] = 1  # Varsayılan 1 porsiyon
                self.yemek_df.to_excel(self.yemek_file_path, index=False)
                print("Porsiyon sütunu eklendi ve kaydedildi.")
            
            print("Yemekler yüklendi. satır:", len(self.yemek_df))
        except Exception as e:
            print("Yemek excel okunamadı:", e)
            self.yemek_df = pd.DataFrame(columns=["yemek adı","porsiyon adt","ürün","miktar","porsiyon"])

        try:
            self.urun_df = pd.read_excel(self.urun_file_path, engine="openpyxl")
            self.urun_df = normalize_urunler_cols(self.urun_df)
            print("Ürünler yüklendi. satır:", len(self.urun_df))
        except Exception as e:
            print("Ürün excel okunamadı:", e)
            self.urun_df = pd.DataFrame(columns=["Ürün Adı","Tarih","Miktar","Alış Fiyatı (TL)"])

    def load_excel_paths(self):
        """Excel dosya yollarını yükle"""
        try:
            if os.path.exists(EXCEL_PATHS_CONFIG):
                with open(EXCEL_PATHS_CONFIG, "r", encoding="utf-8") as f:
                    lines = f.readlines()
                    if len(lines) >= 4:
                        self.yemek_file_path = lines[0].strip()
                        self.urun_file_path = lines[1].strip()
                        self.order_file_path = lines[2].strip()
                        self.ciro_file_path = lines[3].strip()
                        return
                    elif len(lines) >= 3:
                        self.yemek_file_path = lines[0].strip()
                        self.urun_file_path = lines[1].strip()
                        self.order_file_path = lines[2].strip()
                        self.ciro_file_path = ORDER_FILE  # Varsayılan olarak sipariş dosyası
                        return
        except Exception:
            pass
        
        # Varsayılan yollar
        self.yemek_file_path = YEMEK_FILE
        self.urun_file_path = URUN_FILE
        self.order_file_path = ORDER_FILE
        self.ciro_file_path = ORDER_FILE

    def save_excel_paths(self):
        """Excel dosya yollarını kaydet"""
        try:
            with open(EXCEL_PATHS_CONFIG, "w", encoding="utf-8") as f:
                f.write(f"{self.yemek_file_path}\n")
                f.write(f"{self.urun_file_path}\n")
                f.write(f"{self.order_file_path}\n")
                f.write(f"{self.ciro_file_path}\n")
        except Exception as e:
            print(f"Excel yolları kaydedilemedi: {e}")

    def choose_excel_files(self):
        """Excel dosyalarını seç"""
        # Yemek dosyası seç
        yemek_path = filedialog.askopenfilename(
            title="Yemekler Excel Dosyasını Seçin",
            filetypes=[("Excel files", "*.xlsx"), ("All files", "*.*")],
            initialdir=BASE_DIR
        )
        if not yemek_path:
            return
        
        # Ürün dosyası seç
        urun_path = filedialog.askopenfilename(
            title="Ürünler Excel Dosyasını Seçin", 
            filetypes=[("Excel files", "*.xlsx"), ("All files", "*.*")],
            initialdir=BASE_DIR
        )
        if not urun_path:
            return
        
        # Sipariş dosyası seç
        order_path = filedialog.askopenfilename(
            title="Siparişler Excel Dosyasını Seçin",
            filetypes=[("Excel files", "*.xlsx"), ("All files", "*.*")],
            initialdir=BASE_DIR
        )
        if not order_path:
            return
        
        # Yolları kaydet
        self.yemek_file_path = yemek_path
        self.urun_file_path = urun_path
        self.order_file_path = order_path
        self.save_excel_paths()
        
        # Verileri yeniden yükle
        self.load_cost_dataframes()
        self.populate_meals()
        self.update_revenue_label()
        
        messagebox.showinfo("Başarılı", "Excel dosya yolları kaydedildi ve veriler yüklendi!")

    def choose_ciro_excel_file(self):
        """Ciro analizi için Excel dosyasını seç"""
        ciro_path = filedialog.askopenfilename(
            title="Ciro Analizi Excel Dosyasını Seçin",
            filetypes=[("Excel files", "*.xlsx"), ("All files", "*.*")],
            initialdir=BASE_DIR
        )
        if not ciro_path:
            return
        
        # Ciro dosya yolunu kaydet
        self.ciro_file_path = ciro_path
        self.save_excel_paths()
        
        # Ciro analizini güncelle
        self.apply_revenue_filter()
        
        messagebox.showinfo("Başarılı", "Ciro Excel dosyası kaydedildi ve veriler yüklendi!")

    def load_daily_planning_data(self):
        """Günlük planlama verilerini yükle"""
        if not os.path.exists(GUNLUK_FILE):
            return
        
        try:
            # Bugünün tarihini al
            today = datetime.now().date()
            today_str = f"{today.day}/{today.month}/{today.year}"
            
            # Excel sheet'ini kontrol et
            try:
                df_daily = pd.read_excel(GUNLUK_FILE, sheet_name='Günlük Yemekler', engine="openpyxl")
            except ValueError as sheet_error:
                if 'Worksheet named' in str(sheet_error) and 'not found' in str(sheet_error):
                    print(f"INFO: 'Günlük Yemekler' sheet'i bulunamadı - henüz oluşturulmamış. Gelecek kayıtlar için hazır.")
                    return
                else:
                    raise sheet_error
            
            # Bugüne ait kayıtları filtrele
            today_meals = df_daily[df_daily['Gün'] == today_str]
            
            if not today_meals.empty:
                # Bugünün tarihini seçili günlere ekle
                self.selected_days.add(today)
                
                # Günlük planlama arayüzü henüz oluşturulmadıysa çık
                if not hasattr(self, 'day_widgets') or today not in self.day_widgets:
                    # Veriyi geçici olarak sakla, arayüz hazır olunca yükleyeceğiz
                    self.pending_daily_data = today_meals
                    return
                
                # Listbox'a yemekleri ekle
                if today in self.day_widgets:
                    lb = self.day_widgets[today]["listbox"]
                    for _, row in today_meals.iterrows():
                        meal_line = f"{row['Yemek Adı']} x{row['Porsiyon']} = {row['Toplam Maliyet (TL)']} TL"
                        lb.insert(tk.END, meal_line)
                    
                    # Özeti güncelle
                    self.update_planning_summary()
                    
                print(f"Bugünün günlük planlama verileri yüklendi: {len(today_meals)} yemek")
        except Exception as e:
            print(f"Günlük planlama verileri yüklenemedi: {e}")

    def save_excel_changes(self, file_path, dataframe, operation="değişiklik"):
        """Excel dosyasına değişiklikleri gerçek zamanlı kaydet"""
        try:
            dataframe.to_excel(file_path, index=False, engine='openpyxl')
            print(f"Excel {operation} kaydedildi: {file_path}")
            return True
        except Exception as e:
            print(f"Excel kaydetme hatası: {e}")
            messagebox.showerror("Kaydetme Hatası", f"Excel dosyası kaydedilemedi:\n{e}")
            return False

    def save_last_path(self, path):
        """Son seçilen dosya yolunu kaydet"""
        try:
            with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                f.write(path)
        except Exception:
            pass

    def load_last_path(self):
        """Son seçilen dosya yolunu yükle"""
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                    path = f.read().strip()
                    if os.path.exists(path):
                        return path
            except Exception:
                return None
        return None
    
    # =========================================================================
    # YARDIMCI METOTLAR (Performans ve Güvenlik için Sınıf İçi Versiyonu)
    # =========================================================================
    
    def get_previous_purchase_price(self, product_name, current_date=None):
        """
        Satın alma listesi yenileme (refresh_purchase_list) sırasında self.urun_df kullanarak disk erişimi tekrarını önler.
        """
        try:
            df = self.urun_df.copy() # Sınıf değişkeni üzerinden kopyala
            
            name_col = find_column(df, ["Ürün Adı", "ürün", "urun", "product"])
            if name_col is None:
                return None
            
            product_rows = df[df[name_col].astype(str).str.strip().str.lower() == product_name.strip().lower()].copy()
            if product_rows.empty:
                return None
            
            date_col = find_column(df, ["Tarih", "tarih", "Date", "date"])
            
            if date_col:
                product_rows[date_col] = pd.to_datetime(product_rows[date_col], errors='coerce')
                product_rows = product_rows.sort_values(date_col, ascending=False)
                
                if pd.notna(current_date):
                    if isinstance(current_date, str):
                        current_date = pd.to_datetime(current_date)
                    
                    # Bu tarihten önceki kayıtları filtrele
                    previous_rows = product_rows[product_rows[date_col] < current_date].copy()
                else:
                    # current_date yoksa, en son kaydı al
                    previous_rows = product_rows.copy()
                
                if not previous_rows.empty:
                    last_row = previous_rows.iloc[0]
                    
                    price_col = find_column(df, ["Alış Fiyatı (TL)", "alış fiyatı", "fiyat", "price", "toplam"])
                    miktar_col = find_column(df, ["Miktar", "miktar", "adet", "amount"])

                    last_price = last_row.get(price_col)
                    last_quantity = last_row.get(miktar_col, 1)
                    last_date = last_row.get(date_col, None)
                    
                    return {
                        'price': parse_float(last_price) if pd.notna(last_price) else None,
                        'quantity': parse_float(last_quantity) if pd.notna(last_quantity) else 1,
                        'date': last_date
                    }
            
            return None
        except Exception as e:
            print(f"[DEBUG] get_previous_purchase_price hata: {e}")
            return None

    # =========================================================================
    # ANA ARAYÜZ OLUŞTURMA
    # =========================================================================
    
    def create_main_interface(self):
        """Ana arayüzü oluştur"""
        # Stil ayarları
        style = ttk.Style()
        try:
            style.theme_use(style.theme_use())
        except Exception:
            pass
        style.configure("Treeview", rowheight=28, font=("Arial", 12))
        style.configure("Treeview.Heading", font=("Arial", 12, "bold"))
        
        # Üst bilgi çubuğu
        info_bar = tk.Frame(self.root, bd=0, padx=8, pady=4)
        info_bar.pack(side=tk.TOP, fill=tk.X)
        ip_label = tk.Label(info_bar, text=f"Mutfak URL: http://{get_local_ip()}:{KITCHEN_PORT}", font=("Arial", 10, "bold"))
        ip_label.pack(side=tk.LEFT)
        
        # Ana notebook
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill=tk.BOTH, expand=True)
        
        # Sekmeleri oluştur
        self.create_restaurant_tab()
        self.create_cost_tab()
        self.create_planning_tab()
        self.create_revenue_tab()
        self.create_purchase_tab()  # V8 YENİLİK: Satın alma sekmesi
        self.create_satis_maliyet_tab()

    def create_restaurant_tab(self):
        """Restoran yönetimi sekmesi - KIRMIZI"""
        restaurant_tab = tk.Frame(self.notebook, bg="#fff2e6")
        self.notebook.add(restaurant_tab, text="🍽️ Restoran & Masalar")
        
        # V7 YENİLİK: Renkli sekme stili uygula
        tab_index = len(self.notebook.tabs()) - 1
        try:
            self.notebook.tab(tab_index, style='Red.TNotebook.Tab')
        except:
            pass  # Stil uygulanamadıysa devam et
        
        # Sol panel - Menü
        menu_frame = tk.Frame(restaurant_tab, bd=2, relief=tk.RIDGE, padx=10, pady=10, bg="#fff2e6")
        menu_frame.pack(side=tk.LEFT, fill=tk.Y, padx=10, pady=10)
        tk.Label(menu_frame, text="Ürünler", font=("Arial", 18, "bold"), bg="#fff2e6", fg="#ff6600").pack(pady=6)
        
        # Arama alanı
        search_frame = tk.Frame(menu_frame, bg="#fff2e6")
        search_frame.pack(fill=tk.X, pady=4)
        tk.Label(search_frame, text="Ara:", bg="#fff2e6").pack(side=tk.LEFT, padx=4)
        self.search_var = tk.StringVar()
        search_entry = tk.Entry(search_frame, textvariable=self.search_var)
        search_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=4)
        search_entry.bind("<KeyRelease>", self.on_search_key)
        
        # Menü ağacı
        tree_container = tk.Frame(menu_frame)
        tree_container.pack(fill=tk.BOTH, expand=True)
        self.menu_tree = ttk.Treeview(tree_container, columns=("Ürün", "Fiyat"), show="headings", height=18, selectmode="extended")
        self.menu_tree.heading("Ürün", text="Ürün")
        self.menu_tree.heading("Fiyat", text="Fiyat (TL)")
        self.menu_tree.column("Fiyat", anchor="center", width=100)
        self.menu_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        tree_scroll = ttk.Scrollbar(tree_container, orient="vertical", command=self.menu_tree.yview)
        self.menu_tree.configure(yscrollcommand=tree_scroll.set)
        tree_scroll.pack(side=tk.LEFT, fill=tk.Y)
        
        # Menü butonları
        tk.Button(menu_frame, text="Az Versiyon Oluştur (Seçili)", command=self.create_az_versions, bg="#ffb300", fg="white").pack(fill=tk.X, pady=6)
        
        # V8 YENİLİK: Menü güncelleme butonu
        tk.Button(menu_frame, text="🔄 Menü Güncelle", command=self.refresh_menu_from_excel, bg="#28a745", fg="white", font=("Arial", 10, "bold")).pack(fill=tk.X, pady=6)
        
        # Sağ panel - Masalar
        right_side = tk.Frame(restaurant_tab)
        right_side.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        tables_frame = tk.Frame(right_side, bd=2, relief=tk.RIDGE, padx=10, pady=10, bg="#e6f2ff")
        tables_frame.pack(side=tk.TOP, fill=tk.BOTH, expand=True, pady=(0, 10))
        
        # Masa widget'larını oluştur (Bu metodun proxy'de geçersiz kılındığını unutmayın)
        self.create_table_widgets(tables_frame) 
        
        # Alt panel - Kontrol butonları ve Günlük Ciro (Günlük Ciro en alta sabitlenecek)
        self.create_control_buttons(right_side, restaurant_tab)
        
        # Menü ağacına çift tık olayı
        self.menu_tree.bind("<Double-1>", self.on_menu_double_click)
        
        # İlk güncellemeler
        self.update_menu_tree()

    # NOTE: create_table_widgets metodu proxy (main_window.py) tarafından geçersiz kılınmıştır.

    def create_control_buttons(self, parent, root_tab):
        """Kontrol butonlarını oluştur"""
        
        # --------------------------------------------------------------------------------
        # ÜST KONTROL BUTONLARI (2 SATIR HALİNDE)
        # --------------------------------------------------------------------------------
        
        # Tüm butonları içerecek ana çerçeve
        main_control_frame = tk.Frame(parent, bd=2, relief=tk.FLAT, padx=6, pady=8, bg="#f2f2f2")
        main_control_frame.pack(side=tk.TOP, fill=tk.X, pady=(8,0))

        # 1. SATIR BUTONLAR (Menü CRUD, Tüm Masalar)
        action_frame = tk.Frame(main_control_frame, bg="#f2f2f2")
        action_frame.pack(side=tk.TOP, fill=tk.X, pady=(0, 6))

        # Menü CRUD butonları
        tk.Button(action_frame, text="Ekle (Menü)", command=self.add_product, bg="#4caf50", fg="white").pack(side=tk.LEFT, padx=6, ipadx=6)
        tk.Button(action_frame, text="Düzenle (Menü)", command=self.edit_product, bg="#2196f3", fg="white").pack(side=tk.LEFT, padx=6, ipadx=6)
        tk.Button(action_frame, text="Sil (Menü)", command=self.delete_product, bg="#f44336", fg="white").pack(side=tk.LEFT, padx=6, ipadx=6)
        tk.Button(action_frame, text="Excel'den Yükle (Menü)", command=self.load_menu_from_excel, bg="#607d8b", fg="white").pack(side=tk.LEFT, padx=6, ipadx=6)
        tk.Button(action_frame, text="Tüm Masaları Öde", command=self.take_payment_for_all_ready_tables, bg="#9c27b0", fg="white").pack(side=tk.LEFT, padx=6, ipadx=6)
        tk.Button(action_frame, text="Tüm Masaları Temizle", command=self.clear_all_tables, bg="#d32f2f", fg="white").pack(side=tk.LEFT, padx=6, ipadx=6)
        
        # Seçili masa bilgisi
        self.selected_table_label = tk.Label(action_frame, text="Seçili Masa: Yok", bg="#f2f2f2", font=("Arial", 11, "bold"))
        self.selected_table_label.pack(side=tk.RIGHT, padx=8)

        # 2. SATIR BUTONLAR (Masa İşlemleri)
        btn_second_row = tk.Frame(main_control_frame, bg="#f2f2f2")
        btn_second_row.pack(side=tk.TOP, fill=tk.X, pady=(0, 6))
        
        tk.Button(btn_second_row, text="Seçili Ürünleri Seçili Masaya Ekle", command=self.add_selected_menu_to_chosen_table, bg="#4caf50", fg="white").pack(side=tk.LEFT, padx=6)
        
        # NOT: 'Seçili Masadan Çıkart' butonu artık her masanın kendi içinde.
        
        tk.Button(btn_second_row, text="Seçili Masayı Temizle", command=self.clear_selected_table, bg="#ff9800", fg="white").pack(side=tk.LEFT, padx=6)
        
        # Paket servisi seçimi
        self.restoran_var = tk.StringVar(value=restoranlar[0])
        tk.Label(btn_second_row, text="   Paket Servisi:", bg="#f2f2f2").pack(side=tk.LEFT)
        ttk.Combobox(btn_second_row, textvariable=self.restoran_var, values=restoranlar, width=16).pack(side=tk.LEFT, padx=6)
        
        # V8 YENİLİK: Güncel ciro ve günlük ciro etiketleri
        
        # V8 YENİLİK: Güncel ciro gösterimi
        self.selected_table_revenue_label = tk.Label(main_control_frame, text="0.00 TL", font=("Arial", 18, "bold"), bg="#f8d7da", fg="#721c24", padx=10, pady=6)
        self.selected_table_revenue_label.pack(side=tk.RIGHT, padx=8)
        
        # --------------------------------------------------------------------------------
        # GÜNLÜK CİRO YERLEŞİMİ (EKRANIN EN ALTINA SABİTLENDİ)
        # --------------------------------------------------------------------------------
        
        # root_tab argümanı Restoran Sekmesinin kendisidir (restaurant_tab)
        daily_revenue_frame = tk.Frame(root_tab, bg="#d1ecf1", bd=1, relief=tk.SOLID)
        daily_revenue_frame.pack(side=tk.BOTTOM, fill=tk.X, pady=5) 

        # Günlük Ciro Etiketi (Görünürlüğünü sağlamak için en sola yerleştirildi)
        self.daily_revenue_label = tk.Label(daily_revenue_frame, 
                                            text="Bugünkü Ciro: 0.00 TL", 
                                            font=("Arial", 14, "bold"), 
                                            bg="#d1ecf1", 
                                            fg="#0c5460", 
                                            padx=10, 
                                            pady=4)
        self.daily_revenue_label.pack(side=tk.LEFT, padx=10)

        # Ciro Güncelle butonu (Kontrol amaçlı)
        tk.Button(daily_revenue_frame, text="Ciroyu Güncelle", command=self.update_all_revenue, 
                  bg="#bdbdbd", font=("Arial", 10)).pack(side=tk.RIGHT, padx=10)
        
        # Günlük ciro (Menü Yanı) (ESKİ LABEL - uyumluluk için korundu)
        menu_daily_frame = tk.Frame(parent, bd=0, padx=6, pady=6, bg="#f7f7f7")
        menu_daily_frame.pack(side=tk.TOP, fill=tk.X, pady=6)
        self.menu_daily_ciro_label = tk.Label(menu_daily_frame, text="Günlük Ciro (----): 0.00 TL", font=("Arial", 12, "bold"), bg="#f7f7f7")
        self.menu_daily_ciro_label.pack(side=tk.LEFT, padx=6)
        tk.Button(menu_daily_frame, text="Güncelle", command=self.update_all_revenue, bg="#bdbdbd").pack(side=tk.LEFT, padx=6)
        
        # Günlük ciro güncelleyin
        self.update_all_revenue()

    # NOTE: create_table_widgets metodu proxy (main_window.py) tarafından geçersiz kılınmıştır.
    
    def create_cost_tab(self):
        """Maliyet takibi sekmesi"""
        cost_tab = tk.Frame(self.notebook, bg="#f0f8ff")
        self.notebook.add(cost_tab, text="💰 Maliyet Takibi")
        
        # Üst panel - Butonlar
        top_frame = tk.Frame(cost_tab)
        top_frame.pack(fill="x", pady=6)
        tk.Button(top_frame, text="📁 Excel Dosyalarını Seç", command=self.choose_excel_files, bg="#9C27B0", fg="white", font=("Arial", 10, "bold")).pack(side=tk.LEFT, padx=6)
        tk.Button(top_frame, text="Yemekler Excel Yükle", command=self.load_yemekler, bg="#4caf50", fg="white").pack(side=tk.LEFT, padx=6)
        tk.Button(top_frame, text="Ürünler Excel Yükle", command=self.load_urunler, bg="#2196f3", fg="white").pack(side=tk.LEFT, padx=6)
        tk.Button(top_frame, text="Yemekleri Kaydet", command=self.save_yemekler, bg="#ff9800", fg="white").pack(side=tk.LEFT, padx=6)
        tk.Button(top_frame, text="Seçili Reçeteyi Dışa Aktar", command=self.export_selected_recipe, bg="#9c27b0", fg="white").pack(side=tk.LEFT, padx=6)
        tk.Button(top_frame, text="Yenile", command=self.populate_meals, bg="#607d8b", fg="white").pack(side=tk.LEFT, padx=6)
        
        # V8 YENİLİK: Menü güncelleme butonu
        tk.Button(top_frame, text="🔄 Menü Güncelle", command=self.refresh_menu_from_excel, bg="#28a745", fg="white", font=("Arial", 10, "bold")).pack(side=tk.LEFT, padx=6)
        
        # FAZ 2 YENİLİK: Yemek ekleme butonu
        tk.Button(top_frame, text="➕ Yemek Ekle", command=self.create_new_meal, bg="#e91e63", fg="white", font=("Arial", 10, "bold")).pack(side=tk.LEFT, padx=6)
        
        # Ana panel
        main_frame = tk.Frame(cost_tab)
        main_frame.pack(fill="both", expand=True, padx=6, pady=6)
        
        # Sol panel - Yemek listesi
        left_frame = tk.Frame(main_frame)
        left_frame.pack(side=tk.LEFT, fill="y", padx=6, pady=6)
        
        # Yemek listesi için arama
        tk.Label(left_frame, text="🍽️ Yemek Listesi", font=LARGE_BOLD_FONT).pack(anchor="w")
        search_frame = tk.Frame(left_frame)
        search_frame.pack(fill=tk.X, pady=2)
        tk.Label(search_frame, text="Ara:").pack(side=tk.LEFT, padx=2)
        self.meal_search_var = tk.StringVar()
        tk.Entry(search_frame, textvariable=self.meal_search_var, width=30).pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.meal_search_var.trace("w", self.on_meal_search)
        
        # Meal tree ile scrollbar frame
        meal_tree_frame = tk.Frame(left_frame)
        meal_tree_frame.pack(fill="both", expand=True)
        
        meal_scrollbar = ttk.Scrollbar(meal_tree_frame, orient="vertical")
        meal_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        self.meal_tree = ttk.Treeview(meal_tree_frame, columns=("Yemek","Maliyet"), show="headings", height=28,
                                     yscrollcommand=meal_scrollbar.set)
        self.meal_tree.heading("Yemek", text="Yemek Adı", anchor="w", 
                              command=lambda: self.sort_treeview(self.meal_tree, "Yemek", False))
        self.meal_tree.heading("Maliyet", text="Porsiyon Maliyeti (TL)", anchor="center",
                              command=lambda: self.sort_treeview(self.meal_tree, "Maliyet", False))
        self.meal_tree.column("Yemek", anchor="w", width=340)
        self.meal_tree.column("Maliyet", anchor="center", width=160)
        self.meal_tree.pack(side=tk.LEFT, fill="both", expand=True)
        self.meal_tree.bind("<<TreeviewSelect>>", self.show_recipe)
        
        meal_scrollbar.config(command=self.meal_tree.yview)
        
        # Sağ panel
        right_frame = tk.Frame(main_frame)
        right_frame.pack(side=tk.LEFT, fill="both", expand=True, padx=6)
        
        # Reçete paneli
        recipe_frame = tk.LabelFrame(right_frame, text="📋 Seçilen Yemek Reçetesi", font=("Arial", 13, "bold"))
        recipe_frame.pack(fill="both", expand=True, pady=6)
        
        # Reçeteye ürün ekleme butonları
        recipe_btn_frame = tk.Frame(recipe_frame)
        recipe_btn_frame.pack(fill="x", pady=2)
        tk.Button(recipe_btn_frame, text="Ürün Ekle", command=self.on_recipe_add_product, bg="#4caf50", fg="white").pack(side=tk.LEFT, padx=2)
        tk.Button(recipe_btn_frame, text="Seçili Ürünü Sil", command=self.on_recipe_delete_product, bg="#f44336", fg="white").pack(side=tk.LEFT, padx=2)
        
        # Recipe tree ile scrollbar frame
        recipe_tree_frame = tk.Frame(recipe_frame)
        recipe_tree_frame.pack(fill="both", expand=True)
        
        recipe_scrollbar = ttk.Scrollbar(recipe_tree_frame, orient="vertical")
        recipe_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        cols = ("Ürün","Miktar","Birim","Birim Fiyat (TL)","Toplam (TL)")
        self.recipe_tree = ttk.Treeview(recipe_tree_frame, columns=cols, show="headings", height=14,
                                       yscrollcommand=recipe_scrollbar.set)
        for c in cols:
            anchor = "center"
            width = 120
            if c == "Ürün":
                anchor = "w"
                width = 240
            self.recipe_tree.heading(c, text=c, anchor="center",
                                    command=lambda col=c: self.sort_treeview(self.recipe_tree, col, False))
            self.recipe_tree.column(c, anchor=anchor, width=width)
        self.recipe_tree.pack(side=tk.LEFT, fill="both", expand=True)
        self.recipe_tree.bind("<Double-1>", self.on_recipe_double_click)
        
        recipe_scrollbar.config(command=self.recipe_tree.yview)
        
        self.recipe_total_label = tk.Label(recipe_frame, text="", font=("Arial", 12, "bold"))
        self.recipe_total_label.pack(pady=6)
        
        # Renk etiketleri
        self.recipe_tree.tag_configure("cheap", background="#ccffcc")
        self.recipe_tree.tag_configure("medium", background="#fff4b0")
        self.recipe_tree.tag_configure("expensive", background="#ffb3b3")
        
        # Aylık maliyet paneli
        monthly_frame = tk.LabelFrame(right_frame, text="📅 Aylık Maliyetler", font=("Arial", 13, "bold"))
        monthly_frame.pack(fill="x", pady=6)
        self.monthly_tree = ttk.Treeview(monthly_frame, columns=("Ay","Toplam Maliyet (TL)"), show="headings", height=6)
        self.monthly_tree.heading("Ay", text="Ay")
        self.monthly_tree.heading("Toplam Maliyet (TL)", text="Toplam Maliyet (TL)")
        self.monthly_tree.column("Ay", anchor="center", width=150)
        self.monthly_tree.column("Toplam Maliyet (TL)", anchor="center", width=220)
        self.monthly_tree.pack(fill="x", expand=True)
        
        # İlk yükleme
        self.populate_meals()
        
    def create_planning_tab(self):
        """Günlük planlama sekmesi"""
        planning_tab = tk.Frame(self.notebook, bg="#f5fff5")
        self.notebook.add(planning_tab, text="📅 Günlük Planlama")
        
        # Sol panel - Yemek listesi ve özet
        left_panel = tk.Frame(planning_tab, width=360)
        left_panel.pack(side="left", fill="y")
        
        # Yemek listesi için arama
        ttk.Label(left_panel, text="Yemek Listesi", font=LARGE_BOLD_FONT).pack(pady=6)
        search_frame = tk.Frame(left_panel)
        search_frame.pack(fill=tk.X, pady=2)
        ttk.Label(search_frame, text="Ara:").pack(side=tk.LEFT, padx=2)
        self.planning_search_var = tk.StringVar()
        ttk.Entry(search_frame, textvariable=self.planning_search_var, width=25).pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.planning_search_var.trace("w", self.on_planning_search)
        
        self.planning_meal_tree = ttk.Treeview(left_panel, columns=("Yemek Adı", "Maliyet"), show="headings", height=20)
        self.planning_meal_tree.heading("Yemek Adı", text="Yemek Adı")
        self.planning_meal_tree.column("Yemek Adı", anchor="w", width=200)
        self.planning_meal_tree.heading("Maliyet", text="Maliyet (TL/pors)")
        self.planning_meal_tree.column("Maliyet", anchor="e", width=120)
        self.planning_meal_tree.pack(fill="y", padx=6, pady=6)
        
        # Özet paneli
        summary_frame = ttk.Frame(left_panel)
        summary_frame.pack(side="bottom", fill="x", pady=6)
        ttk.Label(summary_frame, text="Seçili Günlerin Sarf Ürünleri ve Toplam", font=BOLD_FONT).pack(anchor="w", padx=6, pady=4)
        self.sarf_tree = ttk.Treeview(summary_frame, columns=("miktar",), show="headings", height=6)
        self.sarf_tree.heading("#1", text="Miktar")
        self.sarf_tree.column("#1", width=160, anchor="center")
        self.sarf_tree.pack(fill="x", padx=6, pady=4)
        self.planning_total_label = ttk.Label(summary_frame, text="Toplam Maliyet: 0.00 TL", font=LARGE_BOLD_FONT, foreground="red")
        self.planning_total_label.pack(pady=6)
        
        # Kaydet butonu
        save_btn_frame = ttk.Frame(summary_frame)
        save_btn_frame.pack(fill="x", pady=4)
        ttk.Button(save_btn_frame, text="Günlük Raporu Kaydet", command=self.save_daily_report).pack(side="right", padx=6)
        
        # Sağ panel - Günler
        right_panel = tk.Frame(planning_tab)
        right_panel.pack(side="left", fill="both", expand=True)
        ttk.Label(right_panel, text="Ayın Günleri (Tek tık = seç/çıkart)", font=LARGE_BOLD_FONT).pack(pady=6)
        
        # Scroll alanı
        canvas = tk.Canvas(right_panel)
        canvas.pack(side="left", fill="both", expand=True)
        vsb = ttk.Scrollbar(right_panel, orient="vertical", command=canvas.yview)
        vsb.pack(side="right", fill="y")
        canvas.configure(yscrollcommand=vsb.set)
        self.planning_container = ttk.Frame(canvas)
        canvas.create_window((0,0), window=self.planning_container, anchor="nw")
        self.planning_container.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        
        # Günleri oluştur
        self.build_days_grid()
        
        # Yemek listesini doldur
        self.populate_planning_meals()

    def create_revenue_tab(self):
        """Gelir analizi sekmesi"""
        revenue_tab = tk.Frame(self.notebook, bg="#e6ffe6")
        self.notebook.add(revenue_tab, text="💵 Gelir")
        
        # Üst bilgi paneli
        top_panel = tk.Frame(revenue_tab, bg="#e6ffe6")
        top_panel.pack(fill=tk.X, pady=10)
        
        # Excel dosya seçimi butonları
        excel_btn_frame = tk.Frame(top_panel, bg="#e6ffe6")
        excel_btn_frame.pack(fill=tk.X, pady=5)
        
        # Genel Excel dosyaları seçimi
        tk.Button(excel_btn_frame, text="📁 Tüm Excel Dosyalarını Seç", command=self.choose_excel_files, 
                 bg="#4CAF50", fg="white", font=("Arial", 11, "bold")).pack(side=tk.LEFT, padx=5)
        
        # Ciro için özel Excel seçimi
        tk.Button(excel_btn_frame, text="📊 Ciro Excel Dosyasını Seç", command=self.choose_ciro_excel_file, 
                 bg="#FF9800", fg="white", font=("Arial", 11, "bold")).pack(side=tk.LEFT, padx=5)
        
        # Toplam ciro etiketi
        self.toplam_ciro_label = tk.Label(top_panel, text="", font=("Arial", 20, "bold"), bg="#ffff99", fg="#333")
        self.toplam_ciro_label.pack(pady=12)
        
        # Filtre paneli
        filter_frame = tk.LabelFrame(top_panel, text="📊 Gelişmiş Filtreleme & Raporlama", font=("Arial", 12, "bold"), bg="#e6ffe6")
        filter_frame.pack(fill=tk.X, padx=10, pady=5)
        
        # Filtre seçenekleri - 3 satır halinde
        filter_row1 = tk.Frame(filter_frame, bg="#e6ffe6")
        filter_row1.pack(fill=tk.X, pady=2)
        
        # Tarih aralığı seçimi
        date_range_frame = tk.Frame(filter_row1, bg="#e6ffe6")
        date_range_frame.pack(side=tk.LEFT, padx=10)
        tk.Label(date_range_frame, text="📅 Tarih Aralığı:", bg="#e6ffe6", font=("Arial", 10, "bold")).pack()
        
        date_sub_frame = tk.Frame(date_range_frame, bg="#e6ffe6")
        date_sub_frame.pack()
        
        tk.Label(date_sub_frame, text="Başlangıç:", bg="#e6ffe6").pack(side=tk.LEFT)
        self.start_date_var = tk.StringVar()
        self.start_date_combo = ttk.Combobox(date_sub_frame, textvariable=self.start_date_var, width=12)
        self.start_date_combo.pack(side=tk.LEFT, padx=2)
        
        tk.Label(date_sub_frame, text="Bitiş:", bg="#e6ffe6").pack(side=tk.LEFT)
        self.end_date_var = tk.StringVar()
        self.end_date_combo = ttk.Combobox(date_sub_frame, textvariable=self.end_date_var, width=12)
        self.end_date_combo.pack(side=tk.LEFT, padx=2)
        
        # Ödeme türü filtresi
        payment_frame = tk.Frame(filter_row1, bg="#e6ffe6")
        payment_frame.pack(side=tk.LEFT, padx=10)
        tk.Label(payment_frame, text="💳 Ödeme Türü:", bg="#e6ffe6", font=("Arial", 10, "bold")).pack()
        self.payment_filter_var = tk.StringVar(value="Tümü")
        payment_options = ["Tümü"] + PAYMENT_TYPES
        self.payment_combo = ttk.Combobox(payment_frame, textvariable=self.payment_filter_var, values=payment_options, width=15)
        self.payment_combo.pack(pady=2)
        
        # Restoran filtresi
        restaurant_frame = tk.Frame(filter_row1, bg="#e6ffe6")
        restaurant_frame.pack(side=tk.LEFT, padx=10)
        tk.Label(restaurant_frame, text="🏪 Restoran:", bg="#e6ffe6", font=("Arial", 10, "bold")).pack()
        self.restaurant_filter_var = tk.StringVar(value="Tümü")
        restaurant_options = ["Tümü"] + restoranlar
        self.restaurant_combo = ttk.Combobox(restaurant_frame, textvariable=self.restaurant_filter_var, values=restaurant_options, width=15)
        self.restaurant_combo.pack(pady=2)
        
        # İkinci satır - Hızlı seçimler
        filter_row2 = tk.Frame(filter_frame, bg="#e6ffe6")
        filter_row2.pack(fill=tk.X, pady=2)
        
        tk.Label(filter_row2, text="⚡ Hızlı Seçim:", bg="#e6ffe6", font=("Arial", 10, "bold")).pack(side=tk.LEFT, padx=5)
        tk.Button(filter_row2, text="Bugün", command=lambda: self.set_quick_date_range("today"), bg="#2196F3", fg="white").pack(side=tk.LEFT, padx=2)
        tk.Button(filter_row2, text="Bu Hafta", command=lambda: self.set_quick_date_range("week"), bg="#2196F3", fg="white").pack(side=tk.LEFT, padx=2)
        tk.Button(filter_row2, text="Bu Ay", command=lambda: self.set_quick_date_range("month"), bg="#2196F3", fg="white").pack(side=tk.LEFT, padx=2)
        tk.Button(filter_row2, text="Son 7 Gün", command=lambda: self.set_quick_date_range("last7"), bg="#2196F3", fg="white").pack(side=tk.LEFT, padx=2)
        tk.Button(filter_row2, text="Son 30 Gün", command=lambda: self.set_quick_date_range("last30"), bg="#2196F3", fg="white").pack(side=tk.LEFT, padx=2)
        
        # Üçüncü satır - Butonlar
        btn_frame = tk.Frame(filter_frame, bg="#e6ffe6")
        btn_frame.pack(fill=tk.X, pady=5)
        
        tk.Button(btn_frame, text="🔍 Filtreyi Uygula", command=self.apply_revenue_filter, bg="#4CAF50", fg="white", font=("Arial", 10, "bold")).pack(side=tk.LEFT, padx=5)
        tk.Button(btn_frame, text="📈 Ödeme Türü Analizi", command=self.show_payment_analysis, bg="#2196F3", fg="white", font=("Arial", 10, "bold")).pack(side=tk.LEFT, padx=5)
        tk.Button(btn_frame, text="⚙️ Ödeme Türlerini Yönet", command=self.manage_payment_types, bg="#9C27B0", fg="white", font=("Arial", 10, "bold")).pack(side=tk.LEFT, padx=5)
        tk.Button(btn_frame, text="🔗 Excel Dosyalarını Birleştir", command=self.merge_excel_files, bg="#E91E63", fg="white", font=("Arial", 10, "bold")).pack(side=tk.LEFT, padx=5)
        tk.Button(btn_frame, text="📋 Detaylı Rapor", command=self.generate_detailed_report, bg="#FF9800", fg="white", font=("Arial", 10, "bold")).pack(side=tk.LEFT, padx=5)
        tk.Button(btn_frame, text="🔄 Filtreyi Temizle", command=self.clear_revenue_filters, bg="#F44336", fg="white", font=("Arial", 10, "bold")).pack(side=tk.LEFT, padx=5)
        
        # V8 YENİLİK: Kar-zarar analizi butonu
        tk.Button(btn_frame, text="📊 Kar-Zarar Analizi", command=self.show_profit_loss_analysis, bg="#6f42c1", fg="white", font=("Arial", 10, "bold")).pack(side=tk.LEFT, padx=5)
        
        # İçerik alanı
        content_frame = tk.Frame(revenue_tab, bg="#e6ffe6")
        content_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # Aylık liste
        monthly_frame = tk.Frame(content_frame, bg="#e6ffe6")
        monthly_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        tk.Label(monthly_frame, text="Aylık Ciro Listesi (çift tıkla günleri göster)", bg="#e6ffe6", font=("Arial", 12, "bold")).pack(anchor="w")
        self.revenue_monthly_tree = ttk.Treeview(monthly_frame, columns=("Ay", "Toplam", "İşlem"), show="headings", height=10)
        self.revenue_monthly_tree.heading("Ay", text="Ay")
        self.revenue_monthly_tree.heading("Toplam", text="Toplam (TL)")
        self.revenue_monthly_tree.heading("İşlem", text="İşlem Sayısı")
        self.revenue_monthly_tree.column("Ay", width=120)
        self.revenue_monthly_tree.column("Toplam", width=150, anchor="e")
        self.revenue_monthly_tree.column("İşlem", width=100, anchor="e")
        self.revenue_monthly_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        monthly_scroll = ttk.Scrollbar(monthly_frame, orient="vertical", command=self.revenue_monthly_tree.yview)
        self.revenue_monthly_tree.configure(yscrollcommand=monthly_scroll.set)
        monthly_scroll.pack(side=tk.LEFT, fill=tk.Y)
        
        # Günlük kırılım
        daily_frame = tk.Frame(content_frame, bg="#e6ffe6")
        daily_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(10,0))
        tk.Label(daily_frame, text="Günlük Döküm", bg="#e6ffe6", font=("Arial", 12, "bold")).pack(anchor="w")
        self.daily_tree = ttk.Treeview(daily_frame, columns=("Gün", "Toplam", "İşlem"), show="headings", height=10)
        self.daily_tree.heading("Gün", text="Gün")
        self.daily_tree.heading("Toplam", text="Toplam (TL)")
        self.daily_tree.heading("İşlem", text="İşlem Sayısı")
        self.daily_tree.column("Gün", width=120)
        self.daily_tree.column("Toplam", width=150, anchor="e")
        self.daily_tree.column("İşlem", width=100, anchor="e")
        self.daily_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        daily_scroll = ttk.Scrollbar(daily_frame, orient="vertical", command=self.daily_tree.yview)
        self.daily_tree.configure(yscrollcommand=daily_scroll.set)
        daily_scroll.pack(side=tk.LEFT, fill=tk.Y)
        
        # Porsiyon detayı
        portion_frame = tk.Frame(daily_frame, bg="#e6ffe6")
        portion_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(10,0))
        tk.Label(portion_frame, text="Porsiyon Detayı (Ürün, Adet)", bg="#e6ffe6", font=("Arial", 12, "bold")).pack(anchor="w")
        self.portion_tree = ttk.Treeview(portion_frame, columns=("Ürün", "Adet", "Ciro"), show="headings", height=10)
        self.portion_tree.heading("Ürün", text="Ürün")
        self.portion_tree.heading("Adet", text="Adet")
        self.portion_tree.heading("Ciro", text="Ciro (TL)")
        self.portion_tree.column("Ürün", width=150)
        self.portion_tree.column("Adet", width=60, anchor="e")
        self.portion_tree.column("Ciro", width=100, anchor="e")
        self.portion_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        portion_scroll = ttk.Scrollbar(portion_frame, orient="vertical", command=self.portion_tree.yview)
        self.portion_tree.configure(yscrollcommand=portion_scroll.set)
        portion_scroll.pack(side=tk.LEFT, fill=tk.Y)
        
        # Zebra çizgiler
        try:
            for tree in [self.revenue_monthly_tree, self.daily_tree, self.portion_tree]:
                tree.tag_configure("odd", background="#f9f9f9")
                tree.tag_configure("even", background="#ffffff")
        except Exception:
            pass
        
        # Olayları bağla
        self.revenue_monthly_tree.bind("<Double-1>", self.on_month_double_click)
        self.daily_tree.bind("<Double-1>", self.on_day_double_click)
        
        # İlk güncelleme
        self.update_revenue_label()

    # V8 YENİLİK: Satın alma sekmesi
    def create_purchase_tab(self):
        """Satın alma sekmesi - SARI"""
        purchase_tab = tk.Frame(self.notebook, bg="#fffbf0")
        self.notebook.add(purchase_tab, text="💳 Satın Alma")
        
        # V8 YENİLİK: Renkli sekme stili uygula
        tab_index = len(self.notebook.tabs()) - 1
        try:
            # Sarı renk stili oluştur
            style = ttk.Style()
            style.configure('Yellow.TNotebook.Tab', background='#fff3cd', foreground='#856404')
            style.map('Yellow.TNotebook.Tab', background=[('selected', '#ffeaa7')])
            self.notebook.tab(tab_index, style='Yellow.TNotebook.Tab')
        except:
            pass  # Stil uygulanamadıysa devam et
        
        # Başlık
        title_frame = tk.Frame(purchase_tab, bg="#fffbf0")
        title_frame.pack(fill=tk.X, pady=10)
        tk.Label(title_frame, text="💳 SATIN ALMA YÖNETİMİ", 
                font=("Arial", 18, "bold"), bg="#fffbf0", fg="#856404").pack()
        tk.Label(title_frame, text="Ürün alışlarını kaydedin ve stok takibi yapın", 
                font=("Arial", 11), bg="#fffbf0", fg="#6c757d").pack()
        
        # Ana container
        main_container = tk.Frame(purchase_tab, bg="#fffbf0")
        main_container.pack(fill=tk.BOTH, expand=True, padx=20, pady=10)
        
        # Sol panel - Satın alma formu
        form_frame = tk.LabelFrame(main_container, text="📝 Yeni Ürün Alışı", 
                                  font=("Arial", 14, "bold"), bg="#fffbf0", fg="#856404")
        form_frame.pack(side=tk.LEFT, fill=tk.Y, padx=(0, 10), pady=5)
        
        # Form alanları
        tk.Label(form_frame, text="Ürün Adı:", font=("Arial", 12, "bold"), bg="#fffbf0").pack(anchor="w", padx=10, pady=(10,5))
        self.purchase_product_var = tk.StringVar()
        self.purchase_product_entry = tk.Entry(form_frame, textvariable=self.purchase_product_var, 
                                              font=("Arial", 12), width=30)
        self.purchase_product_entry.pack(fill=tk.X, padx=10, pady=(0,10))
        
        tk.Label(form_frame, text="Miktar:", font=("Arial", 12, "bold"), bg="#fffbf0").pack(anchor="w", padx=10, pady=(0,5))
        self.purchase_quantity_var = tk.StringVar()
        self.purchase_quantity_entry = tk.Entry(form_frame, textvariable=self.purchase_quantity_var, 
                                               font=("Arial", 12), width=30)
        self.purchase_quantity_entry.pack(fill=tk.X, padx=10, pady=(0,10))
        
        tk.Label(form_frame, text="Alış Fiyatı (TL):", font=("Arial", 12, "bold"), bg="#fffbf0").pack(anchor="w", padx=10, pady=(0,5))
        self.purchase_price_var = tk.StringVar()
        self.purchase_price_entry = tk.Entry(form_frame, textvariable=self.purchase_price_var, 
                                            font=("Arial", 12), width=30)
        self.purchase_price_entry.pack(fill=tk.X, padx=10, pady=(0,5))
        
        # FAZ 2 - TALEP 6: Önceki fiyat karşılaştırma bilgisi
        self.price_comparison_label = tk.Label(form_frame, text="", font=("Arial", 10), 
                                               bg="#fffbf0", fg="#666", wraplength=280, justify=tk.LEFT)
        self.price_comparison_label.pack(anchor="w", padx=10, pady=(0,10))
        
        tk.Label(form_frame, text="Birim:", font=("Arial", 12, "bold"), bg="#fffbf0").pack(anchor="w", padx=10, pady=(0,5))
        self.purchase_unit_var = tk.StringVar()
        self.purchase_unit_entry = tk.Entry(form_frame, textvariable=self.purchase_unit_var, 
                                            font=("Arial", 12), width=30)
        self.purchase_unit_entry.pack(fill=tk.X, padx=10, pady=(0,10))
        
        tk.Label(form_frame, text="Tedarikçi:", font=("Arial", 12, "bold"), bg="#fffbf0").pack(anchor="w", padx=10, pady=(0,5))
        self.purchase_supplier_var = tk.StringVar()
        self.purchase_supplier_entry = tk.Entry(form_frame, textvariable=self.purchase_supplier_var, 
                                               font=("Arial", 12), width=30)
        self.purchase_supplier_entry.pack(fill=tk.X, padx=10, pady=(0,10))
        
        tk.Label(form_frame, text="Tarih:", font=("Arial", 12, "bold"), bg="#fffbf0").pack(anchor="w", padx=10, pady=(0,5))
        self.purchase_date_var = tk.StringVar(value=datetime.now().strftime('%Y-%m-%d'))
        self.purchase_date_entry = tk.Entry(form_frame, textvariable=self.purchase_date_var, 
                                           font=("Arial", 12), width=30)
        self.purchase_date_entry.pack(fill=tk.X, padx=10, pady=(0,15))
        
        # Butonlar
        btn_frame = tk.Frame(form_frame, bg="#fffbf0")
        btn_frame.pack(fill=tk.X, padx=10, pady=10)
        
        tk.Button(btn_frame, text="💾 Satın Almayı Kaydet", command=self.save_purchase, 
                 bg="#28a745", fg="white", font=("Arial", 12, "bold")).pack(fill=tk.X, pady=5)
        tk.Button(btn_frame, text="🧹 Formu Temizle", command=self.clear_purchase_form, 
                 bg="#6c757d", fg="white", font=("Arial", 12, "bold")).pack(fill=tk.X, pady=5)
        
        # Sağ panel - Son alışlar listesi
        history_frame = tk.LabelFrame(main_container, text="📋 Son Alışlar", 
                                     font=("Arial", 14, "bold"), bg="#fffbf0", fg="#856404")
        history_frame.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True, padx=(10, 0), pady=5)
        
        # Treeview için frame
        tree_frame = tk.Frame(history_frame, bg="#fffbf0")
        tree_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # Alış listesi treeview - KARŞILAŞTIRMA SÜTUNU EKLENDİ
        columns = ("Tarih", "Ürün Adı", "Miktar", "Birim", "Alış Fiyatı (TL)", "Birim Fiyat", "Karşılaştırma", "Tedarikçi", "İşlem")
        self.purchase_tree = ttk.Treeview(tree_frame, columns=columns, show="headings", height=15)
        
        # Başlıkları ayarla ve sıralama ekle
        self.purchase_tree.heading("Tarih", text="Tarih", 
                                  command=lambda: self.sort_treeview(self.purchase_tree, "Tarih", False))
        self.purchase_tree.heading("Ürün Adı", text="Ürün Adı",
                                  command=lambda: self.sort_treeview(self.purchase_tree, "Ürün Adı", False))
        self.purchase_tree.heading("Miktar", text="Miktar",
                                  command=lambda: self.sort_treeview(self.purchase_tree, "Miktar", False))
        self.purchase_tree.heading("Birim", text="Birim",
                                  command=lambda: self.sort_treeview(self.purchase_tree, "Birim", False))
        self.purchase_tree.heading("Alış Fiyatı (TL)", text="Toplam Fiyat (TL)",
                                  command=lambda: self.sort_treeview(self.purchase_tree, "Alış Fiyatı (TL)", False))
        self.purchase_tree.heading("Birim Fiyat", text="Birim Fiyat (TL)",
                                  command=lambda: self.sort_treeview(self.purchase_tree, "Birim Fiyat", False))
        self.purchase_tree.heading("Karşılaştırma", text="Karşılaştırma",
                                  command=lambda: self.sort_treeview(self.purchase_tree, "Karşılaştırma", False))
        self.purchase_tree.heading("Tedarikçi", text="Tedarikçi",
                                  command=lambda: self.sort_treeview(self.purchase_tree, "Tedarikçi", False))
        self.purchase_tree.heading("İşlem", text="İşlem", anchor="center")
        
        # Sütun genişlikleri - KARŞILAŞTIRMA SÜTUNU EKLENDİ
        self.purchase_tree.column("Tarih", width=80, anchor="center")
        self.purchase_tree.column("Ürün Adı", width=120, anchor="w")
        self.purchase_tree.column("Miktar", width=60, anchor="center")
        self.purchase_tree.column("Birim", width=60, anchor="center")
        self.purchase_tree.column("Alış Fiyatı (TL)", width=90, anchor="center")
        self.purchase_tree.column("Birim Fiyat", width=80, anchor="center")
        self.purchase_tree.column("Karşılaştırma", width=80, anchor="center")
        self.purchase_tree.column("Tedarikçi", width=100, anchor="w")
        self.purchase_tree.column("İşlem", width=120, anchor="center")
        
        # Scrollbar
        purchase_scrollbar = ttk.Scrollbar(tree_frame, orient="vertical", command=self.purchase_tree.yview)
        self.purchase_tree.configure(yscrollcommand=purchase_scrollbar.set)
        
        self.purchase_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        purchase_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        # Alt panel - Özet bilgiler
        summary_frame = tk.Frame(history_frame, bg="#fffbf0")
        summary_frame.pack(fill=tk.X, padx=10, pady=(0,10))
        
        self.purchase_summary_label = tk.Label(summary_frame, text="Toplam Alış: 0.00 TL", 
                                              font=("Arial", 12, "bold"), bg="#fff3cd", fg="#856404", 
                                              padx=10, pady=5)
        self.purchase_summary_label.pack(fill=tk.X)
        
        # Excel yenileme butonu
        tk.Button(summary_frame, text="🔄 Listeyi Yenile", command=self.refresh_purchase_list, 
                 bg="#17a2b8", fg="white", font=("Arial", 11, "bold")).pack(pady=5)
        
        # FAZ 2 - TALEP 6: Ürün adı ve fiyat değişikliklerini izle
        self.purchase_product_var.trace('w', self.on_purchase_product_change)
        self.purchase_price_var.trace('w', self.on_purchase_price_change)
        
        # İlk yükleme
        self.refresh_purchase_list()

    def create_satis_maliyet_tab(self):
        """Satış-Maliyet Analizi sekmesi"""
        satis_maliyet_tab = tk.Frame(self.notebook, bg="#f0f8ff")
        self.notebook.add(satis_maliyet_tab, text="📊 Satış-Maliyet Analizi")
        
        # Başlık
        title_frame = tk.Frame(satis_maliyet_tab, bg="#f0f8ff")
        title_frame.pack(fill=tk.X, pady=10)
        
        tk.Label(title_frame, text="📊 SATIŞ & MALİYET ANALİZİ", 
                font=("Arial", 20, "bold"), bg="#f0f8ff", fg="#1e3a8a").pack()
        
        tk.Label(title_frame, text="Satış listesi ile reçete maliyetlerini karşılaştırın", 
                font=("Arial", 12), bg="#f0f8ff", fg="#64748b").pack()
        
        # Dosya seçimi paneli
        file_frame = tk.LabelFrame(satis_maliyet_tab, text="📁 Dosya Seçimi", 
                                 font=("Arial", 12, "bold"), bg="#f0f8ff")
        file_frame.pack(fill=tk.X, padx=10, pady=5)
        
        # Satış listesi dosyası seçimi
        sales_file_frame = tk.Frame(file_frame, bg="#f0f8ff")
        sales_file_frame.pack(fill=tk.X, pady=5)
        
        tk.Label(sales_file_frame, text="🍽️ Satış Listesi:", 
                font=("Arial", 11, "bold"), bg="#f0f8ff").pack(side=tk.LEFT, padx=5)
        
        tk.Button(sales_file_frame, text="📄 Satış Dosyası Seç", 
                 command=self.select_sales_file, bg="#3b82f6", fg="white", 
                 font=("Arial", 10), padx=10).pack(side=tk.LEFT, padx=5)
        
        # Seçilen dosya yolu gösterimi
        self.sales_file_label = tk.Label(sales_file_frame, text="❌ Dosya seçilmedi", 
                                        font=("Arial", 9), bg="#f0f8ff", fg="#ef4444")
        self.sales_file_label.pack(side=tk.LEFT, padx=10)
        
        # Satış listesi dosya yolu (başlangıçta None)
        self.selected_sales_file = None
        
        # Kontrol paneli
        control_frame = tk.LabelFrame(satis_maliyet_tab, text="🎛️ Kontrol Paneli", 
                                     font=("Arial", 12, "bold"), bg="#f0f8ff")
        control_frame.pack(fill=tk.X, padx=10, pady=5)
        
        button_frame = tk.Frame(control_frame, bg="#f0f8ff")
        button_frame.pack(fill=tk.X, pady=5)
        
        # Ana analiz butonu
        tk.Button(button_frame, text="🚀 Analizi Başlat", command=self.run_satis_maliyet_analysis,
                 bg="#059669", fg="white", font=("Arial", 14, "bold"), padx=20, pady=5).pack(side=tk.LEFT, padx=5)
        
        # Excel'e aktar butonu
        tk.Button(button_frame, text="📊 Excel'e Aktar", command=self.export_satis_maliyet_excel,
                 bg="#7c3aed", fg="white", font=("Arial", 12, "bold"), padx=15, pady=5).pack(side=tk.LEFT, padx=5)
        
        # Yenile butonu
        tk.Button(button_frame, text="🔄 Yenile", command=self.refresh_satis_maliyet,
                 bg="#f59e0b", fg="white", font=("Arial", 12, "bold"), padx=15, pady=5).pack(side=tk.LEFT, padx=5)
        
        # Durum bilgisi
        status_frame = tk.Frame(control_frame, bg="#f0f8ff")
        status_frame.pack(fill=tk.X, pady=5)
        
        self.satis_maliyet_status = tk.Label(status_frame, text="📊 Analiz için 'Analizi Başlat' butonuna tıklayın", 
                                            font=("Arial", 11), bg="#f0f8ff", fg="#64748b")
        self.satis_maliyet_status.pack(side=tk.LEFT)
        
        # İstatistik paneli
        stats_frame = tk.LabelFrame(satis_maliyet_tab, text="📈 Özet İstatistikler", 
                                   font=("Arial", 12, "bold"), bg="#f0f8ff")
        stats_frame.pack(fill=tk.X, padx=10, pady=5)
        
        stats_inner = tk.Frame(stats_frame, bg="#f0f8ff")
        stats_inner.pack(fill=tk.X, pady=5)
        
        # İstatistik kutuları
        self.satis_count_label = self.create_stat_box(stats_inner, "Satış Ürünü", "0", "#3b82f6")
        self.recete_count_label = self.create_stat_box(stats_inner, "Reçete", "0", "#059669") 
        self.eslesen_count_label = self.create_stat_box(stats_inner, "Eşleşen", "0", "#dc2626")
        self.eslesen_oran_label = self.create_stat_box(stats_inner, "Eşleşme %", "0", "#7c3aed")
        
        # Ana içerik alanı
        main_content = tk.Frame(satis_maliyet_tab, bg="#f0f8ff")
        main_content.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        
        # Sol panel - Eşleşme listesi
        left_frame = tk.LabelFrame(main_content, text="🔗 Eşleşme Listesi", 
                                  font=("Arial", 12, "bold"), bg="#f0f8ff")
        left_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0,5))
        
        # Treeview için container
        tree_container = tk.Frame(left_frame, bg="#f0f8ff")
        tree_container.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # Eşleşme ağacı
        columns = ("Ürün", "Satış Fiyat", "Maliyet", "Kar", "Kar %", "Durum")
        self.satis_maliyet_tree = ttk.Treeview(tree_container, columns=columns, show="headings", height=20)
        
        # Sütun başlıkları
        self.satis_maliyet_tree.heading("Ürün", text="Ürün Adı")
        self.satis_maliyet_tree.heading("Satış Fiyat", text="Satış Fiyatı (TL)")
        self.satis_maliyet_tree.heading("Maliyet", text="Maliyet (TL)")
        self.satis_maliyet_tree.heading("Kar", text="Kar (TL)")
        self.satis_maliyet_tree.heading("Kar %", text="Kar %")
        self.satis_maliyet_tree.heading("Durum", text="Durum")
        
        # Sütun genişlikleri
        self.satis_maliyet_tree.column("Ürün", width=150)
        self.satis_maliyet_tree.column("Satış Fiyat", width=100, anchor="center")
        self.satis_maliyet_tree.column("Maliyet", width=100, anchor="center")
        self.satis_maliyet_tree.column("Kar", width=100, anchor="center")
        self.satis_maliyet_tree.column("Kar %", width=80, anchor="center")
        self.satis_maliyet_tree.column("Durum", width=120, anchor="center")
        
        # Scrollbar
        tree_scroll = ttk.Scrollbar(tree_container, orient="vertical", command=self.satis_maliyet_tree.yview)
        self.satis_maliyet_tree.configure(yscrollcommand=tree_scroll.set)
        
        self.satis_maliyet_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        tree_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        
        # Sağ panel - Detay bilgiler
        right_frame = tk.LabelFrame(main_content, text="📋 Detay Bilgiler", 
                                   font=("Arial", 12, "bold"), bg="#f0f8ff")
        right_frame.pack(side=tk.RIGHT, fill=tk.Y, padx=(5,0))
        
        # Eksik ürünler listesi
        eksik_frame = tk.LabelFrame(right_frame, text="⚠️ Eksik Ürünler", 
                                   font=("Arial", 10, "bold"), bg="#f0f8ff")
        eksik_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # Sadece satışta
        sadece_satis_frame = tk.Frame(eksik_frame, bg="#f0f8ff")
        sadece_satis_frame.pack(fill=tk.X, pady=2)
        
        tk.Label(sadece_satis_frame, text="🔴 Sadece Satışta:", font=("Arial", 9, "bold"), 
                bg="#f0f8ff", fg="#dc2626").pack(anchor="w")
        
        self.sadece_satis_listbox = tk.Listbox(sadece_satis_frame, height=8, font=("Arial", 9))
        self.sadece_satis_listbox.pack(fill=tk.X, pady=2)
        
        # Sadece reçetede
        sadece_recete_frame = tk.Frame(eksik_frame, bg="#f0f8ff")
        sadece_recete_frame.pack(fill=tk.X, pady=2)
        
        tk.Label(sadece_recete_frame, text="🟡 Sadece Reçetede:", font=("Arial", 9, "bold"), 
                bg="#f0f8ff", fg="#f59e0b").pack(anchor="w")
        
        self.sadece_recete_listbox = tk.Listbox(sadece_recete_frame, height=8, font=("Arial", 9))
        self.sadece_recete_listbox.pack(fill=tk.X, pady=2)
        
        # Detay gösterimi için event binding
        self.satis_maliyet_tree.bind("<<TreeviewSelect>>", self.on_satis_maliyet_select)
        
        # İlk yükleme mesajı
        self.satis_maliyet_tree.insert("", "end", values=(
            "Analiz henüz çalıştırılmadı", "", "", "", "", "⏳ Bekliyor"
        ))

    def create_stat_box(self, parent, title, value, color):
        """İstatistik kutusu oluştur"""
        box_frame = tk.Frame(parent, bg=color, relief=tk.RAISED, bd=2)
        box_frame.pack(side=tk.LEFT, padx=5, pady=5, ipadx=10, ipady=5)
        
        title_label = tk.Label(box_frame, text=title, font=("Arial", 10, "bold"), 
                              bg=color, fg="white")
        title_label.pack()
        
        value_label = tk.Label(box_frame, text=value, font=("Arial", 16, "bold"), 
                              bg=color, fg="white")
        value_label.pack()
        
        return value_label

    def calculate_recipe_cost_advanced(self, yemek_adi):
        """Gelişmiş reçete maliyet hesaplama"""
        try:
            if self.yemek_df.empty or self.urun_df.empty:
                return 0.0, []
            
            # Bu yemekle ilgili reçete satırlarını bul
            recipe_rows = self.yemek_df[self.yemek_df['yemek adı'].str.lower().str.strip() == yemek_adi.lower().strip()]
            
            if recipe_rows.empty:
                return 0.0, ["Reçete bulunamadı"]
            
            # Porsiyon sayısını al
            porsiyon_adt = recipe_rows.iloc[0].get('porsiyon adt', 1)
            try:
                porsiyon_adt = parse_float(porsiyon_adt) if porsiyon_adt and parse_float(porsiyon_adt) > 0 else 1
            except:
                porsiyon_adt = 1
            
            total_cost = 0.0
            malzeme_detay = []
            
            for _, recipe_row in recipe_rows.iterrows():
                urun_adi = recipe_row.get('ürün', '')
                miktar = recipe_row.get('miktar', 0)
                birim = recipe_row.get('birim', '')
                
                if pd.isna(urun_adi) or pd.isna(miktar) or miktar == 0:
                    continue
                
                # Enerji maliyetini düşük tut (elektrik/gaz)
                if str(urun_adi).lower() in ['enerji', 'elektrik', 'gaz']:
                    # Saatlik enerji maliyetini 5 TL olarak al (daha gerçekçi)
                    try:
                        miktar_float = float(miktar)
                        enerji_maliyet = miktar_float * 5.0  # 5 TL/saat
                        total_cost += enerji_maliyet
                        malzeme_detay.append(f"⚡ {urun_adi}: {miktar} {birim} × 5.00 = {enerji_maliyet:.2f} TL")
                    except:
                        pass
                    continue
                
                try:
                    miktar = float(miktar)
                except:
                    continue
                
                # Bu ürünün fiyatını ürünler listesinden bul
                urun_rows = self.urun_df[self.urun_df['Ürün Adı'].str.lower().str.strip() == str(urun_adi).lower().strip()]
                
                if not urun_rows.empty:
                    # En son tarihli fiyatı al
                    if 'Tarih' in urun_rows.columns:
                        latest_row = urun_rows.sort_values('Tarih', ascending=False).iloc[0]
                    else:
                        latest_row = urun_rows.iloc[0]
                    
                    birim_fiyat = latest_row.get('Alış Fiyatı (TL)', 0)
                    urun_miktar = latest_row.get('Miktar', 1)
                    
                    try:
                        birim_fiyat = parse_float(birim_fiyat) 
                        urun_miktar = parse_float(urun_miktar) if parse_float(urun_miktar) > 0 else 1
                        
                        # Birim fiyat hesapla
                        per_unit_cost = birim_fiyat / urun_miktar
                        malzeme_cost = per_unit_cost * miktar
                        total_cost += malzeme_cost
                        
                        malzeme_detay.append(f"📦 {urun_adi}: {miktar} {birim} × {per_unit_cost:.2f} = {malzeme_cost:.2f} TL")
                        
                    except:
                        malzeme_detay.append(f"❌ {urun_adi}: {miktar} {birim} - Fiyat hesaplanamadı")
                else:
                    malzeme_detay.append(f"⚠️ {urun_adi}: {miktar} {birim} - Ürün fiyat listesinde yok")
            
            # Porsiyon başına maliyet
            per_portion_cost = total_cost / porsiyon_adt
            malzeme_detay.insert(0, f"📊 Toplam maliyet: {total_cost:.2f} TL ({porsiyon_adt} porsiyon)")
            malzeme_detay.insert(1, f"🍽️ Porsiyon başı: {per_portion_cost:.2f} TL")
            
            return per_portion_cost, malzeme_detay
            
        except Exception as e:
            return 0.0, [f"Hata: {str(e)}"]
    
    def select_sales_file(self):
        """Satış listesi dosyası seçimi"""
        file_path = filedialog.askopenfilename(
            title="Satış Listesi Dosyası Seçin",
            filetypes=[("Excel dosyaları", "*.xlsx *.xls"), ("Tüm dosyalar", "*.*")],
            initialdir=BASE_DIR
        )
        
        if file_path:
            self.selected_sales_file = file_path
            # Sadece dosya adını göster
            file_name = os.path.basename(file_path)
            self.sales_file_label.config(text=f"✅ {file_name}", fg="#059669")
        else:
            self.selected_sales_file = None
            self.sales_file_label.config(text="❌ Dosya seçilmedi", fg="#ef4444")

    def run_satis_maliyet_analysis(self):
        """Ana satış-maliyet analizi"""
        try:
            # Dosya seçimi kontrolü
            if not self.selected_sales_file:
                messagebox.showwarning("Uyarı", "Lütfen önce satış listesi dosyasını seçin!")
                return
            
            # Seçilen dosyanın varlığını kontrol et
            if not os.path.exists(self.selected_sales_file):
                messagebox.showerror("Hata", f"Seçilen dosya bulunamadı:\n{self.selected_sales_file}")
                return
            
            self.satis_maliyet_status.config(text="🔄 Analiz başlatılıyor...", fg="#f59e0b")
            self.root.update()
            
            # Veri yükleme kontrolü
            self.load_cost_dataframes()
            
            # Seçilen dosyadan satış verilerini yükle
            menu_dict = {}
            
            try:
                menu_df = pd.read_excel(self.selected_sales_file, engine="openpyxl")
                for _, row in menu_df.iterrows():
                    if pd.notna(row["Ürün"]) and pd.notna(row["Fiyat"]):
                        menu_dict[str(row["Ürün"]).strip()] = float(row["Fiyat"])
            except Exception as e:
                messagebox.showerror("Hata", f"Satış listesi yüklenemedi:\n{e}")
                return
            
            if not menu_dict:
                messagebox.showwarning("Uyarı", "Satış listesi boş veya geçersiz veri içeriyor!")
                return
                
            # Yemek listesini al
            if os.path.exists("user_input_files/yemekler.xlsx"):
                try:
                    self.yemek_df = pd.read_excel("user_input_files/yemekler.xlsx", engine="openpyxl")
                    self.yemek_df = normalize_yemek_cols(self.yemek_df)
                except Exception as e:
                    messagebox.showerror("Hata", f"Reçete listesi yüklenemedi: {e}")
                    return
            
            # Ürün fiyatları
            if os.path.exists("user_input_files/urunler.xlsx"):
                try:
                    self.urun_df = pd.read_excel("user_input_files/urunler.xlsx", engine="openpyxl")
                    self.urun_df = normalize_urunler_cols(self.urun_df)
                except Exception as e:
                    messagebox.showerror("Hata", f"Ürün fiyat listesi yüklenemedi: {e}")
                    return
            
            self.satis_maliyet_status.config(text="📊 Eşleştirme yapılıyor...", fg="#059669")
            self.root.update()
            
            # Eşleştirme analizi
            satis_urunler = set(str(x).lower().strip() for x in menu_dict.keys())
            recete_yemekler = set()
            
            if not self.yemek_df.empty and 'yemek adı' in self.yemek_df.columns:
                recete_yemekler = set(str(x).lower().strip() for x in self.yemek_df['yemek adı'].dropna().unique())
                recete_yemekler = {x for x in recete_yemekler if x and str(x).strip()}
            
            # Eşleşmeleri bul
            eslesenler = satis_urunler.intersection(recete_yemekler)
            sadece_satista = satis_urunler - recete_yemekler
            sadece_recetede = recete_yemekler - satis_urunler
            
            # İstatistikleri güncelle
            self.satis_count_label.config(text=str(len(satis_urunler)))
            self.recete_count_label.config(text=str(len(recete_yemekler)))
            self.eslesen_count_label.config(text=str(len(eslesenler)))
            
            eslesen_oran = (len(eslesenler) / max(len(satis_urunler.union(recete_yemekler)), 1)) * 100
            self.eslesen_oran_label.config(text=f"{eslesen_oran:.1f}%")
            
            # Treeview'i temizle
            for item in self.satis_maliyet_tree.get_children():
                self.satis_maliyet_tree.delete(item)
            
            self.satis_maliyet_status.config(text="💰 Maliyet hesaplamaları yapılıyor...", fg="#7c3aed")
            self.root.update()
            
            # Eşleşen ürünler için analiz
            for urun_lower in sorted(eslesenler):
                # Orijinal ismi bul
                urun_original = None
                for orig_name, price in menu_dict.items():
                    if orig_name.lower().strip() == urun_lower:
                        urun_original = orig_name
                        satis_fiyat = price
                        break
                
                if urun_original:
                    # Maliyet hesapla
                    maliyet, detay = self.calculate_recipe_cost_advanced(urun_original)
                    
                    if maliyet > 0:
                        kar = satis_fiyat - maliyet
                        kar_oran = (kar / maliyet) * 100
                        
                        # Durum belirleme
                        if kar_oran > 200:
                            durum = "🟢 Çok İyi"
                        elif kar_oran > 100:
                            durum = "🟡 İyi"
                        elif kar_oran > 0:
                            durum = "🟠 Düşük"
                        else:
                            durum = "🔴 Zarar"
                        
                        self.satis_maliyet_tree.insert("", "end", values=(
                            urun_original,
                            f"{satis_fiyat:.2f}",
                            f"{maliyet:.2f}",
                            f"{kar:.2f}",
                            f"%{kar_oran:.1f}",
                            durum
                        ))
                    else:
                        self.satis_maliyet_tree.insert("", "end", values=(
                            urun_original,
                            f"{satis_fiyat:.2f}",
                            "Hesaplanamadı",
                            "-",
                            "-",
                            "❌ Veri Eksik"
                        ))
            
            # Sadece satışta olanlar için
            for urun_lower in sorted(sadece_satista)[:20]:  # İlk 20'sini göster
                # Orijinal ismi bul
                for orig_name, price in menu_dict.items():
                    if orig_name.lower().strip() == urun_lower:
                        self.satis_maliyet_tree.insert("", "end", values=(
                            orig_name,
                            f"{price:.2f}",
                            "Reçete Yok",
                            "-",
                            "-",
                            "🔴 Sadece Satışta"
                        ))
                        break
            
            # Eksik ürün listelerini güncelle
            self.sadece_satis_listbox.delete(0, tk.END)
            for item in sorted(sadece_satista)[:50]:  # İlk 50 tanesi
                # Orijinal ismi bul
                for orig_name in menu_dict.keys():
                    if orig_name.lower().strip() == item:
                        self.sadece_satis_listbox.insert(tk.END, orig_name)
                        break
            
            self.sadece_recete_listbox.delete(0, tk.END)
            for item in sorted(sadece_recetede)[:50]:  # İlk 50 tanesi
                # Orijinal ismi bul (reçeteden)
                for yemek_name in self.yemek_df['yemek adı'].dropna().unique():
                    if str(yemek_name).lower().strip() == item:
                        self.sadece_recete_listbox.insert(tk.END, yemek_name)
                        break
            
            self.satis_maliyet_status.config(text=f"✅ Analiz tamamlandı! {len(eslesenler)} eşleşme bulundu", fg="#059669")
            
        except Exception as e:
            self.satis_maliyet_status.config(text=f"❌ Hata: {str(e)}", fg="#dc2626")
            messagebox.showerror("Hata", f"Analiz sırasında hata oluştu:\n{str(e)}")

    def on_satis_maliyet_select(self, event):
        """Seçilen ürün için detay göster"""
        selection = self.satis_maliyet_tree.selection()
        if selection:
            item = self.satis_maliyet_tree.item(selection[0])
            urun_adi = item['values'][0]
            
            # Detay hesaplama
            maliyet, detay = self.calculate_recipe_cost_advanced(urun_adi)
            
            # Popup ile detayları göster
            detail_window = tk.Toplevel(self.root)
            detail_window.title(f"Maliyet Detayı: {urun_adi}")
            detail_window.geometry("500x400")
            detail_window.configure(bg="#f0f8ff")
            
            tk.Label(detail_window, text=f"📊 {urun_adi} - Maliyet Detayı", 
                    font=("Arial", 14, "bold"), bg="#f0f8ff").pack(pady=10)
            
            detail_frame = tk.Frame(detail_window, bg="#f0f8ff")
            detail_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
            
            detail_text = tk.Text(detail_frame, font=("Courier", 10), wrap=tk.WORD)
            detail_scroll = ttk.Scrollbar(detail_frame, orient="vertical", command=detail_text.yview)
            detail_text.configure(yscrollcommand=detail_scroll.set)
            
            detail_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
            detail_scroll.pack(side=tk.RIGHT, fill=tk.Y)
            
            # Detayları yazdir
            for d in detay:
                detail_text.insert(tk.END, d + "\n")
            
            detail_text.config(state=tk.DISABLED)

    def export_satis_maliyet_excel(self):
        """Analiz sonuçlarını Excel'e aktar"""
        try:
            # Masaüstü yolunu bul
            desktop_path = os.path.join(os.path.expanduser("~"), "Desktop")
            if not os.path.exists(desktop_path):
                desktop_path = os.path.join(os.path.expanduser("~"), "OneDrive", "Desktop")
                if not os.path.exists(desktop_path):
                    desktop_path = os.path.expanduser("~")
            
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"Satis_Maliyet_Analizi_{timestamp}.xlsx"
            filepath = os.path.join(desktop_path, filename)
            
            # Treeview verilerini al
            data = []
            for child in self.satis_maliyet_tree.get_children():
                values = self.satis_maliyet_tree.item(child)['values']
                data.append(values)
            
            if not data:
                messagebox.showwarning("Uyarı", "Excel'e aktarılacak veri yok! Önce analizi çalıştırın.")
                return
            
            # DataFrame oluştur
            columns = ["Ürün Adı", "Satış Fiyatı (TL)", "Maliyet (TL)", "Kar (TL)", "Kar %", "Durum"]
            df = pd.DataFrame(data, columns=columns)
            
            # Excel'e kaydet
            with pd.ExcelWriter(filepath, engine='openpyxl') as writer:
                df.to_excel(writer, sheet_name='Satış Maliyet Analizi', index=False)
                
                # İstatistikler sayfası
                stats_data = [
                    ['Toplam Satış Ürünü', self.satis_count_label.cget('text')],
                    ['Toplam Reçete', self.recete_count_label.cget('text')],
                    ['Eşleşen Ürün', self.eslesen_count_label.cget('text')],
                    ['Eşleşme Oranı', self.eslesen_oran_label.cget('text')]
                ]
                stats_df = pd.DataFrame(stats_data, columns=['Metrik', 'Değer'])
                stats_df.to_excel(writer, sheet_name='İstatistikler', index=False)
            
            messagebox.showinfo("Başarılı", f"Analiz Excel'e aktarıldı:\n{filepath}")
            
        except Exception as e:
            messagebox.showerror("Hata", f"Excel aktarımında hata:\n{str(e)}")

    def refresh_satis_maliyet(self):
        """Satış-maliyet analizini yenile"""
        self.run_satis_maliyet_analysis()

    # =========================================================================
    # RESTORAN YÖNETİMİ FONKSİYONLARI
    # =========================================================================
    
    def on_search_key(self, event=None):
        """Arama fonksiyonu"""
        q = self.search_var.get().strip().lower()
        if not q:
            self.update_menu_tree()
            return
        filtered = [name for name in menu.keys() if q in name.lower()]
        self.update_menu_tree(filtered=filtered)
    
    def update_menu_tree(self, filtered=None):
        """Menü ağacını güncelle - Alfabetik sıralama ile"""
        for row in self.menu_tree.get_children():
            self.menu_tree.delete(row)
        items = filtered if filtered is not None else list(menu.keys())
        # Alfabetik sıralama
        items = sorted(items, key=str.lower)
        for i, item in enumerate(items):
            price = menu.get(item, "")
            tag = "odd" if i % 2 else "even"
            try:
                self.menu_tree.insert("", tk.END, values=(item, f"{format_currency(price)}"), tags=(tag,))
            except Exception:
                self.menu_tree.insert("", tk.END, values=(item, str(price)), tags=(tag,))

    def select_table(self, name):
        """Masa seç"""
        global selected_table_name
        selected_table_name = name
        for t_name, (frame, _, _, _) in table_widgets.items():
            if t_name == name:
                frame.config(highlightthickness=3, highlightbackground="#1976d2")
            else:
                frame.config(highlightthickness=0)
        self.selected_table_label.config(text=f"Seçili Masa: {selected_table_name}")
        self.update_selected_table_revenue_display()

    def refresh_table(self, table_name):
        """Masa görünümünü yenile"""
        frame, listbox, total_label, info_label = table_widgets[table_name]
        listbox.delete(0, tk.END)
        total = 0.0
        for item, price in tables[table_name]:
            try:
                total += float(price)
                listbox.insert(tk.END, f"{item} - {float(price):.2f} TL")
            except:
                listbox.insert(tk.END, f"{item} - {price} TL")
        total_label.config(text=f"Toplam: {format_currency(total)} TL")
        
        # Kişi sayısı ve not bilgilerini göster
        people_count = table_people.get(table_name, 0)
        note_text = table_notes.get(table_name, "")
        info_text = f"Kişi: {people_count}"
        if note_text:
            info_text += f" | Not: {note_text[:30]}{'...' if len(note_text) > 30 else ''}"
        info_label.config(text=info_text)
        
        self.update_menu_daily_revenue()
        self.update_selected_table_revenue_display()
        self.ensure_active_order_for_table(table_name)

    def colorize_table_area(self, table_name, color_hex):
        """Masa alanını renklendir"""
        try:
            frame, listbox, total_label, info_label = table_widgets[table_name]
            frame.config(bg=color_hex)
            listbox.config(bg=color_hex)
            total_label.config(bg=color_hex)
            info_label.config(bg=color_hex)
        except Exception:
            pass

    # =========================================================================
    # MUTFAK SİPARİŞ YÖNETİMİ
    # =========================================================================
    
    def ensure_active_order_for_table(self, table_name):
        """Masa için aktif sipariş sağla"""
        try:
            current_items = list(tables.get(table_name, []))
            if not current_items:
                self.clear_active_order_for_table(table_name)
                return
            
            oid = table_active_order_id.get(table_name)
            people = int(table_people.get(table_name, 0))
            note = table_notes.get(table_name, "")
            
            # Baseline ile delta hesapla
            baseline = table_ready_baseline.get(table_name, [])
            def to_counts(lst):
                d = {}
                for it in lst:
                    d[it] = d.get(it, 0) + 1
                return d
            
            base_counts = to_counts(baseline)
            cur_counts = to_counts(current_items)
            delta = []
            for it, c in cur_counts.items():
                b = base_counts.get(it, 0)
                if c > b:
                    delta.extend([it] * (c - b))

            if not oid:
                if delta:
                    oid = datetime.now().strftime("%Y%m%d%H%M%S%f")
                    table_active_order_id[table_name] = oid
                    active_orders[oid] = {"table": table_name, "items": delta, "ready": False, "created": datetime.now().isoformat(), "people": people, "note": note}
            else:
                if oid in active_orders:
                    if active_orders[oid].get("ready", False):
                        if delta:
                            new_oid = datetime.now().strftime("%Y%m%d%H%M%S%f")
                            table_active_order_id[table_name] = new_oid
                            active_orders[new_oid] = {"table": table_name, "items": delta, "ready": False, "created": datetime.now().isoformat(), "people": people, "note": note}
                    else:
                        if delta:
                            active_orders[oid]["items"] = delta
                            active_orders[oid]["people"] = people
                            active_orders[oid]["note"] = note
                        else:
                            self.clear_active_order_for_table(table_name)
        except Exception:
            pass

    def clear_active_order_for_table(self, table_name):
        """Masa için aktif siparişi temizle"""
        try:
            oid = table_active_order_id.pop(table_name, None)
            if oid and oid in active_orders and not active_orders[oid].get("paid"):
                del active_orders[oid]
        except Exception:
            pass

    def mark_order_paid(self, order_id, table_name):
        """Siparişi ödendi olarak işaretle"""
        try:
            if order_id in active_orders:
                active_orders[order_id]["paid"] = True
            if table_active_order_id.get(table_name) == order_id:
                table_active_order_id.pop(table_name, None)
        except Exception:
            pass

    # =========================================================================
    # MENÜ YÖNETİMİ
    # =========================================================================
    
    def add_product(self):
        """V8 YENİLİK: Ürün ekle - Maliyet sekmesine yönlendirme"""
        # V8 YENİLİK: Kullanıcıyı maliyet sekmesine yönlendir
        result = messagebox.askyesno(
            "Yemek Ekleme", 
            "Yeni yemek eklemek için reçete düzenlemesi gerekiyor.\n\n"
            "Maliyet sekmesine geçip reçete oluşturmak ister misiniz?\n\n"
            "• EVET: Maliyet sekmesine geçeceğiz\n"
            "• HAYIR: İşlem iptal edilecek"
        )
        
        if result:
            # Maliyet sekmesine geç (sekme indeksi 1)
            self.notebook.select(1)
            messagebox.showinfo(
                "Maliyet Sekmesi", 
                "🍽️ Maliyet sekmesine geçtiniz!\n\n"
                "Sol taraftan yemek seçip reçete düzenleyebilir,\n"
                "veya yeni yemek için reçete oluşturabilirsiniz.\n\n"
                "📌 İpucu: Reçete oluşturduktan sonra 'Yemekleri Kaydet' "
                "butonuna tıklayarak Excel'e kaydedin."
            )
        else:
            messagebox.showinfo("İptal", "Yemek ekleme işlemi iptal edildi.")

    # V8 YENİLİK: Menü güncelleme fonksiyonu
    def refresh_menu_from_excel(self):
        """Excel'den menüyü güncelle"""
        try:
            # Menü önbelleğini yeniden yükle
            self.load_menu_cache()
            
            # Maliyet dataframe'lerini yeniden yükle
            self.load_cost_dataframes()
            
            # Arayüzleri güncelle
            self.update_menu_tree()
            self.populate_meals()
            
            # Ciro bilgilerini güncelle
            self.update_all_revenue()
            
            messagebox.showinfo("Başarılı", "✅ Menü Excel'den başarıyla güncellendi!\n\n• Yemek listesi güncellendi\n• Reçeteler güncellendi\n• Fiyatlar güncellendi\n• Ciro bilgileri güncellendi")
            
        except Exception as e:
            messagebox.showerror("Hata", f"Menü güncellenirken hata oluştu:\n{e}")
            print(f"[DEBUG] Menü güncelleme hatası: {e}")
            traceback.print_exc()

    # V8 YENİLİK: Satın alma fonksiyonları
    def save_purchase(self):
        """Satın alma kaydını Excel'e ekle"""
        try:
            # Form verilerini al
            product_name = self.purchase_product_var.get().strip()
            quantity_str = self.purchase_quantity_var.get().strip()
            price_str = self.purchase_price_var.get().strip()
            unit = self.purchase_unit_var.get().strip()
            supplier = self.purchase_supplier_var.get().strip()
            date_str = self.purchase_date_var.get().strip()
            
            # Validasyon
            if not product_name:
                messagebox.showwarning("Uyarı", "Ürün adı boş olamaz!")
                return
            
            if not quantity_str or not price_str:
                messagebox.showwarning("Uyarı", "Miktar ve fiyat bilgileri gerekli!")
                return
            
            # Sayısal değerleri parse et
            try:
                quantity = parse_float(quantity_str)
                price = parse_float(price_str)
            except ValueError as e:
                messagebox.showwarning("Hata", f"Geçersiz sayı formatı: {e}")
                return
            
            if quantity <= 0 or price <= 0:
                messagebox.showwarning("Uyarı", "Miktar ve fiyat sıfırdan büyük olmalı!")
                return
            
            # Tarih validasyonu
            try:
                datetime.strptime(date_str, '%Y-%m-%d')
            except ValueError:
                messagebox.showwarning("Uyarı", "Tarih formatı hatalı! (YYYY-MM-DD)")
                return
            
            # Toplam fiyat hesapla
            total_price = quantity * price
            
            # Excel dosyasına ekle - Yeni format: Tarih, Ürün Adı, Miktar, Alış Fiyatı, Birim, Tedarikçi
            new_row_data = [[date_str, product_name, quantity, price, unit, supplier]]
            headers = ["Tarih", "Ürün Adı", "Miktar", "Alış Fiyatı (TL)", "Birim", "Tedarikçi"]
            
            if safe_excel_append(self.urun_file_path, new_row_data, headers):
                messagebox.showinfo("Başarılı", f"✅ Satın alma kaydı başarıyla eklendi!\n\n"
                                              f"• Ürün: {product_name}\n"
                                              f"• Miktar: {quantity} {unit}\n"
                                              f"• Birim Fiyat: {format_currency(price)} TL\n"
                                              f"• Tedarikçi: {supplier if supplier else 'Belirtilmemiş'}\n"
                                              f"• Tarih: {date_str}")
                
                # Formu temizle
                self.clear_purchase_form()
                
                # Listeyi yenile
                self.refresh_purchase_list()
                
                # Ürünler dataframe'ini yeniden yükle
                self.load_cost_dataframes()
                
            else:
                messagebox.showerror("Hata", "Satın alma kaydı Excel'e eklenemedi!")
                
        except Exception as e:
            messagebox.showerror("Hata", f"Satın alma kaydedilirken hata oluştu:\n{e}")
            print(f"[DEBUG] Satın alma kaydetme hatası: {e}")
            traceback.print_exc()
    
    def clear_purchase_form(self):
        """Satın alma formunu temizle"""
        self.purchase_product_var.set("")
        self.purchase_quantity_var.set("")
        self.purchase_price_var.set("")
        self.purchase_unit_var.set("")
        self.purchase_supplier_var.set("")
        self.purchase_date_var.set(datetime.now().strftime('%Y-%m-%d'))
        self.price_comparison_label.config(text="")  # Karşılaştırma bilgisini temizle
        self.purchase_product_entry.focus()
    
    def on_purchase_product_change(self, *args):
        """FAZ 2 - TALEP 6: Ürün adı değiştiğinde önceki fiyatı göster"""
        product_name = self.purchase_product_var.get().strip()
        
        if not product_name:
            self.price_comparison_label.config(text="")
            return
        
        # Önceki fiyatı kontrol et - Sınıf içi metot çağrılıyor
        previous_data = self.get_previous_purchase_price(product_name)
        
        if previous_data and previous_data['price'] is not None:
            price = previous_data['price']
            date = previous_data.get('date', None)
            
            date_str = ""
            if date and pd.notna(date):
                try:
                    if isinstance(date, str):
                        date_str = f" ({date[:10]})"
                    else:
                        date_str = f" ({date.strftime('%Y-%m-%d')})"
                except:
                    pass
            
            self.price_comparison_label.config(
                text=f"📅 Önceki Alış: {format_currency(price)} TL{date_str}",
                fg="#2196f3"
            )
        else:
            self.price_comparison_label.config(
                text="ℹ️ Bu ürün için henüz satın alma kaydı yok",
                fg="#9e9e9e"
            )

    def clear_all_tables(self):
        """Tüm masaları temizle"""
        from models.data_models import tables, table_widgets, table_people, table_notes, table_active_order_id, active_orders
        
        # Onay al
        if messagebox.askyesno("Onay", "TÜM masaları temizlemek istediğinizden emin misiniz?\n\nBu işlem geri alınamaz!"):
            try:
                for table_name in tables.keys():
                    # Masa verilerini temizle
                    tables[table_name] = []
                    table_people[table_name] = 0
                    table_notes[table_name] = ""
                    
                    # Aktif siparişi temizle
                    if table_name in table_active_order_id:
                        oid = table_active_order_id.pop(table_name)
                        if oid in active_orders:
                            active_orders.pop(oid)
                    
                    # UI'yi güncelle
                    if table_name in table_widgets:
                        _, listbox, total_label, info_label = table_widgets[table_name]
                        listbox.delete(0, tk.END)
                        total_label.config(text="Toplam: 0.00 TL")
                        info_label.config(text="Kişi: 0")
                
                # JSON dosyasını kaydet (JSON kaydetme metodu burada verilmediği için varsayılıyor)
                # globals()['save_json_data']() # Eğer globalde tanımlıysa
                
                messagebox.showinfo("Başarılı", "Tüm masalar başarıyla temizlendi!")
                self.update_all_revenue()  # Ciroyu güncelle
            except Exception as e:
                messagebox.showerror("Hata", f"Masalar temizlenirken hata oluştu:\n{e}")
                print(f"[DEBUG] Masa temizleme hatası: {e}")
                traceback.print_exc()
    
    def on_purchase_price_change(self, *args):
        """FAZ 2 - TALEP 6: Yeni fiyat girildiğinde karşılaştırma yap"""
        product_name = self.purchase_product_var.get().strip()
        new_price_str = self.purchase_price_var.get().strip()
        
        if not product_name or not new_price_str:
            return
        
        try:
            new_price = parse_float(new_price_str)
        except:
            return
        
        # Önceki fiyatı kontrol et - Sınıf içi metot çağrılıyor
        previous_data = self.get_previous_purchase_price(product_name)
        
        if not previous_data or previous_data['price'] is None:
            return
        
        previous_price = previous_data['price']
        date = previous_data.get('date', None)
        
        # Fiyat farkını hesapla
        price_diff = new_price - previous_price
        price_diff_percent = (price_diff / previous_price) * 100 if previous_price > 0 else 0
        
        # Tarih string'i
        date_str = ""
        if date and pd.notna(date):
            try:
                if isinstance(date, str):
                    date_str = f" ({date[:10]})"
                else:
                    date_str = f" ({date.strftime('%Y-%m-%d')})"
            except Exception:
                pass
        
        # Renk ve emoji seç
        if price_diff > 0:
            color = "#f44336"  # Kırmızı - Artış
            trend = "🔺 ART(IŞ"
            sign = "+"
        elif price_diff < 0:
            color = "#4caf50"  # Yeşil - Azalış
            trend = "🔻 AZAŁI(Ş"
            sign = ""
        else:
            color = "#2196f3"  # Mavi - Değişmedi
            trend = "➡️ AYNI"
            sign = ""
        
        # Bilgi mesajı
        comparison_text = (
            f"📅 Önceki: {format_currency(previous_price)} TL{date_str}\n"
            f"{trend}: {sign}{format_currency(abs(price_diff))} TL ({sign}{abs(price_diff_percent):.1f}%)"
        )
        
        self.price_comparison_label.config(text=comparison_text, fg=color)
    
    def refresh_purchase_list(self):
        """Satın alma listesini yenile - THREADING KALDIRILDI, GÜVENLİ SERİ İŞLEM"""
        try:
            # Treeview'ı temizle
            for item in self.purchase_tree.get_children():
                self.purchase_tree.delete(item)
            
            # Excel dosyasını oku (self.urun_df'i yükleyen metot çağrılıyor)
            self.load_cost_dataframes()
            
            # DataFrame kontrolü
            df = self.urun_df.copy()
            
            if df.empty:
                self.purchase_summary_label.config(text="Toplam Alış: 0.00 TL")
                return
            
            # Tarihe göre azalan sırada sırala (en yeni üstte)
            if 'Tarih' in df.columns:
                df['Tarih'] = pd.to_datetime(df['Tarih'], errors='coerce')
                df = df.sort_values('Tarih', ascending=False).reset_index(drop=True)
            
            # Mevcut Ay'ın kaydını göster
            current_month = datetime.now().month
            current_year = datetime.now().year
            
            df_display = df[
                (df['Tarih'].dt.month == current_month) &
                (df['Tarih'].dt.year == current_year)
            ]
            
            total_price = 0.0
            
            # --- SERİ İŞLEM BAŞLANGICI (Kilitlenmeyi önlemek için) ---
            
            for index, row in df_display.iterrows():
                product_name = str(row.get('Ürün Adı', ''))
                date_val = row.get('Tarih', '')
                quantity = row.get('Miktar', 0)
                price = row.get('Alış Fiyatı (TL)', 0)
                unit = str(row.get('Birim', ''))
                supplier = str(row.get('Tedarikçi', ''))
                
                # Tarih formatını düzenle
                try:
                    date_display = date_val.strftime('%Y-%m-%d') if pd.notna(date_val) else ""
                except:
                    date_display = str(date_val)[:10] if str(date_val) != 'nan' else ""
                
                # Sayısal değerleri parse et
                try:
                    quantity = parse_float(quantity) if pd.notna(quantity) else 0.0
                    price = parse_float(price) if pd.notna(price) else 0.0
                except:
                    quantity = 0.0
                    price = 0.0
                
                # Birim fiyatı hesapla
                unit_price = price / quantity if quantity > 0 else 0.0
                total_price += price
                
                # Önceki fiyatı al ve BİRİM FİYAT karşılaştırması yap
                # SINIF İÇİ FONKSİYON çağrılıyor
                previous_purchase = self.get_previous_purchase_price(product_name, date_val)
                
                price_tag = "fiyat_sabit"
                price_comparison = "😊 Değişim Yok (0.0%)"
                
                if previous_purchase and previous_purchase.get('price') is not None and previous_purchase.get('quantity') is not None:
                    prev_price = previous_purchase['price']
                    prev_quantity = previous_purchase.get('quantity', 1)
                    prev_unit_price = prev_price / prev_quantity if prev_quantity > 0 else prev_price
                    
                    if prev_unit_price > 0:
                        price_change_percent = ((unit_price - prev_unit_price) / prev_unit_price) * 100
                        
                        if unit_price > prev_unit_price:
                            price_tag = "fiyat_artmis"
                            price_comparison = f"💸 Artış ({price_change_percent:+.1f}%)"
                        elif unit_price < prev_unit_price:
                            price_tag = "fiyat_azalmis"
                            price_comparison = f"🎉 Düşüş ({price_change_percent:+.1f}%)"
                        else:
                            price_tag = "fiyat_sabit"
                            price_comparison = f"😊 Değişim Yok ({price_change_percent:+.1f}%)"
                    else:
                        price_tag = "fiyat_sabit"
                        price_comparison = "🌟 İlk Alım"
                else:
                    price_tag = "fiyat_sabit"
                    price_comparison = "🌟 İlk Alım"
                
                # Treeview'a ekleme (Ana thread'de güvenli)
                self.purchase_tree.insert("", tk.END, values=(
                    date_display,
                    product_name,
                    f"{quantity:.2f}",
                    unit if unit != 'nan' else '',
                    f"{format_currency(price)}",
                    f"{format_currency(unit_price)}",
                    price_comparison,
                    supplier if supplier != 'nan' else '',
                    "📝 ✏️ Sil"
                ), tags=(price_tag,))
            
            # --- SERİ İŞLEM SONU ---
            
            # Bant şeklinde renk kodlaması (Mevcut kodunuzdan)
            self.purchase_tree.tag_configure("fiyat_sabit", foreground="black", background="#fff9c4")
            self.purchase_tree.tag_configure("fiyat_artmis", foreground="black", background="#ffcdd2")
            self.purchase_tree.tag_configure("fiyat_azalmis", foreground="black", background="#c8e6c9")
            
            # Event Bindingler (Mevcut kodunuzdan)
            self.purchase_tree.bind("<Double-1>", self.on_purchase_tree_double_click)
            self.purchase_tree.bind("<Button-3>", lambda e: self.show_purchase_context_menu(e))
            
            # Bu ayın satış cirosunu hesapla (Mevcut kodunuzdan)
            monthly_sales_revenue = 0.0
            try:
                nostock_file = find_excel_file("menu_cache_nostock.xlsx")
                if nostock_file and os.path.exists(nostock_file):
                    df_sales = pd.read_excel(nostock_file, engine="openpyxl")
                    
                    date_col = 'Tarih'
                    amount_col = 'Fiyat'
                    if date_col in df_sales.columns and amount_col in df_sales.columns:
                        df_sales.loc[:, date_col] = pd.to_datetime(df_sales[date_col], errors='coerce')
                        current_month_sales = df_sales[
                            df_sales[date_col].dt.month == datetime.now().month
                        ]
                        monthly_sales_revenue = current_month_sales[amount_col].sum()
            except Exception as e:
                print(f"[DEBUG] Ciro hesaplama hatası: {e}")
            
            # Toplam göster - alış fiyat toplamı + bu ayın satış cirosu
            self.purchase_summary_label.config(
                text=f"💰 Bu Ay Alış Fiyatları Toplamı: {format_currency(total_price)} TL 💰\n💰 Bu Ay Satış Cirosu: {format_currency(monthly_sales_revenue)} TL",
                font=("Arial", 16, "bold"),
                bg="#fff3cd",
                fg="#856404",
                relief="solid",
                bd=2,
                padx=10,
                pady=8
            )
            
        except Exception as e:
            print(f"[DEBUG] Satın alma listesi yenileme hatası: {e}")
            messagebox.showerror("Hata", f"Satın alma listesi yenilenemedi:\n{e}")
            import traceback
            traceback.print_exc()

    def edit_purchase_record(self, item_id, row):
        # Geçici yer tutucu: gerçek düzenleme mantığı bulunana kadar
        # fonksiyonun boş olması Python'un beklenen girinti hatasına
        # sebep olmasını engellemek için `pass` eklenir.
        pass

# ... (Diğer metotlar olduğu gibi devam eder) ...