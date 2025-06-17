import speech_recognition as sr
import os
import sys
import google.generativeai as genai
import subprocess
import json
import platform
from gtts import gTTS
import uuid
import re
import time
import difflib 
import pygame 
import threading
import urllib.parse 
import tkinter as tk
from tkinter import messagebox

# --- AYARLAR ---
# Lütfen bu API anahtarını Google AI Studio'dan aldığınız kendi GİZLİ anahtarınızla değiştirin.
# Bu anahtarı kimseyle paylaşmayın.
GEMINI_API_KEY = "AIzaSyATsBYWQ051Mnen7lMFr6sDIEUahcnQ2FE" 
genai.configure(api_key=GEMINI_API_KEY)

# Gemini'den yapılandırılmış JSON yanıtı almak için özel ayarlar
generation_config = {
    "response_mime_type": "application/json",
}
# Eylem belirleme için JSON model
action_model = genai.GenerativeModel('gemini-1.5-flash', generation_config=generation_config)
# Genel sohbet için standart metin modeli
chat_model = genai.GenerativeModel('gemini-1.5-flash')

# Pygame modüllerini başlatıyoruz
pygame.init()
pygame.mixer.init()

# --- Konfigürasyon Dosyaları ---
KOMUTLAR_DOSYASI = "ogrenilmis_eylemler.json"
AYARLAR_DOSYASI = "ayarlar.json" 

konusma_aktif = True
r = sr.Recognizer()
# DÜZELTME: Kullanıcının cümle ortasında duraksaması için tanınan süreyi artırdık.
r.pause_threshold = 2.0

# --- YARDIMCI FONKSİYONLAR ---

def ayarlari_yukle():
    """Kaydedilmiş ayarları (örn: mikrofon indeksi) JSON dosyasından yükler."""
    try:
        with open(AYARLAR_DOSYASI, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}

def ayar_kaydet(ayarlar):
    """Ayarları JSON dosyasına kaydeder."""
    with open(AYARLAR_DOSYASI, 'w', encoding='utf-8') as f:
        json.dump(ayarlar, f, indent=4)

def mikrofon_sec_ve_kaydet():
    """Kullanıcıya mikrofon listesini görsel olarak gösterir, seçim yapmasını ister ve kaydeder."""
    try:
        mic_list = sr.Microphone.list_microphone_names()
    except Exception as e:
        print(f"HATA: Mikrofonlar listelenemedi. PyAudio kurulumunuzu kontrol edin. Hata: {e}")
        return None

    if not mic_list:
        print("HATA: Hiç mikrofon bulunamadı.")
        return None

    selected_index = [None]  # Değiştirilebilir tipte tutmak için liste kullandık

    def on_select():
        idx = lb.curselection()
        if idx:
            selected_index[0] = idx[0]
            root.destroy()
        else:
            messagebox.showerror("Seçim Hatası", "Lütfen bir mikrofon seçin.")

    root = tk.Tk()
    root.title("Mikrofon Seçiniz")
    root.geometry("500x300")
    tk.Label(root, text="Kullanmak istediğiniz mikrofonu seçin:", font=("Arial", 12)).pack(padx=10, pady=10)
    lb = tk.Listbox(root, width=60, font=("Arial", 10))
    for i, mic in enumerate(mic_list):
        lb.insert(tk.END, f"{i}: {mic}")
    lb.pack(padx=10, pady=5)
    tk.Button(root, text="Seç", command=on_select, font=("Arial", 11)).pack(pady=10)
    root.mainloop()

    if selected_index[0] is not None:
        ayarlar = ayarlari_yukle()
        ayarlar['mic_index'] = selected_index[0]
        ayar_kaydet(ayarlar)
        print(f"'{mic_list[selected_index[0]]}' varsayılan mikrofon olarak ayarlandı.\n")
        return selected_index[0]
    else:
        print("Mikrofon seçilmedi.")
        return None

def eylemleri_yukle():
    """Kaydedilmiş eylemleri JSON dosyasından yükler."""
    try:
        with open(KOMUTLAR_DOSYASI, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}

def eylem_kaydet(sesli_istek, eylem_detaylari):
    """Yeni öğrenilen eylemi JSON dosyasına kaydeder."""
    ogrenilmis_eylemler = eylemleri_yukle()
    ogrenilmis_eylemler[sesli_istek] = eylem_detaylari
    with open(KOMUTLAR_DOSYASI, 'w', encoding='utf-8') as f:
        json.dump(ogrenilmis_eylemler, f, indent=4, ensure_ascii=False)
    print(f"'{sesli_istek}' isteği '{eylem_detaylari['eylem']}' olarak öğrenildi.")

def find_best_match(user_command, commands):
    """Kullanıcının söylediği komuta en çok benzeyen öğrenilmiş komutu bulur."""
    best_match = None
    highest_score = 0.7 
    if not user_command: return None
    for cmd_key in commands.keys():
        score = difflib.SequenceMatcher(None, user_command, cmd_key).ratio()
        if score > highest_score:
            highest_score = score
            best_match = cmd_key
    return best_match

# --- EYLEM İŞLEYİCİLERİ (ASİSTANIN "BEYNİ") ---

def eylem_yonlendirici(eylem_detaylari, asistan_hafizasi):
    """Gelen eyleme göre ilgili Python fonksiyonunu çağırır."""
    eylem = eylem_detaylari.get("eylem")
    parametreler = eylem_detaylari.get("parametreler", {})
    
    if eylem == "klasor_olustur":
        return klasor_olustur_eylemi(parametreler, asistan_hafizasi)
    elif eylem == "program_calistir":
        return program_calistir_eylemi(parametreler, asistan_hafizasi)
    elif eylem == "bilgisayari_yeniden_baslat":
        return yeniden_baslat_eylemi()
    elif eylem == "son_eylemi_ac":
        return son_eylemi_ac_eylemi(asistan_hafizasi)
    elif eylem == "web_arama":
        return web_arama_eylemi(parametreler, asistan_hafizasi)
    elif eylem == "son_yaniti_tekrarla": 
        return son_yaniti_tekrarla_eylemi(asistan_hafizasi)
    else:
        return False, f"'{eylem}' adlı bir eylemi nasıl yapacağımı bilmiyorum."

def klasor_olustur_eylemi(parametreler, asistan_hafizasi):
    """Klasör oluşturma eylemini Python'un kendi komutlarıyla akıllıca gerçekleştirir."""
    try:
        base_path_str = parametreler.get("konum")
        folder_name = parametreler.get("isim")

        if not folder_name: folder_name = "Yeni Klasör"
        if not base_path_str:
            path = os.path.join(os.path.expanduser('~'), 'Desktop')
        elif "masaüstü" in base_path_str.lower() or "desktop" in base_path_str.lower():
            path = os.path.join(os.path.expanduser('~'), 'Desktop')
        elif re.match(r'^[a-zA-Z]:', base_path_str):
             path = base_path_str
        else:
            path = os.path.expanduser(base_path_str.replace("sürücüsü", ":\\").replace("sürücüsünde",":\\"))
        if not os.path.isdir(path):
            print(f"UYARI: '{path}' konumu anlaşılamadı, masaüstü kullanılıyor.")
            path = os.path.join(os.path.expanduser('~'), 'Desktop')

        full_path = os.path.join(path, folder_name)
        final_path = full_path
        counter = 1
        while os.path.exists(final_path):
            final_path = f"{full_path} ({counter})"
            counter += 1
        
        os.makedirs(final_path)
        print(f"Başarıyla oluşturuldu: {final_path}")
        asistan_hafizasi['son_eylem_sonucu'] = {"tip": "klasor", "yol": final_path}
        
        return True, f"Klasörünüz '{os.path.basename(final_path)}' adıyla oluşturuldu."
    except Exception as e:
        print(f"Klasör oluşturma hatası: {e}")
        return False, "Klasörü oluştururken bir sorunla karşılaştım."

def program_calistir_eylemi(parametreler, asistan_hafizasi):
    """Bir programı veya komutu çalıştırır."""
    try:
        program_adi = parametreler.get("program_adi")
        if not program_adi:
            return False, "Çalıştırılacak bir program adı belirtilmedi."
        
        print(f"'{program_adi}' çalıştırılıyor...")
        if platform.system() == "Windows":
            subprocess.Popen(f'start "" "{program_adi}"', shell=True)
        else:
            subprocess.Popen(program_adi, shell=True)
        
        asistan_hafizasi['son_eylem_sonucu'] = {"tip": "program", "isim": program_adi}
        
        if program_adi.startswith("http"):
             try:
                 parsed_url = urllib.parse.urlparse(program_adi)
                 query_params = urllib.parse.parse_qs(parsed_url.query)
                 sorgu = query_params.get('q', [None])[0]
                 if sorgu:
                     return True, f"'{sorgu}' için arama yapılıyor."
                 else:
                     return True, "İsteğiniz tarayıcıda açılıyor."
             except:
                return True, "İsteğiniz tarayıcıda açılıyor."
        else:
            return True, f"'{program_adi}' başlatılıyor."

    except Exception as e:
        print(f"Program çalıştırma hatası: {e}")
        return False, "Programı çalıştırırken bir sorun oluştu."

def yeniden_baslat_eylemi():
    """Bilgisayarı yeniden başlatır."""
    print("Bilgisayar yeniden başlatılıyor...")
    sistem = platform.system()
    try:
        if sistem == "Windows": os.system("shutdown /r /t 1")
        elif sistem in ["Linux", "macOS"]: os.system("sudo reboot")
        return True, "Bilgisayar yeniden başlatılıyor."
    except Exception as e:
        return False, "Yeniden başlatma komutunu çalıştıramadım."

def son_eylemi_ac_eylemi(asistan_hafizasi):
    """Hafızadaki son eylem sonucunu açar."""
    son_eylem = asistan_hafizasi.get('son_eylem_sonucu')
    if not son_eylem:
        return False, "Hafızamda açabileceğim bir şey yok."

    if son_eylem.get("tip") == "klasor":
        yol = son_eylem.get("yol")
        return program_calistir_eylemi({"program_adi": yol}, asistan_hafizasi)
    else:
        return False, "En son yaptığım eylemin sonucunu açamam."

def web_arama_eylemi(parametreler, asistan_hafizasi):
    """İnternette bir arama yapar."""
    try:
        sorgu = parametreler.get("sorgu")
        if not sorgu:
            return False, "Arama yapmak için bir terim belirtmediniz."
        
        url_sorgu = urllib.parse.quote_plus(sorgu)
        arama_url = f"https://www.google.com/search?q={url_sorgu}"
        
        return program_calistir_eylemi({"program_adi": arama_url}, asistan_hafizasi)
    except Exception as e:
        print(f"Web arama hatası: {e}")
        return False, "Arama yaparken bir sorun oluştu."

def son_yaniti_tekrarla_eylemi(asistan_hafizasi):
    """Hafızadaki son sesli yanıtı kullanıcıya söyler."""
    son_yanit_metni = asistan_hafizasi.get('son_sesli_yanit')
    if son_yanit_metni:
        return True, son_yanit_metni
    else:
        return False, "Henüz tekrar edecek bir şey söylemedim."

# --- SESLİ YANIT FONKSİYONU ---
def sesli_yanit(text, asistan_hafizasi):
    """
    Verilen metni Google'ın doğal sesiyle seslendirir.
    Yeni bir ses çalmadan önce, önceki sesi keser ve yanıtı hafızaya kaydeder.
    """
    asistan_hafizasi['son_sesli_yanit'] = text

    def play_and_delete(filename):
        """Sesi çalar ve bittikten sonra dosyayı siler."""
        try:
            pygame.mixer.music.load(filename)
            pygame.mixer.music.play()
            while pygame.mixer.music.get_busy():
                time.sleep(0.1)
            pygame.mixer.music.unload()
            time.sleep(0.2) 
            os.remove(filename)
        except Exception as e:
            print(f"Hata (play_and_delete): {e}")

    if not text or not konusma_aktif: return None
    print(f"Sesli Yanıt: {text}")
    try:
        if pygame.mixer.music.get_busy():
            pygame.mixer.music.stop()

        tts = gTTS(text=text, lang='tr')
        filename = f"temp_{uuid.uuid4()}.mp3"
        tts.save(filename)
        
        playback_thread = threading.Thread(target=play_and_delete, args=(filename,), daemon=True)
        playback_thread.start()
        return playback_thread
        
    except Exception as e:
        print(f"Sesli yanıt sırasında bir hata oluştu: {e}")
        return None

# --- ANA DÖNGÜ ---
def ana_dongu(mic_index):
    global konusma_aktif
    ogrenilmis_eylemler = eylemleri_yukle()
    asistan_hafizasi = {} 

    try:
        with sr.Microphone(device_index=mic_index) as source:
            print("\n--- Akıllı Sesli Asistan (Nihai Sürüm) ---")
            playback_thread = sesli_yanit("Asistan hazır.", asistan_hafizasi)
            if playback_thread: playback_thread.join() 

            while True:
                print("\nDinliyorum...")
                try:
                    r.adjust_for_ambient_noise(source, duration=0.5)
                    audio = r.listen(source)
                    text = r.recognize_google(audio, language="tr-TR").lower()
                    print(f"Anlaşılan: '{text}'")

                    if text == "çıkış":
                        playback_thread = sesli_yanit("Görüşmek üzere.", asistan_hafizasi)
                        if playback_thread: playback_thread.join()
                        break
                    elif text == "sus":
                        konusma_aktif = False
                        continue
                    elif text == "konuş":
                        konusma_aktif = True
                        playback_thread = sesli_yanit("Tekrar konuşuyorum.", asistan_hafizasi)
                        if playback_thread: playback_thread.join()
                        continue

                    matched_command = find_best_match(text, ogrenilmis_eylemler)
                    if matched_command:
                        eylem_detaylari = ogrenilmis_eylemler[matched_command]
                        basarili, mesaj = eylem_yonlendirici(eylem_detaylari, asistan_hafizasi)
                        playback_thread = sesli_yanit(mesaj, asistan_hafizasi)
                        if playback_thread: playback_thread.join()
                        continue

                    # Gemini'ye gönderilen prompt artık tüm eylemleri ve kuralları kapsıyor.
                    prompt = (f"Kullanıcının isteği: '{text}'. Bu isteği analiz et ve aşağıdaki eylemlerden hangisine uyduğunu JSON formatında belirt: "
                              f"'klasor_olustur', 'program_calistir', 'bilgisayari_yeniden_baslat', 'son_eylemi_ac', 'web_arama', 'son_yaniti_tekrarla', 'bilinmeyen_eylem'. "
                              f"JSON objesi bir 'eylem' anahtarı ve 'parametreler' adlı bir alt obje içermeli. Parametreleri istekten çıkarım yap. "
                              f"KURALLAR: "
                              f"1. Eğer 'klasor_olustur' eylemi isteniyorsa ama isim belirtilmemişse, 'isim' değerini 'Yeni Klasör' yap. Konum belirtilmemişse 'konum' değerini 'masaustu' yap. "
                              f"2. Eğer istek, web'de bir arama ise (örn: 'internette bak', 'araştır'), 'eylem' değerini 'web_arama' yap ve 'sorgu' parametresine aranacak kelimeleri ekle. "
                              f"3. Eğer istek 'tekrar et', 'ne dedin' gibi bir anlam taşıyorsa, 'eylem' değerini 'son_yaniti_tekrarla' yap. "
                              f"4. Eğer eylem anlaşılamıyorsa 'eylem' değerini 'bilinmeyen_eylem' yap. "
                              f"ÖRNEKLER: "
                              f"İstek: 'google'da bugünün hava durumunu araştır' -> {{\"eylem\": \"web_arama\", \"parametreler\": {{\"sorgu\": \"bugünün hava durumu\"}}}} "
                              f"İstek: 'son söylediğini tekrarla' -> {{\"eylem\": \"son_yaniti_tekrarla\", \"parametreler\": {{}}}}")
                    
                    response = action_model.generate_content(prompt)
                    eylem_detaylari = json.loads(response.text)
                    
                    eylem = eylem_detaylari.get("eylem")

                    if eylem != "bilinmeyen_eylem":
                        basarili, mesaj = eylem_yonlendirici(eylem_detaylari, asistan_hafizasi)
                        playback_thread = sesli_yanit(mesaj, asistan_hafizasi)
                        if playback_thread: playback_thread.join()
                    else:
                        context_prompt = (f"Sen, bir Türk kullanıcının bilgisayarında çalışan kişisel bir sesli asistansın. "
                                          f"Sana sorulan sorulara her zaman Türkçe, kısa, doğrudan ve sohbet havasında yanıt ver. "
                                          f"Liste veya madde imleri kullanmaktan kaçın. "
                                          f"Kullanıcının sorusu şu: '{text}'")
                        sohbet_yaniti = chat_model.generate_content(context_prompt)
                        playback_thread = sesli_yanit(sohbet_yaniti.text, asistan_hafizasi)
                        if playback_thread: playback_thread.join()

                except sr.UnknownValueError:
                    print("Anlayamadım.")
                except sr.RequestError as e:
                    print(f"Servis hatası; {e}")
                except KeyboardInterrupt:
                    sesli_yanit("Hoşça kalın.", asistan_hafizasi)
                    break
    except Exception as e:
        print(f"\nKRİTİK HATA: Mikrofon başlatılamadı - {e}")

if __name__ == "__main__":
    ayarlar = ayarlari_yukle()
    mic_index = ayarlar.get('mic_index')
    
    if mic_index is None:
        mic_index = mikrofon_sec_ve_kaydet()

    if mic_index is not None:
        ana_dongu(mic_index)
