"""
Restoran Yönetim Sistemi - Debug Version
"""

import sys
import os
import traceback

# Modül yolunu ekle
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def main():
    """Ana uygulama başlatma fonksiyonu"""
    try:
        print("=== DEBUG: Program başlatılıyor ===")
        
        import tkinter as tk
        from gui import main_window
        
        print("=== DEBUG: Tkinter ve modüller import edildi ===")
        
        # Tkinter pencere oluşturulmaya çalışılıyor; eğer ortamda GUI yoksa
        # `tk.TclError` fırlatılacaktır. Bu durumda uygulama headless moda
        # geçer ve GUI gerektirmeyen başlangıç görevleri (ör. örnek excel
        # dosyalarını oluşturma) yapılıp temiz şekilde sonlandırılır.
        try:
            root = tk.Tk()
            print("=== DEBUG: Tk penceresi oluşturuldu ===")

            app = main_window.RestaurantSystemV7(root)
            print("=== DEBUG: RestaurantSystemV7 oluşturuldu ===")

            print("=== DEBUG: mainloop başlatılıyor ===")
            root.mainloop()
        except tk.TclError as e:
            # Başta tkinter importu başarılı olabilir ama pencere oluşturulamaz
            # (ör. CI/container'da DISPLAY yok). Bu durumda headless fallback uygula.
            print(f"⚠️ GUI başlatılamıyor: {e}")
            print("ℹ️ Headless başlangıç modu: GUI yerine arka plan görevleri çalıştırılıyor.")
            try:
                # Örnek excel oluşturma gibi güvenli başlangıç görevlerini çalıştır
                from utils.excel_handler import create_sample_excels
                base_path = os.path.dirname(os.path.abspath(__file__))
                create_sample_excels(base_path)
            except Exception as ex:
                print(f"❌ Headless başlangıçta hata: {ex}")
                traceback.print_exc()
            return
        
    except Exception as e:
        print(f"❌ CRITICAL ERROR: {e}")
        traceback.print_exc()
        input("Çıkmak için Enter'a basın...")

if __name__ == "__main__":
    main()